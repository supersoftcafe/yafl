"""MatchArm and MatchExpression — pattern matching on union types."""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from functools import reduce
from typing import Callable

from langtools import cast
from parsing.tokenizer import LineRef
from parsing.parselib import Error

import codegen.ops as cg_o
import codegen.param as cg_p
import codegen.typedecl as cg_t

import pyast.expression as e
import pyast.resolver as g
import pyast.statement as s
import pyast.typespec as t


# Primitive builtin types that support literal-pattern matching: arbitrary-
# precision Int (bigint), String (str), and the fixed-width integers (int8..
# int64). A char literal is an int32, so matching characters lands here.
_PRIMITIVE_MATCH_INT_TYPES = ("bigint", "int8", "int16", "int32", "int64")

def _is_primitive_match_type(type_name: str) -> bool:
    return type_name == "str" or type_name in _PRIMITIVE_MATCH_INT_TYPES

def _match_int_precision(type_name: str) -> int:
    """Expected IntegerExpression.precision for an integer-like match subject:
    0 for bigint, else the fixed width (int32 → 32)."""
    return 0 if type_name == "bigint" else int(type_name[3:])


def _arm_unique_name(arm: "MatchArm") -> str:
    """Per-arm unique name for the bound variable.

    Two arms in the same source can use the same identifier (e.g. `Int a`
    and `Str a`), each with its own type.  We rename the binding to a
    name unique per source location so each arm gets its own typed local
    and its own state-object field, eliminating the name-aliased-different-
    type situation that downstream substitution previously had to paper
    over.  hash6() is derived from line_ref so the result is deterministic
    across runs and stable across compile passes.

    Idempotent: once an arm carries the unique suffix, returning the same
    arm yields the same name (so re-running compile is a no-op, and the
    suffix that ast_inline appends to disambiguate inlined copies survives
    a second look-up).  Returns the input verbatim when there is no name
    to rename (else arm with no binding, or `_`).
    """
    if not arm.name or arm.name == "_":
        return arm.name
    if "@arm" in arm.name:
        return arm.name
    return f"{arm.name}@arm{arm.line_ref.hash6()}"


def _binding_finder(arm: "MatchArm", bound_type: t.TypeSpec) -> Callable[[str], list]:
    """The one way an arm's bound name resolves: a LetStatement of
    `bound_type` under the arm's unique name. Matches either the user-typed
    name (first compile pass on the body) or the already-rewritten unique
    name (subsequent passes and generate-time lookups)."""
    uniq = _arm_unique_name(arm)
    def find(query: str, a=arm, ty=bound_type, u=uniq) -> list:
        if u == query or g.name_matches(a.name, query):
            let = s.LetStatement(a.line_ref, u, None, {}, (), None, ty)
            return [g.Resolved(u, let, g.ResolvedScope.LOCAL)]
        return []
    return find


def _binding_resolver(resolver: g.Resolver, arm: "MatchArm",
                      bound_type: t.TypeSpec | None) -> g.Resolver:
    """Extend `resolver` with the arm's bound name (no-op for unbound/`_`)."""
    if not arm.name or arm.name == "_" or bound_type is None:
        return resolver
    return g.ResolverData(resolver, _binding_finder(arm, bound_type))


def _literal_eq_test(lit_type_name: str, value: cg_p.RParam,
                     literal: cg_p.RParam) -> cg_p.RParam:
    """Boolean IR expression comparing a primitive `value` to a `literal`."""
    args = cg_p.NewStruct((("a", value), ("b", literal)))
    if lit_type_name == "str":
        return cg_p.IntEqConst(cg_p.Invoke("string_compare", args, cg_t.Int(32)), 0)
    if lit_type_name == "bigint":
        return cg_p.Invoke("integer_test_eq", args, cg_t.Int(8))
    return cg_p.Invoke(f"{lit_type_name}_test_eq", args, cg_t.Int(8))  # int8..int64


