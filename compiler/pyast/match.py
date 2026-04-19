"""MatchArm and MatchExpression — pattern matching on union types."""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
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

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver, any], any]) -> MatchArm:
        nested_resolver = g.ResolverData(resolver, self.__find_bound) if self.name and self.name != "_" else resolver
        new_body = self.body.search_and_replace(nested_resolver, replace)
        new_type = self.type_spec.search_and_replace(resolver, replace) if self.type_spec else None
        new_literal = self.literal.search_and_replace(resolver, replace) if self.literal else None
        return dataclasses.replace(self, type_spec=new_type, body=new_body, literal=new_literal)

    def __find_bound(self, names: set[str]) -> list[g.Resolved[s.DataStatement]]:
        if self.name and self.name != "_" and self.type_spec and g.match_names(self.name, names):
            let = s.LetStatement(self.line_ref, self.name, None, {}, (), None, self.type_spec)
            return [g.Resolved(self.name, let, g.ResolvedScope.LOCAL)]
        return []

    def compile(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> tuple[MatchArm, list[s.Statement]]:
        nested_resolver = g.ResolverData(resolver, self.__find_bound) if self.name and self.name != "_" else resolver
        new_body, body_stmts = self.body.compile(nested_resolver, func_ret_type)
        new_type, type_stmts = self.type_spec.compile(resolver) if self.type_spec else (None, [])
        new_literal, lit_stmts = self.literal.compile(resolver, None) if self.literal else (None, [])
        return dataclasses.replace(self, type_spec=new_type, body=new_body, literal=new_literal), body_stmts + type_stmts + lit_stmts

    def get_body_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        nested_resolver = g.ResolverData(resolver, self.__find_bound) if self.name and self.name != "_" else resolver
        return self.body.get_type(nested_resolver)

    def check(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> list:
        nested_resolver = g.ResolverData(resolver, self.__find_bound) if self.name and self.name != "_" else resolver
        type_err = self.type_spec.check(resolver) if self.type_spec else []
        body_err = self.body.check(nested_resolver, func_ret_type)
        literal_err = self.literal.check(resolver, None) if self.literal else []
        return type_err + body_err + literal_err


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
            if arm.type_spec is None and arm.name and arm.name != "_" and subj_type is not None:
                def find_else(names, a=arm, st=subj_type):
                    if g.match_names(a.name, names):
                        let = s.LetStatement(a.line_ref, a.name, None, {}, (), None, st)
                        return [g.Resolved(a.name, let, g.ResolvedScope.LOCAL)]
                    return []
                arm_results.append(arm.compile(g.ResolverData(resolver, find_else), expected_type))
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
                                and subj_type.type_name in ("bigint", "str"))

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
            if expected_kind == "bigint":
                if not isinstance(lit, e.IntegerExpression):
                    errors.append(Error(arm.line_ref,
                        f"literal arm type mismatch: expected integer, got {type(lit).__name__}"))
                    continue
                key = ("int", lit.value)
            else:  # "str"
                if not isinstance(lit, e.StringExpression):
                    errors.append(Error(arm.line_ref,
                        f"literal arm type mismatch: expected string, got {type(lit).__name__}"))
                    continue
                key = ("str", lit.value)

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
                    if isinstance(remaining, set):
                        remaining = set()
                    else:
                        remaining = {}
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

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        subj_bundle = self.subject.generate(resolver).rename_vars("s")
        subj_type = self.subject.get_type(resolver)
        result_type = self.get_type(resolver)
        result_var = cg_p.StackVar(result_type.generate(), "result") if result_type else None

        if isinstance(subj_type, t.BuiltinSpec) and subj_type.type_name in ("bigint", "str"):
            return self.__gen_primitive_match(resolver, subj_bundle, subj_type, result_var)

        if isinstance(subj_type, t.EnumSpec):
            return self.__gen_enum_match(resolver, subj_bundle, subj_type, result_var)

        assert isinstance(subj_type, t.CombinationSpec)
        target_ctype = subj_type.generate()

        discriminators = resolver.get_discriminators()

        # DataPointer union: null check for unit variant, pass through for pointer
        if isinstance(target_ctype, cg_t.DataPointer):
            return self.__gen_pointer_match(resolver, subj_bundle, subj_type, result_var, discriminators)

        # UnionContainer: tag comparison
        assert isinstance(target_ctype, cg_t.UnionContainer)
        return self.__gen_tagged_match(resolver, subj_bundle, subj_type, target_ctype, result_var, discriminators)

    def __emit_arm_body(self, arm: MatchArm, arm_resolver: g.Resolver, suffix: str,
                        result_var: cg_p.StackVar | None, bundles: list) -> None:
        """Generate arm body, append it to bundles, and store its result into result_var if present."""
        body_bundle = arm.body.generate(arm_resolver).rename_vars(suffix)
        bundles.append(body_bundle)
        if result_var:
            bundles.append(g.OperationBundle(operations=(cg_o.Move(result_var, body_bundle.result_var),)))

    def __bind_arm_var(self, arm: MatchArm, arm_ctype, slot_assignments, slot_fields,
                       sv: cg_p.RParam, resolver: g.Resolver, bundles: list) -> g.Resolver:
        """Emit ops to bind arm.name to the matched variant value; return the extended resolver.

        slot_assignments is variant_map[var_idx]: a list of (slot_index, orig_type) pairs,
        one per primitive in this variant.  For a single-primitive variant the bound variable
        is loaded from its one union slot.  For a multi-primitive (struct) variant each field
        is loaded from its corresponding slot and the struct is reconstructed with NewStruct.
        """
        def make_resolver(arm_=arm):
            def find(names):
                if g.match_names(arm_.name, names):
                    let = s.LetStatement(arm_.line_ref, arm_.name, None, {}, (), None, arm_.type_spec)
                    return [g.Resolved(arm_.name, let, g.ResolvedScope.LOCAL)]
                return []
            return g.ResolverData(resolver, find)

        prims = cg_t._flatten_primitives(arm_ctype)
        arm_sv = cg_p.StackVar(arm_ctype, arm.name)

        if len(prims) == 1:
            si, _ = slot_assignments[0]
            slot_value = cg_p.StructField(sv, slot_fields[si][0])
            if isinstance(arm_ctype, cg_t.Struct):
                field_name = arm_ctype.fields[0][0]
                arm_value = cg_p.NewStruct(((field_name, slot_value),))
            else:
                arm_value = slot_value
            bundles.append(g.OperationBundle(stack_vars=(arm_sv,),
                                             operations=(cg_o.Move(arm_sv, arm_value),)))
        else:
            assert isinstance(arm_ctype, cg_t.Struct), f"Multi-primitive non-struct arm type {arm_ctype}"
            field_values: list[tuple[str, cg_p.RParam]] = []
            for prim_idx, (field_name, field_type) in enumerate(arm_ctype.fields):
                assert len(cg_t._flatten_primitives(field_type)) == 1, \
                    f"Nested multi-primitive field in match arm not yet supported"
                si, _ = slot_assignments[prim_idx]
                field_values.append((field_name, cg_p.StructField(sv, slot_fields[si][0])))
            bundles.append(g.OperationBundle(stack_vars=(arm_sv,),
                                             operations=(cg_o.Move(arm_sv, cg_p.NewStruct(tuple(field_values))),)))
        return make_resolver()

    def __gen_primitive_match(self, resolver, subj_bundle, subj_type, result_var):
        """Literal-arm match on a primitive (Int = bigint, String = str) subject."""
        is_bigint = subj_type.type_name == "bigint"
        sv = subj_bundle.result_var
        end_label = "match_end"
        stack_vars = (result_var,) if result_var else ()
        bundles = [subj_bundle]

        literal_arms = [arm for arm in self.arms if arm.literal is not None]
        else_arm = next((arm for arm in self.arms
                         if arm.literal is None and arm.type_spec is None), None)

        for i, arm in enumerate(literal_arms):
            arm_label = f"match_arm_{i}"
            next_label = f"match_next_{i}"

            lit_bundle = arm.literal.generate(resolver).rename_vars(f"l{i}")
            bundles.append(lit_bundle)

            args = cg_p.NewStruct((("a", sv), ("b", lit_bundle.result_var)))
            if is_bigint:
                test_expr = cg_p.Invoke("integer_test_eq", args, cg_t.Int(8))
            else:
                cmp_expr = cg_p.Invoke("string_compare", args, cg_t.Int(32))
                test_expr = cg_p.IntEqConst(cmp_expr, 0)

            bundles.append(g.OperationBundle(operations=(cg_o.JumpIf(arm_label, test_expr),)))
            bundles.append(g.OperationBundle(operations=(cg_o.Jump(next_label),)))
            bundles.append(g.OperationBundle(operations=(cg_o.Label(arm_label),)))

            arm_local = []
            self.__emit_arm_body(arm, resolver, f"a{i}", result_var, arm_local)
            if arm_local:
                bundles.append(reduce(lambda a, b: a + b, arm_local).rename_vars(f"arm{i}_"))
            bundles.append(g.OperationBundle(operations=(cg_o.Jump(end_label),)))
            bundles.append(g.OperationBundle(operations=(cg_o.Label(next_label),)))

        if else_arm is not None:
            else_local = []
            else_resolver = resolver
            if else_arm.name and else_arm.name != "_":
                else_sv = cg_p.StackVar(subj_type.generate(), else_arm.name)
                def find_else(names, arm=else_arm, st=subj_type):
                    if g.match_names(arm.name, names):
                        let = s.LetStatement(arm.line_ref, arm.name, None, {}, (), None, st)
                        return [g.Resolved(arm.name, let, g.ResolvedScope.LOCAL)]
                    return []
                else_resolver = g.ResolverData(resolver, find_else)
                else_local.append(g.OperationBundle(stack_vars=(else_sv,),
                                                    operations=(cg_o.Move(else_sv, sv),)))
            self.__emit_arm_body(else_arm, else_resolver, "el", result_var, else_local)
            if else_local:
                bundles.append(reduce(lambda a, b: a + b, else_local).rename_vars("else_"))

        bundles.append(g.OperationBundle(stack_vars=stack_vars,
                                         operations=(cg_o.Label(end_label),), result_var=result_var))
        return reduce(lambda a, b: a + b, bundles).rename_vars("")

    def __gen_pointer_match(self, resolver, subj_bundle, subj_type, result_var, discriminators):
        """DataPointer union dispatch.

        Generates:
          1. `sv == NULL` → null arm (or else arm if the subject has a unit
             variant but no explicit typed one).
          2. For each typed arm (Int, Str, class), a call to libyafl's
             `object_is_instance(sv, target_vtable)` which handles both
             tagged-pointer and heap-vtable representations and walks the
             implements_array for inheritance.
          3. Foreign classes can't be vtable-checked from generated code
             (their symbol lives in an external library and the compiler
             doesn't know the C name), so at most one foreign class per
             union is allowed and it acts as the implicit fallback —
             whatever didn't match any prior `is_instance` check falls
             through to it.
          4. If no foreign class, the else arm catches the remainder.
        """
        unit_type = cg_t.Struct(())
        sv         = subj_bundle.result_var
        stack_vars = (result_var,) if result_var else ()
        end_label  = "match_end"

        subj_has_none = any(v.generate() == unit_type for v in subj_type.types)

        null_arm = None
        else_arm = None
        foreign_fallback = None
        # arm_steps preserves source order, emits interleaved with typed tests.
        # Each entry: ("literal", arm) | ("typed", arm, test_expr, suffix)
        arm_steps: list[tuple] = []
        for arm in self.arms:
            if arm.literal is not None:
                arm_steps.append(("literal", arm))
                continue
            if arm.type_spec is None:
                else_arm = arm
                continue
            arm_ctype = arm.type_spec.generate()
            if arm_ctype == unit_type:
                null_arm = arm
                continue
            if isinstance(arm_ctype, cg_t.Int) and arm_ctype.precision == 0:
                arm_steps.append(
                    ("typed", arm,
                     cg_p.ObjVtableEq(sv, extern_symbol="INTEGER_VTABLE"), "int"))
            elif isinstance(arm_ctype, cg_t.Str):
                arm_steps.append(
                    ("typed", arm,
                     cg_p.ObjVtableEq(sv, extern_symbol="STRING_VTABLE"), "str"))
            elif isinstance(arm.type_spec, t.ClassSpec):
                if self.__class_is_foreign(resolver, arm.type_spec.name):
                    foreign_fallback = arm
                else:
                    arm_steps.append(
                        ("typed", arm,
                         cg_p.ObjVtableEq(sv, class_name=arm.type_spec.name),
                         f"cls{len(arm_steps)}"))

        null_target = null_arm if null_arm is not None else (else_arm if subj_has_none else None)
        final_fallback = foreign_fallback if foreign_fallback is not None else else_arm

        bundles: list = [subj_bundle]
        next_counter = [0]

        def emit_test(target_arm, test_expr, suffix: str,
                      extra_bundles_before_test=()) -> None:
            idx = next_counter[0]
            next_counter[0] = idx + 1
            arm_label = f"match_{suffix}_{idx}"
            next_label = f"match_next_{idx}"
            for eb in extra_bundles_before_test:
                bundles.append(eb)
            bundles.append(g.OperationBundle(operations=(cg_o.JumpIf(arm_label, test_expr),)))
            bundles.append(g.OperationBundle(operations=(cg_o.Jump(next_label),)))
            bundles.append(g.OperationBundle(operations=(cg_o.Label(arm_label),)))
            self.__emit_pointer_arm_body(target_arm, sv, resolver, suffix, result_var, bundles)
            bundles.append(g.OperationBundle(operations=(cg_o.Jump(end_label),)))
            bundles.append(g.OperationBundle(operations=(cg_o.Label(next_label),)))

        if null_target is not None:
            emit_test(null_target, cg_p.IntEqConst(sv, 0), "null")
        for step in arm_steps:
            if step[0] == "typed":
                _, arm, test_expr, suffix = step
                emit_test(arm, test_expr, suffix)
            else:
                _, arm = step
                lit = arm.literal
                idx = next_counter[0]
                next_counter[0] = idx + 1
                lit_bundle = lit.generate(resolver).rename_vars(f"lit{idx}")
                arm_label  = f"match_lit_{idx}"
                next_label = f"match_next_{idx}"
                check_label = f"match_litchk_{idx}"
                # Dispatch on the generated C type of the literal value, not
                # the parse-time AST class — earlier passes rewrite string and
                # integer literals into NamedExpression references to globals.
                lit_ctype = lit_bundle.result_var.get_type()
                if isinstance(lit_ctype, cg_t.Str):
                    guard = cg_p.ObjVtableEq(sv, extern_symbol="STRING_VTABLE")
                    args  = cg_p.NewStruct((("a", sv), ("b", lit_bundle.result_var)))
                    cmp   = cg_p.Invoke("string_compare", args, cg_t.Int(32))
                    test_expr = cg_p.IntEqConst(cmp, 0)
                elif isinstance(lit_ctype, cg_t.Int) and lit_ctype.precision == 0:
                    guard = cg_p.ObjVtableEq(sv, extern_symbol="INTEGER_VTABLE")
                    args  = cg_p.NewStruct((("a", sv), ("b", lit_bundle.result_var)))
                    test_expr = cg_p.Invoke("integer_test_eq", args, cg_t.Int(8))
                else:
                    continue  # unreachable — check() already validated
                bundles.append(lit_bundle)
                # if (is_primitive) goto check_label; else goto next_label
                bundles.append(g.OperationBundle(operations=(cg_o.JumpIf(check_label, guard),)))
                bundles.append(g.OperationBundle(operations=(cg_o.Jump(next_label),)))
                bundles.append(g.OperationBundle(operations=(cg_o.Label(check_label),)))
                # if (value == literal) goto arm_label; else goto next_label
                bundles.append(g.OperationBundle(operations=(cg_o.JumpIf(arm_label, test_expr),)))
                bundles.append(g.OperationBundle(operations=(cg_o.Jump(next_label),)))
                bundles.append(g.OperationBundle(operations=(cg_o.Label(arm_label),)))
                self.__emit_pointer_arm_body(arm, sv, resolver, f"lit{idx}", result_var, bundles)
                bundles.append(g.OperationBundle(operations=(cg_o.Jump(end_label),)))
                bundles.append(g.OperationBundle(operations=(cg_o.Label(next_label),)))

        if final_fallback is not None:
            self.__emit_pointer_arm_body(final_fallback, sv, resolver, "fb",
                                         result_var, bundles)

        bundles.append(g.OperationBundle(stack_vars=stack_vars,
                                         operations=(cg_o.Label(end_label),), result_var=result_var))
        return reduce(lambda a, b: a + b, bundles).rename_vars("")

    def __class_is_foreign(self, resolver: g.Resolver, class_name: str) -> bool:
        """Return True if the named class is declared `[foreign]` — its
        vtable symbol lives in an external library, so we can't emit a
        vtable-identity check against it."""
        classes = resolver.find_type({class_name})
        for resolved in classes:
            stmt = resolved.statement
            if isinstance(stmt, s.ClassStatement) and "foreign" in stmt.attributes:
                return True
        return False

    def __emit_pointer_arm_body(self, arm, sv, resolver, suffix, result_var, bundles):
        """Bind the arm's name (if any) to the subject pointer and emit the body."""
        arm_resolver = resolver
        arm_local = []
        if arm.name and arm.name != "_":
            type_for_binding = arm.type_spec if arm.type_spec is not None else None
            bound_sv = cg_p.StackVar(cg_t.DataPointer(), arm.name)
            def find_bound(names, a=arm, t_spec=type_for_binding):
                if g.match_names(a.name, names):
                    # For an else arm there's no arm.type_spec; caller's
                    # compile() already substituted the subject type into
                    # the body resolver, so this local lookup uses
                    # whatever type_spec the arm carries.
                    let = s.LetStatement(a.line_ref, a.name, None, {}, (), None, t_spec)
                    return [g.Resolved(a.name, let, g.ResolvedScope.LOCAL)]
                return []
            arm_resolver = g.ResolverData(resolver, find_bound)
            arm_local.append(g.OperationBundle(stack_vars=(bound_sv,),
                                               operations=(cg_o.Move(bound_sv, sv),)))
        self.__emit_arm_body(arm, arm_resolver, suffix, result_var, arm_local)
        if arm_local:
            bundles.append(reduce(lambda a, b: a + b, arm_local).rename_vars(f"{suffix}_"))

    def __gen_tagged_match(self, resolver, subj_bundle, subj_type, container, result_var, discriminators):
        """UnionContainer union: compare $tag for each typed arm; for literal
        arms, first test the $tag matches the variant the literal belongs to,
        then extract the primitive from its slot and compare to the literal
        value."""
        sv         = subj_bundle.result_var
        tag_field  = cg_p.StructField(sv, "$tag")
        stack_vars = (result_var,) if result_var else ()
        end_label  = "match_end"

        variant_types = [v.generate() for v in subj_type.types]
        _, variant_map = cg_t.UnionContainer.compute(variant_types)
        slot_fields = container.slots

        bundles  = [subj_bundle]
        else_arm = next((arm for arm in self.arms
                         if arm.type_spec is None and arm.literal is None), None)

        # For literal arms, find the variant that holds the matching primitive
        # so we can extract sv.$s{slot} and compare. bigint → Int variant,
        # str → Str variant.
        def primitive_variant_info(lit_ctype):
            for vi, vt in enumerate(variant_types):
                if (isinstance(lit_ctype, cg_t.Int) and lit_ctype.precision == 0
                        and isinstance(vt, cg_t.Int) and vt.precision == 0):
                    return vi, vt
                if isinstance(lit_ctype, cg_t.Str) and isinstance(vt, cg_t.Str):
                    return vi, vt
            return None, None

        arm_index = 0
        for arm in self.arms:
            if arm.type_spec is None and arm.literal is None:
                continue  # else arm handled after the loop

            arm_label  = f"match_arm_{arm_index}"
            next_label = f"match_next_{arm_index}"

            if arm.literal is not None:
                lit_bundle = arm.literal.generate(resolver).rename_vars(f"lit{arm_index}")
                lit_ctype = lit_bundle.result_var.get_type()
                var_idx, _ = primitive_variant_info(lit_ctype)
                if var_idx is None:
                    arm_index += 1
                    continue  # check() prevents this; skip to be safe
                tag_value = discriminators.get(subj_type.types[var_idx].as_unique_id_str(), 0)
                # Extract the primitive from its slot.
                si, _orig = variant_map[var_idx][0]
                slot_val = cg_p.StructField(sv, slot_fields[si][0])
                check_label = f"match_litchk_{arm_index}"
                bundles.append(lit_bundle)
                # Tag guard: only proceed if $tag selects the primitive variant.
                bundles.append(g.OperationBundle(operations=(
                    cg_o.JumpIf(check_label, cg_p.IntEqConst(tag_field, tag_value)),)))
                bundles.append(g.OperationBundle(operations=(cg_o.Jump(next_label),)))
                bundles.append(g.OperationBundle(operations=(cg_o.Label(check_label),)))
                # Value test.
                args = cg_p.NewStruct((("a", slot_val), ("b", lit_bundle.result_var)))
                if isinstance(lit_ctype, cg_t.Str):
                    cmp = cg_p.Invoke("string_compare", args, cg_t.Int(32))
                    test_expr = cg_p.IntEqConst(cmp, 0)
                else:
                    test_expr = cg_p.Invoke("integer_test_eq", args, cg_t.Int(8))
                bundles.append(g.OperationBundle(operations=(cg_o.JumpIf(arm_label, test_expr),)))
                bundles.append(g.OperationBundle(operations=(cg_o.Jump(next_label),)))
                bundles.append(g.OperationBundle(operations=(cg_o.Label(arm_label),)))
                arm_local = []
                self.__emit_arm_body(arm, resolver, f"lit{arm_index}", result_var, arm_local)
                if arm_local:
                    bundles.append(reduce(lambda a, b: a + b, arm_local).rename_vars(f"lit{arm_index}_"))
                bundles.append(g.OperationBundle(operations=(cg_o.Jump(end_label),)))
                bundles.append(g.OperationBundle(operations=(cg_o.Label(next_label),)))
                arm_index += 1
                continue

            # Typed arm — original path.
            arm_ctype  = arm.type_spec.generate()
            tag_value  = discriminators.get(arm.type_spec.as_unique_id_str(), 0)

            bundles.append(g.OperationBundle(operations=(cg_o.JumpIf(arm_label, cg_p.IntEqConst(tag_field, tag_value)),)))
            bundles.append(g.OperationBundle(operations=(cg_o.Jump(next_label),)))
            bundles.append(g.OperationBundle(operations=(cg_o.Label(arm_label),)))

            arm_local = []
            arm_resolver = resolver
            if arm.name and arm.name != "_":
                var_idx = next((idx for idx, vt in enumerate(variant_types) if vt == arm_ctype), None)
                if var_idx is not None:
                    arm_resolver = self.__bind_arm_var(
                        arm, arm_ctype, variant_map[var_idx], slot_fields, sv, resolver, arm_local)

            self.__emit_arm_body(arm, arm_resolver, f"a{arm_index}", result_var, arm_local)
            if arm_local:
                bundles.append(reduce(lambda a, b: a + b, arm_local).rename_vars(f"arm{arm_index}_"))
            bundles.append(g.OperationBundle(operations=(cg_o.Jump(end_label),)))
            bundles.append(g.OperationBundle(operations=(cg_o.Label(next_label),)))
            arm_index += 1

        if else_arm:
            else_local = []
            else_resolver = resolver
            if else_arm.name and else_arm.name != "_":
                else_sv = cg_p.StackVar(subj_type.generate(), else_arm.name)
                def find_else(names, arm=else_arm):
                    if g.match_names(arm.name, names):
                        let = s.LetStatement(arm.line_ref, arm.name, None, {}, (), None, arm.type_spec or subj_type)
                        return [g.Resolved(arm.name, let, g.ResolvedScope.LOCAL)]
                    return []
                else_resolver = g.ResolverData(resolver, find_else)
                else_local.append(g.OperationBundle(stack_vars=(else_sv,), operations=(cg_o.Move(else_sv, sv),)))
            self.__emit_arm_body(else_arm, else_resolver, "el", result_var, else_local)
            if else_local:
                bundles.append(reduce(lambda a, b: a + b, else_local).rename_vars("else_"))

        bundles.append(g.OperationBundle(stack_vars=stack_vars,
                                         operations=(cg_o.Label(end_label),), result_var=result_var))
        return reduce(lambda a, b: a + b, bundles).rename_vars("")

    def __gen_enum_match(self, resolver, subj_bundle, subj_type: t.EnumSpec, result_var):
        """EnumSpec: compare $tag for each arm using discriminator indices from the EnumSpec."""
        sv = subj_bundle.result_var
        tag_sv = cg_p.StructField(sv, "$tag")
        stack_vars = (result_var,) if result_var else ()
        end_label = "match_end"
        bundles = [subj_bundle]
        else_arm = next((arm for arm in self.arms if arm.type_spec is None), None)

        for i, arm in enumerate(arm for arm in self.arms if arm.type_spec is not None):
            arm_type = arm.type_spec
            assert isinstance(arm_type, t.EnumSpec)
            arm_label = f"match_arm_{i}"
            next_label = f"match_next_{i}"

            for leaf_name in arm_type.valid_leaf_names:
                leaf_idx = arm_type.all_leaf_names.index(leaf_name)
                bundles.append(g.OperationBundle(operations=(
                    cg_o.JumpIf(arm_label, cg_p.IntEqConst(tag_sv, leaf_idx)),)))
            bundles.append(g.OperationBundle(operations=(cg_o.Jump(next_label),)))
            bundles.append(g.OperationBundle(operations=(cg_o.Label(arm_label),)))

            arm_local = []
            arm_resolver = resolver
            if arm.name and arm.name != "_":
                arm_sv = cg_p.StackVar(arm_type.generate(), arm.name)
                def find_arm(names, arm=arm):
                    if g.match_names(arm.name, names):
                        let = s.LetStatement(arm.line_ref, arm.name, None, {}, (), None, arm.type_spec)
                        return [g.Resolved(arm.name, let, g.ResolvedScope.LOCAL)]
                    return []
                arm_resolver = g.ResolverData(resolver, find_arm)
                arm_local.append(g.OperationBundle(stack_vars=(arm_sv,), operations=(cg_o.Move(arm_sv, sv),)))

            self.__emit_arm_body(arm, arm_resolver, f"a{i}", result_var, arm_local)
            if arm_local:
                bundles.append(reduce(lambda a, b: a + b, arm_local).rename_vars(f"arm{i}_"))
            bundles.append(g.OperationBundle(operations=(cg_o.Jump(end_label),)))
            bundles.append(g.OperationBundle(operations=(cg_o.Label(next_label),)))

        if else_arm:
            else_local = []
            else_resolver = resolver
            if else_arm.name and else_arm.name != "_":
                else_sv = cg_p.StackVar(subj_type.generate(), else_arm.name)
                def find_else(names, arm=else_arm):
                    if g.match_names(arm.name, names):
                        let = s.LetStatement(arm.line_ref, arm.name, None, {}, (), None, arm.type_spec or subj_type)
                        return [g.Resolved(arm.name, let, g.ResolvedScope.LOCAL)]
                    return []
                else_resolver = g.ResolverData(resolver, find_else)
                else_local.append(g.OperationBundle(stack_vars=(else_sv,), operations=(cg_o.Move(else_sv, sv),)))
            self.__emit_arm_body(else_arm, else_resolver, "el", result_var, else_local)
            if else_local:
                bundles.append(reduce(lambda a, b: a + b, else_local).rename_vars("else_"))

        bundles.append(g.OperationBundle(stack_vars=stack_vars,
                                         operations=(cg_o.Label(end_label),), result_var=result_var))
        return reduce(lambda a, b: a + b, bundles).rename_vars("")