@dataclass
class MatchArm:
    """One arm of a match expression.

    Exactly one of the following holds:
    - `literal` is set (IntegerExpression or StringExpression): literal arm.
    - `type_spec` is set (with optional `name`): type-dispatch arm.
    - Both `literal` and `type_spec` are None: else arm (with optional `name`
      that binds the whole subject).
    """
    line_ref: LineRef
    name: str | None         # Bound variable name; None for else arm, "_" to discard
    type_spec: t.TypeSpec | None  # Variant type; None for else or literal arm
    body: e.Expression
    literal: e.Expression | None = None  # Literal value to match against

    def __body_resolver(self, resolver: g.Resolver) -> g.Resolver:
        # The else arm's binding type (the whole subject) isn't knowable
        # here; MatchExpression.compile supplies it. Typed arms bind their
        # own type_spec.
        return _binding_resolver(resolver, self, self.type_spec)

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver, any], any]) -> MatchArm:
        new_body = self.body.search_and_replace(self.__body_resolver(resolver), replace)
        new_type = self.type_spec.search_and_replace(resolver, replace) if self.type_spec else None
        new_literal = self.literal.search_and_replace(resolver, replace) if self.literal else None
        return dataclasses.replace(self, type_spec=new_type, body=new_body, literal=new_literal)

    def compile(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> tuple[MatchArm, list[s.Statement]]:
        new_body, body_stmts = self.body.compile(self.__body_resolver(resolver), func_ret_type)
        new_type, type_stmts = self.type_spec.compile(resolver) if self.type_spec else (None, [])
        new_literal, lit_stmts = self.literal.compile(resolver, None) if self.literal else (None, [])
        # Rename arm.name to the unique form so it stays in sync with the
        # body's NamedExpressions (which the binding finder rewrote during
        # the body.compile() call above).  ast_inline then renames arm.name
        # and the body together; without this, those two sides would desync.
        return dataclasses.replace(self, name=_arm_unique_name(self),
                                    type_spec=new_type, body=new_body, literal=new_literal), body_stmts + type_stmts + lit_stmts

    def get_body_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        return self.body.get_type(self.__body_resolver(resolver))

    def check(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> list:
        type_err = self.type_spec.check(resolver) if self.type_spec else []
        body_err = self.body.check(self.__body_resolver(resolver), func_ret_type)
        literal_err = self.literal.check(resolver, None) if self.literal else []
        return type_err + body_err + literal_err


@dataclass
class _Emitter:
    """Control-flow scaffolding shared by every match flavour.

    A match is a chain of guarded arms over one subject:

        [guard stages] -> bind -> body -> jump to the shared join
        (fail any stage -> next arm)        ...
        fallback (else / abort)
        join: Phi over every arm's exit edge

    The generators below differ only in how they TEST (vtable identity, $tag
    compare, literal equality, null check) and how they BIND (the pointer
    itself, slots reassembled into the arm's type, a narrowed sub-union).
    Everything else — labels, jumps, the value join — lives here, once. See
    arm() for how a guard is expressed.
    """
    owner: "MatchExpression"
    resolver: g.Resolver
    result_type: t.TypeSpec | None
    bundles: list = field(default_factory=list)
    arm_results: list = field(default_factory=list)   # (exit_label, value) per arm
    end_label: str = "match_end"
    counter: int = 0

    def ops(self, *operations: cg_o.Op, stack_vars: tuple = ()) -> None:
        self.bundles.append(g.OperationBundle(stack_vars=stack_vars, operations=operations))

    def add(self, bundle: g.OperationBundle) -> None:
        self.bundles.append(bundle)

    def next_index(self) -> int:
        self.counter += 1
        return self.counter - 1

    def arm(self, arm: MatchArm, stages: list[list[cg_p.RParam]],
            bind: tuple[g.OperationBundle, g.Resolver] | None = None,
            pre: tuple[g.OperationBundle, ...] = ()) -> None:
        """One guarded arm. `stages` is a sequence of checks that must ALL
        pass to reach the body; each check is a list of alternatives, and ANY
        one of them passing clears that check. So:
          - an ordinary typed arm:   [["tag == 24"]]
          - a union arm (Word|None): [["is Word", "is None"]]
          - a literal on a pointer:  [["is a string"], ["equals \"foo\""]]
        Failing a check (no alternative hit) falls through to the next arm.
        `bind` carries the optional binding bundle and the resolver exposing
        the bound name to the body."""
        idx = self.next_index()
        arm_label, next_label = f"match_arm_{idx}", f"match_next_{idx}"
        for b in pre:
            self.add(b)
        for stage_no, guards in enumerate(stages):
            pass_label = arm_label if stage_no == len(stages) - 1 else f"match_stage_{idx}_{stage_no}"
            for guard in guards:
                self.ops(cg_o.JumpIf(pass_label, guard))
            self.ops(cg_o.Jump(next_label))
            self.ops(cg_o.Label(pass_label))
        self.__body(arm, bind, f"arm{idx}")
        self.ops(cg_o.Label(next_label))

    def multi_entry_arm(self, arm: MatchArm, entries: list[tuple[cg_p.RParam, cg_p.RParam]],
                        bound_ctype: cg_t.Type) -> None:
        """One arm with several entry edges, each binding a DIFFERENT value —
        the tagged-union narrow arm: per member, a tag guard and the value
        narrowed for that member. The bound variable is defined once, by a
        Phi over the entry edges (SSA single-definition)."""
        idx = self.next_index()
        next_label, body_label = f"match_next_{idx}", f"match_armbody_{idx}"
        binds: list[tuple[str, cg_p.RParam]] = []
        for k, (guard, value) in enumerate(entries):
            entry_label = f"match_arm_{idx}_m{k}"
            self.ops(cg_o.JumpIf(entry_label, guard))
            binds.append((entry_label, value))
        self.ops(cg_o.Jump(next_label))
        for entry_label, _ in binds:
            self.ops(cg_o.Label(entry_label), cg_o.Jump(body_label))
        arm_sv = cg_p.StackVar(bound_ctype, _arm_unique_name(arm))
        self.ops(cg_o.Label(body_label),
                 cg_o.Phi(target=arm_sv, sources=tuple(binds)),
                 stack_vars=(arm_sv,))
        resolver = _binding_resolver(self.resolver, arm, arm.type_spec)
        self.__body(arm, (None, resolver), f"arm{idx}")
        self.ops(cg_o.Label(next_label))

    def fallback(self, arm: MatchArm | None,
                 bind: tuple[g.OperationBundle, g.Resolver] | None,
                 abort_reason: str) -> None:
        """The unguarded tail: the else arm if present, else an explicit
        Abort — control must not reach the join with the result slot
        uninitialised, and the Abort keeps the unreachable path out of the
        Phi."""
        if arm is not None:
            self.__body(arm, bind, "else")
        else:
            self.ops(cg_o.Abort(reason=abort_reason))

    def finish(self, result_var: cg_p.StackVar | None) -> g.OperationBundle:
        """The join: a Phi collecting one source per arm — or a bare label if
        the match has no value, or an Abort if it SHOULD have one but every
        arm transferred control away (e.g. a [tail] recur on every path): a
        fall-through label there would hand the enclosing join a predecessor
        edge its Phi has no source for."""
        if result_var is None:
            self.ops(cg_o.Label(self.end_label))
        elif not self.arm_results:
            self.ops(cg_o.Label(self.end_label),
                     cg_o.Abort(reason="unreachable match join: every arm transferred control"))
        else:
            self.add(g.OperationBundle(
                stack_vars=(result_var,),
                operations=(cg_o.Label(self.end_label),
                            cg_o.Phi(target=result_var, sources=tuple(self.arm_results))),
                result_var=result_var))
        return reduce(lambda a, b: a + b, self.bundles)

    # -- internals ------------------------------------------------------------

    def __body(self, arm: MatchArm, bind, prefix: str) -> None:
        """Binding bundle (if any), the arm body generated TO the shared slot
        type (so narrow arms widen before the join), an exit label naming
        this arm's Phi edge, and the jump to the join — suppressed when the
        body already ended in a control transfer, whose dead jump would give
        the join a sourceless predecessor edge."""
        bind_bundle, arm_resolver = bind if bind is not None else (None, self.resolver)
        if bind_bundle is not None:
            self.add(bind_bundle.with_prefix(prefix))
        body_bundle = arm.body.generate_to(arm_resolver, self.result_type).with_prefix(prefix)
        self.add(body_bundle)
        if body_bundle.result_var is not None:
            exit_label = f"{prefix}_exit"
            self.ops(cg_o.Label(exit_label))
            self.arm_results.append((exit_label, body_bundle.result_var))
        last = self.bundles[-1].operations
        if not (last and isinstance(last[-1],
                (cg_o.Jump, cg_o.Return, cg_o.ReturnVoid, cg_o.Abort, cg_o.SwitchJump))):
            self.ops(cg_o.Jump(self.end_label))

    # -- binding constructors (used by the generators) -------------------------

    def bind_subject(self, arm: MatchArm, bound_type: t.TypeSpec,
                     value: cg_p.RParam) -> tuple[g.OperationBundle, g.Resolver] | None:
        """Bind the arm name to `value` at `bound_type` — the common case
        where the subject (or the subject pointer) IS the arm's value."""
        if not arm.name or arm.name == "_":
            return None
        arm_ctype = bound_type.generate(self.resolver)
        # A unit-typed arm in a pointer union (the `None` of `Box|None`)
        # carries no data: the subject is object_t* and cannot assign to a
        # struct{}, so synthesise the empty value instead.
        if isinstance(arm_ctype, cg_t.Struct) and not arm_ctype.fields:
            value = cg_p.ZeroOf(arm_ctype)
        arm_sv = cg_p.StackVar(arm_ctype, _arm_unique_name(arm))
        bundle = g.OperationBundle(stack_vars=(arm_sv,), operations=(cg_o.Move(arm_sv, value),))
        return bundle, _binding_resolver(self.resolver, arm, bound_type)

    def bind_from_slots(self, arm: MatchArm, arm_ctype, slot_assignments,
                        slot_fields, sv: cg_p.RParam) -> tuple[g.OperationBundle, g.Resolver] | None:
        """Bind the arm name to the variant value reassembled from union
        slots. `slot_assignments` is variant_map[var_idx]: one (slot_index,
        orig_type) per primitive of this variant; a multi-primitive variant
        is rebuilt field by field."""
        if not arm.name or arm.name == "_":
            return None

        def reconstruct(ctype, offset):
            if not isinstance(ctype, cg_t.Struct):
                si, _ = slot_assignments[offset]
                return cg_p.StructField(sv, slot_fields[si][0]), offset + 1
            fvs = {}
            for fname, ftype in ctype.fields:
                fvs[fname], offset = reconstruct(ftype, offset)
            return cg_p.union_struct(ctype, fvs), offset

        arm_value, _ = reconstruct(arm_ctype, 0)
        arm_sv = cg_p.StackVar(arm_ctype, _arm_unique_name(arm))
        bundle = g.OperationBundle(stack_vars=(arm_sv,), operations=(cg_o.Move(arm_sv, arm_value),))
        return bundle, _binding_resolver(self.resolver, arm, arm.type_spec)


@dataclass
class MatchExpression(e.Expression):
    """match subject\n    arm*"""
    subject: e.Expression
    arms: list[MatchArm]

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver, any], any]) -> e.Expression:
        return cast(e.Expression, replace(resolver, dataclasses.replace(self,
            subject=self.subject.search_and_replace(resolver, replace),
            arms=[arm.search_and_replace(resolver, replace) for arm in self.arms])))

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        for arm in self.arms:
            t_arm = arm.get_body_type(resolver)
            if t_arm is not None:
                return t_arm
        return None

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[e.Expression, list[s.Statement]]:
        new_subject, subj_stmts = self.subject.compile(resolver, None)
        subj_type = new_subject.get_type(resolver)
        arm_results = []
        for arm in self.arms:
            # A bound else arm receives the whole subject: its binding type
            # is the subject type, which only this level knows.
            if arm.type_spec is None and subj_type is not None:
                arm_results.append(arm.compile(_binding_resolver(resolver, arm, subj_type), expected_type))
            else:
                arm_results.append(arm.compile(resolver, expected_type))
        new_arms = [arm for arm, _ in arm_results]
        arm_stmts = [stmt for _, stmts in arm_results for stmt in stmts]
        return dataclasses.replace(self, subject=new_subject, arms=new_arms), subj_stmts + arm_stmts

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list:
        subj_type = self.subject.get_type(resolver)
        if subj_type is None:
            return []  # Not ready

        has_literal = any(arm.literal is not None for arm in self.arms)
        is_primitive_subject = (isinstance(subj_type, t.BuiltinSpec)
                                and _is_primitive_match_type(subj_type.type_name))

        # Subjects with literal arms must contain at least one primitive
        # variant (Int or String) that the literal values can match.
        if has_literal and not (is_primitive_subject or self.__subject_has_primitive(subj_type)):
            return [Error(self.line_ref,
                "literal match arms require a subject with a primitive (Int or String) variant")]

        if not has_literal and not isinstance(subj_type, (t.EnumSpec, t.CombinationSpec)):
            return [Error(self.line_ref, "match subject must be a union type"
                          + ", or use literal patterns on an Int/String subject")]

        errors = []
        for arm in self.arms:
            errors += arm.check(resolver, expected_type)
        if is_primitive_subject and subj_type.is_concrete():
            errors += self.__check_literal_arms(subj_type)
        elif subj_type.is_concrete():
            errors += self.__check_exhaustiveness(subj_type, resolver)
        return errors

    @staticmethod
    def __subject_has_primitive(subj_type: t.TypeSpec) -> bool:
        """True if subj_type is a union containing a primitive (bigint/str)."""
        if isinstance(subj_type, t.CombinationSpec):
            return any(isinstance(v, t.BuiltinSpec) and v.type_name in ("bigint", "str")
                       for v in subj_type.types)
        return False

    def __check_literal_arms(self, subj_type: t.BuiltinSpec) -> list:
        """Check literal arms: each literal's type matches subject; no duplicates;
        else arm required (Int/String are not finite)."""
        errors: list = []
        expected_kind = subj_type.type_name  # "bigint" or "str"
        seen_values: dict = {}
        else_seen = False

        for arm in self.arms:
            if else_seen:
                errors.append(Error(arm.line_ref, "unreachable arm: follows an else arm"))
                continue

            if arm.type_spec is not None:
                errors.append(Error(arm.line_ref,
                    f"type arms not allowed on a primitive ({expected_kind}) subject; use literal patterns"))
                continue

            if arm.literal is None:
                # else arm (with optional binding)
                else_seen = True
                continue

            lit = arm.literal
            if expected_kind == "str":
                if not isinstance(lit, e.StringExpression):
                    errors.append(Error(arm.line_ref,
                        f"literal arm type mismatch: expected string, got {type(lit).__name__}"))
                    continue
                key = ("str", lit.value)
            else:  # integer-like: bigint or a fixed-width int (int8..int64)
                if not isinstance(lit, e.IntegerExpression):
                    errors.append(Error(arm.line_ref,
                        f"literal arm type mismatch: expected integer, got {type(lit).__name__}"))
                    continue
                # The literal's precision must match the subject's, since there
                # is no implicit Int/Int32 coercion. A char literal is int32, so
                # it matches an Int32 subject; a bare `65` is bigint.
                if lit.precision != _match_int_precision(expected_kind):
                    errors.append(Error(arm.line_ref,
                        f"literal arm type mismatch: subject is {expected_kind}"))
                    continue
                key = ("int", lit.value)

            if key in seen_values:
                errors.append(Error(arm.line_ref,
                    f"unreachable arm: literal value already matched"))
            else:
                seen_values[key] = arm.line_ref

        if not else_seen:
            errors.append(Error(self.line_ref,
                f"non-exhaustive match; a literal-pattern match on {expected_kind} requires an else arm"))

        return errors

    def __check_exhaustiveness(self, subj_type: t.TypeSpec, resolver: g.Resolver) -> list:
        """Emit errors for non-exhaustive match and unreachable arms.

        For CombinationSpec subjects, an arm's type T covers a subject
        variant V when V is assignable to T (i.e. T is V or an ancestor of
        V). This makes interface arms on a union of implementers behave
        correctly, and flags later-arms-for-already-covered-variants as
        unreachable regardless of whether the coverage came from an exact
        match or a supertype match.
        """
        errors: list = []

        if isinstance(subj_type, t.EnumSpec):
            remaining = set(subj_type.valid_leaf_names)
            missing_name = lambda names: " | ".join(sorted(names))
        else:
            assert isinstance(subj_type, t.CombinationSpec)
            remaining = {}  # id -> (printable name, TypeSpec)
            for v in subj_type.types:
                uid = v.as_unique_id_str()
                if uid is None:
                    return []  # Subject not yet fully resolved
                remaining[uid] = (getattr(v, "name", uid), v)
            remaining_for_err = {uid: name for uid, (name, _) in remaining.items()}
            missing_name = lambda ids: " | ".join(remaining_for_err[i] for i in ids)

        else_seen = False

        def arm_covered_ids(arm_type: t.TypeSpec) -> set[str]:
            """IDs of subject variants this arm covers (handles inheritance).

            Iterates the remaining subject variants and keeps those
            assignable to arm_type via trivially_assignable_from.
            """
            if isinstance(arm_type, t.CombinationSpec):
                out: set[str] = set()
                for member in arm_type.types:
                    out |= arm_covered_ids(member)
                return out
            out = set()
            for uid, (_, v) in remaining.items():
                if arm_type.trivially_assignable_from(resolver, v) is True:
                    out.add(uid)
            return out

        for arm in self.arms:
            if else_seen:
                errors.append(Error(arm.line_ref, "unreachable arm: follows an else arm"))
                continue

            # Literal arms narrow a primitive variant but can't cover it —
            # `remaining` is unchanged. Treat them as always reachable; a
            # literal against a subject lacking that primitive variant is
            # already rejected by check().
            if arm.literal is not None:
                continue

            if arm.type_spec is None:
                # else arm
                if not remaining:
                    errors.append(Error(arm.line_ref,
                        "unreachable else arm: all variants already covered"))
                else:
                    remaining = set() if isinstance(remaining, set) else {}
                    else_seen = True
                continue

            if isinstance(subj_type, t.EnumSpec):
                if not isinstance(arm.type_spec, t.EnumSpec):
                    continue  # handled by other checks
                covers = arm.type_spec.valid_leaf_names & remaining
                if not covers:
                    errors.append(Error(arm.line_ref,
                        f"unreachable arm: leaves already covered"))
                else:
                    remaining -= covers
            else:
                covers = arm_covered_ids(arm.type_spec)
                if not covers:
                    errors.append(Error(arm.line_ref,
                        f"unreachable arm: variant not in match subject or already covered"))
                else:
                    for k in covers:
                        del remaining[k]

        if not else_seen and remaining:
            errors.append(Error(self.line_ref,
                f"non-exhaustive match; missing: {missing_name(remaining)}"))

        return errors

    def generate_to(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> g.OperationBundle:
        # All arms share one result slot, so each arm body is coerced to the
        # slot type *inside* generate (before the join Phi); nothing remains to
        # coerce afterwards.
        return self.generate(resolver, expected_type)

    def generate(self, resolver: g.Resolver, expected_type: t.TypeSpec | None = None) -> g.OperationBundle:
        subj_bundle = self.subject.generate(resolver).with_prefix("subj")
        subj_type = self.subject.get_type(resolver)
        # `result_type` is the shared slot type. A sink supplies it (the union
        # the arms widen into); otherwise the arms already agree and `get_type`
        # is exact. Each arm body is generated *to* this type (the emitter's
        # __body widens narrow arms before the join Phi).
        result_type = expected_type if expected_type is not None else self.get_type(resolver)
        result_var = cg_p.StackVar(result_type.generate(resolver), "result") if result_type else None

        em = _Emitter(self, resolver, result_type)
        em.add(subj_bundle)

        if isinstance(subj_type, t.BuiltinSpec) and _is_primitive_match_type(subj_type.type_name):
            self.__gen_primitive_match(em, subj_bundle, subj_type)
        elif isinstance(subj_type, t.EnumSpec):
            self.__gen_enum_match(em, subj_bundle, subj_type)
        else:
            assert isinstance(subj_type, t.CombinationSpec)
            target_ctype = subj_type.generate(resolver)
            discriminators = resolver.get_discriminators()
            if isinstance(target_ctype, cg_t.DataPointer):
                self.__gen_pointer_match(em, subj_bundle, subj_type, resolver)
            else:
                assert isinstance(target_ctype, cg_t.Struct)
                self.__gen_tagged_match(em, subj_bundle, subj_type, target_ctype,
                                        discriminators, resolver)
        return em.finish(result_var)

    def __else_arm(self) -> MatchArm | None:
        return next((arm for arm in self.arms
                     if arm.type_spec is None and arm.literal is None), None)

    def __gen_primitive_match(self, em: _Emitter, subj_bundle, subj_type) -> None:
        """Literal-arm match on a primitive subject: Int (bigint), String (str),
        or a fixed-width integer (int8..int64 — a char literal is int32)."""
        sv = subj_bundle.result_var
        for arm in (a for a in self.arms if a.literal is not None):
            idx = em.counter  # peek for the literal bundle prefix only
            lit_bundle = arm.literal.generate(em.resolver).with_prefix(f"lit{idx}")
            test = _literal_eq_test(subj_type.type_name, sv, lit_bundle.result_var)
            em.arm(arm, [[test]], pre=(lit_bundle,))
        em.fallback(self.__else_arm(),
                    em.bind_subject(self.__else_arm(), subj_type, sv) if self.__else_arm() else None,
                    "primitive match fell through all arms")

    def __gen_enum_match(self, em: _Emitter, subj_bundle, subj_type: t.EnumSpec) -> None:
        """EnumSpec: compare $tag for each arm, one guard per covered leaf."""
        sv = subj_bundle.result_var
        # Complex enums lower to DataPointer; the $tag field lives on the
        # heap object and is read via ObjectField. Simple (non-complex)
        # enums are flat structs and read via StructField.
        if subj_type.is_complex:
            tag = cg_p.ObjectField(cg_t._tag_type(len(subj_type.all_leaf_names)),
                                   sv, subj_type.root_name, "$tag", None)
        else:
            tag = cg_p.StructField(sv, "$tag")

        for arm in (a for a in self.arms if a.type_spec is not None):
            arm_type = arm.type_spec
            assert isinstance(arm_type, t.EnumSpec)
            guards = [cg_p.IntEqConst(tag, arm_type.all_leaf_names.index(leaf))
                      for leaf in arm_type.valid_leaf_names]
            # Bind at subj_type (always concrete), not arm.type_spec: an
            # EnumSpec built by _assign_specs never carries type_params, so
            # the generics redirect pass can leave arm_type pointing at the
            # pruned generic EnumSpec with stale all_fields. The subject's
            # fully-resolved type is the canonical type of the matched value;
            # arm.type_spec still drives the leaf guards above, where only
            # leaf identity matters.
            em.arm(arm, [guards], bind=em.bind_subject(arm, subj_type, sv))
        else_arm = self.__else_arm()
        em.fallback(else_arm,
                    em.bind_subject(else_arm, subj_type, sv) if else_arm else None,
                    "enum match fell through all arms")

    # -- pointer (DataPointer) unions ------------------------------------------

    def __gen_pointer_match(self, em: _Emitter, subj_bundle, subj_type, resolver) -> None:
        """DataPointer union dispatch.

          1. `sv == NULL` → the None arm (or a union arm covering None, via
             its own guards in source order; or the else arm when the
             subject can be None at all).
          2. Typed arms test vtable identity (`object_is_instance` semantics
             via ObjVtableEq — handles tagged-pointer and heap-vtable
             representations and walks implements_array for inheritance).
             A union-typed arm is the disjunction of its members' tests.
          3. Literal arms test the vtable kind first, then value equality.
          4. Foreign classes can't be vtable-checked from generated code
             (their symbol lives in an external library), so at most one
             foreign class per union is allowed and it acts as the implicit
             fallback alongside the else arm.
        """
        unit_type = cg_t.Struct(())
        sv = subj_bundle.result_var
        subj_has_none = any(v.generate(resolver) == unit_type for v in subj_type.types)

        def member_guard(member: t.TypeSpec) -> cg_p.RParam | None:
            """The pointer-shape test for one (non-unit) union member; None
            for foreign classes, which cannot be tested and fall through."""
            if isinstance(member, t.BuiltinSpec) and member.type_name == "bigint":
                return cg_p.ObjVtableEq(sv, extern_symbol="INTEGER_VTABLE")
            if isinstance(member, t.BuiltinSpec) and member.type_name == "str":
                return cg_p.ObjVtableEq(sv, extern_symbol="STRING_VTABLE")
            if isinstance(member, t.ClassSpec):
                if self.__class_is_foreign(resolver, member.name):
                    return None
                return cg_p.ObjVtableEq(sv, class_name=member.name)
            if isinstance(member, t.EnumSpec):
                # Complex-enum leaf: the parent enum's vtable is shared by
                # every leaf object; implements_array makes leaves match it.
                return cg_p.ObjVtableEq(sv, class_name=member.root_name)
            return None

        # Classify the arms, preserving source order for the guarded ones.
        null_arm = None
        foreign_fallback = None
        guarded: list[MatchArm] = []
        union_arm_covers_none = False
        for arm in self.arms:
            if arm.literal is not None:
                guarded.append(arm)
            elif arm.type_spec is None:
                pass  # else arm: the fallback, handled at the end
            elif arm.type_spec.generate(resolver) == unit_type:
                null_arm = arm
            elif isinstance(arm.type_spec, t.ClassSpec) and self.__class_is_foreign(resolver, arm.type_spec.name):
                foreign_fallback = arm
            else:
                if isinstance(arm.type_spec, t.CombinationSpec) and any(
                        m.generate(resolver) == unit_type for m in arm.type_spec.types):
                    union_arm_covers_none = True
                guarded.append(arm)

        else_arm = self.__else_arm()
        # NULL routes to: an explicit None arm; else a union arm covering None
        # (that arm's own null guard, in source order); else the else arm when
        # the subject can be None at all.
        null_target = (null_arm if null_arm is not None
                       else (else_arm if subj_has_none and not union_arm_covers_none else None))
        if null_target is not None:
            em.arm(null_target, [[cg_p.IntEqConst(sv, 0)]],
                   bind=em.bind_subject(null_target,
                                        null_target.type_spec or subj_type, sv))

        for arm in guarded:
            if arm.literal is not None:
                self.__pointer_literal_arm(em, arm, sv, resolver)
            elif isinstance(arm.type_spec, t.CombinationSpec):
                # Union-typed arm: one body guarded by the OR of its members'
                # tests; a unit member contributes the NULL test (and claimed
                # NULL routing above, so the else arm doesn't steal it).
                guards = []
                for member in arm.type_spec.types:
                    if member.generate(resolver) == unit_type:
                        guards.append(cg_p.IntEqConst(sv, 0))
                    else:
                        guard = member_guard(member)
                        if guard is not None:
                            guards.append(guard)
                em.arm(arm, [guards], bind=em.bind_subject(arm, arm.type_spec, sv))
            else:
                guard = member_guard(arm.type_spec)
                if guard is None:
                    continue  # untestable arm kind; check() rejects these
                em.arm(arm, [[guard]], bind=em.bind_subject(arm, arm.type_spec, sv))

        final_fallback = foreign_fallback if foreign_fallback is not None else else_arm
        em.fallback(final_fallback,
                    em.bind_subject(final_fallback,
                                    final_fallback.type_spec or subj_type, sv)
                    if final_fallback else None,
                    "pointer-union match fell through all arms")

    def __pointer_literal_arm(self, em: _Emitter, arm: MatchArm, sv, resolver) -> None:
        """A literal arm on a pointer union: two guard stages — is the subject
        the literal's primitive kind at all, then does the value match. The
        AST type selects the comparison (earlier passes rewrite literals to
        global refs, so the codegen type is DataPointer for both kinds)."""
        lit_ast_type = arm.literal.get_type(resolver)
        if not isinstance(lit_ast_type, t.BuiltinSpec):
            return  # unreachable — check() already validated
        if lit_ast_type.type_name == "str":
            kind_guard = cg_p.ObjVtableEq(sv, extern_symbol="STRING_VTABLE")
        elif lit_ast_type.type_name == "bigint":
            kind_guard = cg_p.ObjVtableEq(sv, extern_symbol="INTEGER_VTABLE")
        else:
            return  # unreachable — check() already validated
        lit_bundle = arm.literal.generate(resolver).with_prefix(f"lit{em.counter}")
        value_test = _literal_eq_test(lit_ast_type.type_name, sv, lit_bundle.result_var)
        em.arm(arm, [[kind_guard], [value_test]], pre=(lit_bundle,))

    def __class_is_foreign(self, resolver: g.Resolver, class_name: str) -> bool:
        """Return True if the named class is declared `[foreign]` — its
        vtable symbol lives in an external library, so we can't emit a
        vtable-identity check against it."""
        classes = resolver.find_type(class_name)
        for resolved in classes:
            stmt = resolved.statement
            if isinstance(stmt, s.ClassStatement) and "foreign" in stmt.attributes:
                return True
        return False

    # -- tagged (Struct) unions -------------------------------------------------

    def __gen_tagged_match(self, em: _Emitter, subj_bundle, subj_type, container,
                           discriminators, resolver) -> None:
        """Tagged-union Struct: compare $tag for each typed arm; literal arms
        first guard the $tag of the variant the literal belongs to, then
        compare the value extracted from its slot; union-typed arms enter on
        any member's tag and bind the value narrowed for that member."""
        sv = subj_bundle.result_var
        tag = cg_p.StructField(sv, "$tag")
        variant_types = [v.generate(resolver) for v in subj_type.types]
        _, variant_map = cg_t.compute_union_slots(variant_types)
        slot_fields = container.fields

        def variant_index(uid: str | None) -> int | None:
            if uid is None:
                return None
            return next((i for i, v in enumerate(subj_type.types)
                         if v.as_unique_id_str() == uid), None)

        for arm in self.arms:
            if arm.type_spec is None and arm.literal is None:
                continue  # else arm: the fallback, handled at the end

            if arm.literal is not None:
                lit_ast_type = arm.literal.get_type(resolver)
                lit_type_name = lit_ast_type.type_name if isinstance(lit_ast_type, t.BuiltinSpec) else None
                vi = next((i for i, v in enumerate(subj_type.types)
                           if isinstance(v, t.BuiltinSpec) and v.type_name == lit_type_name), None)
                if vi is None:
                    continue  # check() prevents this; skip to be safe
                tag_value = discriminators.get(subj_type.types[vi].as_unique_id_str(), 0)
                si, _ = variant_map[vi][0]
                slot_val = cg_p.StructField(sv, slot_fields[si][0])
                lit_bundle = arm.literal.generate(resolver).with_prefix(f"lit{em.counter}")
                em.arm(arm,
                       [[cg_p.IntEqConst(tag, tag_value)],
                        [_literal_eq_test(lit_type_name, slot_val, lit_bundle.result_var)]],
                       pre=(lit_bundle,))

            elif isinstance(arm.type_spec, t.CombinationSpec):
                # Union-typed arm, e.g. `(w: Word|None)` over Word|None|IOError.
                # Discriminator ids are GLOBAL per leaf type, so each member's
                # tag test is the same constant it has in the wide union; the
                # bound value is the NARROWED representation, rebuilt from the
                # wide slots (tags carry over unchanged for the same reason).
                narrow_ctype = arm.type_spec.generate(resolver)
                narrow_map = None
                if isinstance(narrow_ctype, cg_t.Struct):
                    _, narrow_map = cg_t.compute_union_slots(
                        [m.generate(resolver) for m in arm.type_spec.types])

                entries: list[tuple[cg_p.RParam, cg_p.RParam]] = []
                for k, member in enumerate(arm.type_spec.types):
                    uid = member.as_unique_id_str()
                    vi = variant_index(uid)
                    if vi is None or uid not in discriminators:
                        continue  # check() validated coverage; skip defensively
                    member_tag = discriminators[uid]
                    if narrow_map is None:
                        # DataPointer narrow union: NULL for the unit member,
                        # else the member's single pointer slot.
                        if member.generate(resolver) == cg_t.Struct(()):
                            value: cg_p.RParam = cg_p.NullPointer()
                        else:
                            wsi, _ = variant_map[vi][0]
                            value = cg_p.StructField(sv, slot_fields[wsi][0])
                    else:
                        fields = {"$tag": cg_p.Integer(member_tag, 32)}
                        for (nsi, _nt), (wsi, _wt) in zip(narrow_map[k], variant_map[vi]):
                            fields[narrow_ctype.fields[nsi][0]] = cg_p.StructField(sv, slot_fields[wsi][0])
                        value = cg_p.union_struct(narrow_ctype, fields)
                    entries.append((cg_p.IntEqConst(tag, member_tag), value))
                em.multi_entry_arm(arm, entries, narrow_ctype)

            else:
                arm_ctype = arm.type_spec.generate(resolver)
                tag_value = discriminators.get(arm.type_spec.as_unique_id_str(), 0)
                vi = next((i for i, vt in enumerate(variant_types) if vt == arm_ctype), None)
                bind = (em.bind_from_slots(arm, arm_ctype, variant_map[vi], slot_fields, sv)
                        if vi is not None else None)
                em.arm(arm, [[cg_p.IntEqConst(tag, tag_value)]], bind=bind)

        else_arm = self.__else_arm()
        em.fallback(else_arm,
                    em.bind_subject(else_arm, subj_type, sv) if else_arm else None,
                    "tagged-union match fell through all arms")
