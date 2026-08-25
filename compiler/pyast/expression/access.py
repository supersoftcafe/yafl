from __future__ import annotations

from typing import Callable, Any
import dataclasses
import pyast.rewrite as rw
from dataclasses import dataclass, field
from functools import reduce

from langtools import checked_cast
from parsing.tokenizer import LineRef
from parsing.parselib import Error

import codegen.ops as cg_o
import codegen.param as cg_p
import codegen.typedecl as cg_t

import pyast.resolver as g
import pyast.statement as s
import pyast.typespec as t
import pyast.utils as u
from pyast import inference, union_repr
from pyast.expression.base import Expression
from pyast.expression.literal import StringExpression
from pyast.expression.tuple_expr import TupleExpression


def _foreign_symbol(stmt: s.FunctionStatement) -> str | None:
    """Return the C symbol name if stmt has [foreign("symbol")], else None."""
    foreign_attr = stmt.attributes.get("foreign")
    if (isinstance(foreign_attr, TupleExpression)
            and len(foreign_attr.expressions) == 1
            and isinstance(foreign_attr.expressions[0].value, StringExpression)):
        return foreign_attr.expressions[0].value.value
    return None



def _is_impure(stmt: s.FunctionStatement) -> bool:
    """Return True if stmt has the [impure] attribute."""
    return "impure" in stmt.attributes



def _is_sync(stmt: s.FunctionStatement) -> bool:
    """Return True if stmt has the [sync] attribute."""
    return "sync" in stmt.attributes


def _enum_fields(resolver: g.Resolver, espec: "t.EnumSpec"):
    """The enum's fields for member resolution — DERIVED from the statement
    when it is reachable (identity vs state: the statement is the current
    truth), falling back to the stored copy only until the stored field is
    removed. Fields are template-shaped either way; the caller substitutes
    type params on read."""
    found = resolver.find_type(espec.root_name)
    if len(found) == 1:
        stmt = found[0].statement
        if hasattr(stmt, "derive_all_fields"):
            return resolver.get_enum_fields(stmt)
    return ()   # unreachable root (pruned): no fields to resolve against


def _substitute_class_type_params(
        resolver: g.Resolver,
        receiver: t.ClassSpec,
        cdecl: s.ClassStatement,
        field_type: t.TypeSpec | None,
) -> t.TypeSpec | None:
    # Map the class's declared placeholders to the receiver's concrete
    # type arguments and rewrite placeholders inside the field's declared
    # type. Mirrors the parent-class substitution in ClassStatement.compile
    # so that e.g. `b: Box<Int>` → `b.value: Int` (not the bare `T`).
    if field_type is None or not cdecl.type_params or not receiver.type_params:
        return field_type
    mapping = {p.name: concrete for p, concrete in zip(cdecl.type_params, receiver.type_params)}
    return t.substitute_placeholders(field_type, mapping, resolver)


def _substitute_enum_type_params(
        resolver: g.Resolver,
        receiver: t.EnumSpec,
        field_type: t.TypeSpec | None,
) -> t.TypeSpec | None:
    # The enum analogue of _substitute_class_type_params: a generic enum's
    # variant fields are stored against the enum's placeholders (`value: T`), so
    # reading a field off a concrete instantiation (`Chain<String>`) must map the
    # enum's declared placeholders to the receiver's type arguments. Without this,
    # match-arm binders kept the placeholder type (`link.value: T`, not String).
    if field_type is None or not receiver.type_params:
        return field_type
    decl = resolver.find_type(receiver.root_name)
    if not decl or len(decl) != 1:
        return field_type
    placeholders = getattr(decl[0].statement, "type_params", ()) or ()
    if len(placeholders) != len(receiver.type_params):
        return field_type
    mapping = {ph.name: concrete for ph, concrete in zip(placeholders, receiver.type_params)}
    return t.substitute_placeholders(field_type, mapping, resolver)



def _resolve_overloads(resolver: g.Resolver, expected_type: t.TypeSpec | None, candidates: list[g.Resolved[s.DataStatement]]) -> list[g.Resolved[s.DataStatement]]:
    if len(candidates) <= 1:
        return candidates
    # Partition by verdict: definite matches (True) win over undecided ones
    # (None) when both are present. The undecided bucket is only returned
    # when no candidate matches definitively. This gives specific-beats-
    # generic dispatch — e.g. `0 == 1` picks `BasicEquality<Int>::==` over
    # the in-scope-but-unconstrained `BasicEquality<K>::==`.
    def candidate_type(x: g.Resolved[s.DataStatement]) -> t.TypeSpec | None:
        other_type = x.statement.get_type()
        # Apply trait type param substitution so e.g. Plus<Int>.+ has effective type
        # (Int,Int)->Int rather than (TVal,TVal)->TVal, enabling correct disambiguation.
        if (x.scope == g.ResolvedScope.TRAIT
                and x.trait_scope is not None
                and x.owner_class is not None):
            mapping = {p.name: c for p, c in zip(x.owner_class.type_params, x.trait_scope.type_params)}
            other_type = t.substitute_placeholders(other_type, mapping, resolver)
        # The candidate's OWN generic parameters are wildcards: instantiating
        # this candidate can bind them to whatever the argument holds, so no
        # structural mismatch through them may reject it. Substituting an
        # unresolvable NamedSpec makes every comparison through such a slot
        # undecided (None) — crucially even where callable-parameter
        # contravariance puts the placeholder on the ground side of the
        # comparison (the `f: (:TIn): TOut` parameter of the union `?>`
        # against a concrete lambda). A placeholder the candidate does NOT
        # own (the caller's own `K` inside a generic template) stays as-is
        # and keeps rejecting concrete instances, which is what routes
        # template-internal calls to the `where`-constraint's method.
        own = getattr(x.statement, "type_params", None) or ()
        if own:
            wildcards = {p.name: t.NamedSpec(x.statement.line_ref, "$overload$wildcard")
                         for p in own}
            other_type = t.substitute_placeholders(other_type, wildcards, resolver)
        # A GENERIC ambient instance's placeholders are equally the
        # candidate's own: the instance is a family, and instantiating this
        # member can bind them to whatever the use site holds.
        if x.instance_params:
            wildcards = {n: t.NamedSpec(x.statement.line_ref, "$overload$wildcard")
                         for n in x.instance_params}
            other_type = t.substitute_placeholders(other_type, wildcards, resolver)
        return other_type

    def partition(expected: t.TypeSpec | None) -> list[g.Resolved[s.DataStatement]]:
        truthy: list[g.Resolved[s.DataStatement]] = []
        maybe: list[g.Resolved[s.DataStatement]] = []
        for x in candidates:
            b = t.trivially_assignable_equals(resolver, expected, candidate_type(x))
            if b is True:
                truthy.append(x)
            elif b is None:
                maybe.append(x)
        return truthy if truthy else maybe

    survivors = partition(expected_type)
    if survivors or not isinstance(expected_type, t.CallableSpec) or expected_type.result is None:
        return survivors
    # Every candidate was rejected and the expected shape is a CALL: the result
    # slot is the usual culprit — a call in a union-typed position expects
    # `Int|Err` while every candidate returns a member, and callables demand
    # bidirectional result equivalence (correct for function VALUES, which get
    # no implicit thunk). A CALL owns its own result conversion, so retry on
    # the parameters alone; a unique winner widens into the union at the call.
    return partition(dataclasses.replace(expected_type, result=None))



# Sentinel: a bare enum-field name that SEVERAL possible variants declare (at
# different layout positions) — reading it un-narrowed would be a silent read
# of one arbitrary variant's slot. compile leaves the name unresolved and
# check() reports it.
_AMBIGUOUS_ENUM_FIELD = object()


def _narrowed_enum_field(resolver: g.Resolver, espec: t.EnumSpec,
                         bare: str):
    """Resolve bare field name `bare` against enum subject `espec`, honouring
    its narrowing: the (unique_name, type) pair, None when absent, or
    _AMBIGUOUS_ENUM_FIELD. A single enum-wide match resolves directly; when
    several variants declare the same bare name, only a field the narrowed
    value is GUARANTEED to carry (declared at a node covering every possible
    leaf) may win."""
    cands = [(fn, ft) for fn, ft in _enum_fields(resolver, espec) if g.match_name(fn, bare)]
    if len(cands) == 1:
        return cands[0]
    if not cands:
        return None
    types = resolver.find_type(espec.root_name)
    if len(types) != 1 or not isinstance(types[0].statement, s.EnumStatement):
        return None  # root not resolved yet: retry next pass
    covering = {fn for fn, _ in types[0].statement.covering_fields(espec.valid_leaf_names)}
    owned = [c for c in cands if c[0] in covering]
    return owned[0] if len(owned) == 1 else _AMBIGUOUS_ENUM_FIELD



@dataclass
class DotExpression(Expression):
    base: Expression
    name: str

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,Any],Any]) -> Expression:
        return rw.rewrite(self, replace, resolver,
            base=self.base.search_and_replace(resolver, replace))

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        btype = self.base.get_type(resolver)
        match btype:
            case t.TupleSpec(entries=entries):
                entry = next((en for en in entries if en.name == self.name), None)
                return entry.type if entry else None
            case t.ClassSpec() as cspec:
                cdecl = resolver.find_type(cspec.name)
                if not cdecl or len(cdecl) > 1:
                    raise ValueError("A resolved class is later resolving incorrectly. Probably a compiler bug.")
                cdecl = cdecl[0].statement
                if not isinstance(cdecl, s.ClassStatement):
                    raise ValueError("A resolved class is later resolving to a wrong type. Probably a compiler bug.")
                datas = cdecl.find_data(resolver, self.name)
                if datas and len(datas) == 1:
                    return _substitute_class_type_params(
                        resolver, cspec, cdecl, datas[0].statement.get_type())
            case t.EnumSpec() as espec:
                ft = next((ft for fn, ft in _enum_fields(resolver, espec) if fn == self.name), None)
                return _substitute_enum_type_params(resolver, espec, ft)
        return None


    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) ->  tuple[Expression, list[s.Statement]]:
        base, new_statements = self.base.compile(resolver, None)
        name = self.name

        btype = base.get_type(resolver)
        match btype:
            case t.TupleSpec():
                pass  # field name is already the tuple entry name
            case t.ClassSpec(_, cname):
                cdecl = resolver.find_type(cname)
                if not cdecl or len(cdecl) > 1:
                    raise ValueError()
                cdecl = cdecl[0].statement
                if not isinstance(cdecl, s.ClassStatement):
                    raise ValueError()
                datas = _resolve_overloads(resolver, expected_type, cdecl.find_data(resolver, self.name))
                if len(datas) == 1:
                    name = datas[0].unique_name
            case t.EnumSpec() as espec:
                if '@' not in self.name:
                    match_field = _narrowed_enum_field(resolver, espec, self.name)
                    if match_field is not None and match_field is not _AMBIGUOUS_ENUM_FIELD:
                        name = match_field[0]

        expr = dataclasses.replace(self, base=base, name=name)
        # A field read owns its conversion to the receiver (an `A`-typed field
        # into an `A|None` slot). A method load (CallableSpec expected) never
        # converts.
        from pyast.expression.conversion import converted
        return converted(expr, expected_type, resolver), new_statements

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        btype = self.base.get_type(resolver)
        match btype:
            case t.TupleSpec(entries=entries):
                entry = next((en for en in entries if en.name == self.name), None)
                if not entry:
                    return [Error(self.line_ref, f"Could not find field {self.name}")]
                return []
            case t.ClassSpec(_, cname):
                cdecl = resolver.find_type(cname)
                if not cdecl or len(cdecl) > 1:
                    raise ValueError()
                cdecl = cdecl[0].statement
                if not isinstance(cdecl, s.ClassStatement):
                    raise ValueError(self.line_ref, "Does not reference a class")
                datas = cdecl.find_data(resolver, self.name)
                if not datas:
                    return [Error(self.line_ref, f"Could not find a field named {self.name}")]
                if len(datas) > 1:
                    return [Error(self.line_ref, f"Ambiguous reference to field named {self.name}")]
            case t.EnumSpec() as espec:
                if any(fn == self.name for fn, _ in _enum_fields(resolver, espec)):
                    return []  # already resolved to a unique field name
                found = _narrowed_enum_field(resolver, espec, self.name)
                if found is _AMBIGUOUS_ENUM_FIELD:
                    return [Error(self.line_ref,
                        f"field '{self.name}' is declared by more than one possible "
                        f"variant here — match on the specific variant first")]
                if found is None:
                    return [Error(self.line_ref, f"Could not find field {self.name}")]
                return []
        return []

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        base_bundle = self.base.generate(resolver)
        btype = self.base.get_type(resolver)
        match btype:
            case t.TupleSpec(entries=entries):
                idx = next((i for i, en in enumerate(entries) if en.name == self.name), None)
                if idx is None:
                    raise ValueError(f"Field {self.name} not found in TupleSpec")
                result_var = cg_p.StructField(base_bundle.result_var, f"_{idx}")
                return base_bundle + g.OperationBundle((), (), result_var)

            case t.ClassSpec(_, cname):
                cdecl = checked_cast(s.ClassStatement, resolver.find_type(cname)[0].statement)
                data = cdecl.find_data(resolver, self.name)[0].statement
                xtype = data.get_type().generate(resolver)

                if not isinstance(data, s.FunctionStatement):
                    result_var = cg_p.ObjectField(xtype, base_bundle.result_var, cdecl.name, data.name, None)
                elif "final" not in cdecl.attributes:
                    result_var = cg_p.VirtualFunction(data.name, base_bundle.result_var)
                else:
                    result_var = cg_p.GlobalFunction(data.name, base_bundle.result_var, c_symbol=_foreign_symbol(data), impure=_is_impure(data), sync=_is_sync(data))

                return base_bundle + g.OperationBundle(stack_vars=(), operations=(), result_var=result_var)

            case t.EnumSpec() as es:
                # The union's repr owns the field read (complex enum -> heap
                # object field; flat enum -> slot reconstruction from the tagged
                # struct).
                result_var = union_repr.classify(es, resolver).read_field(
                    base_bundle.result_var, self.name, resolver)
                return base_bundle + g.OperationBundle((), (), result_var)

        raise ValueError("Could not generate dot expression")



def _distinct_resolutions(datas: list) -> list:
    """Collapse duplicate resolutions of the SAME statement reached by
    different resolver routes (root scope vs import scope, stacked imports):
    one statement is one candidate, whatever paths found it. Ambiguity
    judgements must run on distinct statements only — the duplicate-route
    case used to report "ambiguous" with a single candidate listed."""
    seen: set[int] = set()
    out = []
    for d in datas:
        key = id(d.statement)
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out


def _scope_filtered(datas, resolved_trait_scope: t.ClassSpec | None):
    """Disambiguate multi-candidate trait members against the scope compile
    committed. Exact match first (where-clause / concrete-instance
    candidates); a generic ambient instance's candidate carries the PATTERN
    scope, so it matches when the pattern unifies with the committed
    (solved) scope through the instance's own placeholders."""
    if len(datas) <= 1 or resolved_trait_scope is None:
        return datas
    filtered = [d for d in datas if d.trait_scope == resolved_trait_scope]
    if len(filtered) != 1:
        # unify_generic is deliberately lenient: a structural mismatch defers
        # (returns the mapping so far) rather than failing, so the caller must
        # demand every instance placeholder actually bound — exactly as
        # _solve_instance_scope does. Testing `is not None` alone let a
        # FOREIGN generic instance of the same interface through on the empty
        # mapping (two generic ambient Drop instances made every drop
        # unresolvable).
        def scope_binds(d) -> bool:
            if not d.instance_params or d.trait_scope is None:
                return False
            binding = t.unify_generic(d.trait_scope, resolved_trait_scope,
                                      set(d.instance_params))
            return binding is not None and set(binding) == set(d.instance_params)
        filtered = [d for d in datas if scope_binds(d)]
    return filtered if len(filtered) == 1 else datas


def _solve_instance_scope(resolver: g.Resolver, data,
                          expected_type: t.TypeSpec | None) -> t.ClassSpec | None:
    """Bind a generic ambient instance's own placeholders from the use site —
    the latch a generic FUNCTION candidate gets, applied to the instance.
    Returns the solved interface scope (Sized<List<T>> ⇒ Sized<List<Int>>),
    or None while the use site can't bind every placeholder yet."""
    if expected_type is None or data.owner_class is None or data.trait_scope is None:
        return None
    effective = data.statement.get_type()
    if effective is None:
        return None
    mapping = {p.name: c for p, c in zip(data.owner_class.type_params,
                                         data.trait_scope.type_params)}
    effective = t.substitute_placeholders(effective, mapping, resolver)
    binding = t.unify_generic(effective, expected_type, set(data.instance_params))
    if binding is None or set(binding) != set(data.instance_params):
        return None
    solved = t.substitute_placeholders(data.trait_scope, binding, resolver)
    return solved if isinstance(solved, t.ClassSpec) else None


@dataclass
class NamedExpression(Expression):
    name: str
    type_params: tuple[t.TypeSpec, ...] = ()
    # Disambiguation cache re-derived from `name` by compile each pass — not
    # part of program identity, so its settling never keeps the loop spinning.
    resolved_trait_scope: t.ClassSpec | None = field(default=None, compare=False)


    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        # If the name resolves to just one statement we have a known type
        # The name might actually resolve to just one, or we might have gone
        # through a compile step and found the unique name of a type match.
        # Both outcomes are fine.
        datas = resolver.find_data(self.name)
        # An incomplete search can't give a trustworthy type yet — defer.
        if not datas.complete:
            return None
        # compile() already disambiguated via resolved_trait_scope; filter to that scope
        datas = _scope_filtered(datas, self.resolved_trait_scope)
        if len(datas) != 1:
            return None
        resolved = datas[0]
        statement = resolved.statement
        raw_type = statement.get_type()
        if raw_type is None:
            return None

        mapping: dict[str, t.TypeSpec] = {}

        # Case 1: explicit type params on the call site (e.g., doNothing<Int>)
        if self.type_params and hasattr(statement, 'type_params') and statement.type_params:
            for placeholder, concrete in zip(statement.type_params, self.type_params):
                mapping[placeholder.name] = concrete

        # Case 2: resolved via a 'where' clause trait — map the interface's type params
        # to the concrete types recorded in the trait_scope on this Resolved instance.
        if (resolved.scope == g.ResolvedScope.TRAIT
                and resolved.trait_scope is not None
                and resolved.owner_class is not None):
            # A generic ambient instance's candidate carries the pattern
            # scope; the SOLVED scope compile committed (instance
            # placeholders bound from the use site) takes precedence.
            scope = (self.resolved_trait_scope
                     if resolved.instance_params and self.resolved_trait_scope is not None
                     else resolved.trait_scope)
            for placeholder, concrete in zip(resolved.owner_class.type_params,
                                             scope.type_params):
                mapping[placeholder.name] = concrete

        return t.substitute_placeholders(raw_type, mapping, resolver)

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,Any],Any]) -> Expression:
        rts = rw.opt(self.resolved_trait_scope, resolver, replace)
        return rw.rewrite(self, replace, resolver,
            type_params=rw.seq(self.type_params, resolver, replace),
            resolved_trait_scope=(rts if rts is rw.UNCHANGED or isinstance(rts, t.ClassSpec) else None))

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement]]:
        # Resolve the statement this name refers to. Once the name is fully
        # qualified (@-hash) we skip the ambiguity check but still run the
        # generic-inference step below, because the argument types feeding
        # inference may only become known on a later iteration of the
        # compile loop.
        datas = resolver.find_data(self.name)
        if '@' not in self.name:
            # Never commit a name against an INCOMPLETE candidate set: the search
            # was blocked (an unresolved `[where]` alias / NamedSpec), so the
            # candidate that should win may not be visible yet. Leave the use
            # unresolved and retry once the blocker clears on a later pass.
            if not datas.complete:
                return self, []
            datas = _resolve_overloads(resolver, expected_type, datas)
            if len(datas) != 1:
                return self, [] # didn't find a unique candidate
            data = datas[0]
            if data.scope == g.ResolvedScope.MEMBER:
                this = NamedExpression(self.line_ref, "this")
                dot = DotExpression(self.line_ref, this, data.unique_name)
                return dot, []
            new_name = data.unique_name
            trait_scope = (data.trait_scope
                           if data.scope == g.ResolvedScope.TRAIT
                           and isinstance(data.trait_scope, t.ClassSpec)
                           else None)
            # A generic ambient instance's member commits only once the use
            # site binds every instance placeholder; until then leave the
            # use unresolved and let a later pass retry (fixpoint style).
            if data.instance_params:
                trait_scope = _solve_instance_scope(resolver, data, expected_type)
                if trait_scope is None:
                    return self, []
        else:
            if len(datas) != 1:
                return self, []
            data = datas[0]
            new_name = self.name
            trait_scope = self.resolved_trait_scope

        # Fill or refresh this use's type arguments from the enclosing
        # CallExpression's expected type; runs while any supplied argument
        # still carries a hole, keeping a partial result's placeholders for a
        # later pass (see _infer_use_site_type_params for the rules).
        type_params_to_compile = inference.use_site_type_params(
            data.statement, self.type_params, expected_type, resolver)

        type_params, new_statements = u.flatten_lists(x.compile(resolver) for x in type_params_to_compile)
        expr = dataclasses.replace(self, name=new_name, type_params=tuple(type_params), resolved_trait_scope=trait_scope)
        # A committed load owns its conversion to the receiver (an `A`-typed
        # binding into an `A|None` slot). Ground types only, so the expected-
        # SHAPE overload selection above is undisturbed, and a CallableSpec
        # expected (this load is being called) never converts.
        from pyast.expression.conversion import converted
        return converted(expr, expected_type, resolver), new_statements

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        tp_errors = [te for tp in self.type_params for te in tp.check(resolver)]
        # Duplicate-route resolutions of one statement are one candidate for
        # ambiguity purposes ONLY here in check: get_type/compile treat the
        # raw multiplicity as an unresolved signal that overload inference
        # depends on, so they must keep seeing it.
        datas = _distinct_resolutions(resolver.find_data(self.name))
        # compile() already disambiguated via resolved_trait_scope; filter to that scope
        datas = _scope_filtered(datas, self.resolved_trait_scope)
        match datas:
            case []:
                return [Error(self.line_ref, f"Failed to resolve {self.name}")] + tp_errors
            case [resolved]:
                # A generic AMBIENT instance member that never committed a
                # solved scope: the use site could not bind the instance's
                # placeholders — ambience applies to concrete types only, so
                # a name-match alone is NOT a resolution (without this the
                # template dies later, deep in codegen).
                if resolved.instance_params and self.resolved_trait_scope is None:
                    return [Error(self.line_ref,
                        f"Failed to resolve {g.bare_name(self.name)}: the ambient instance "
                        f"applies to concrete types only — generic code needs its own "
                        f"`where` clause")] + tp_errors
                return resolved.statement.check_caller_type_params(resolver, self.type_params, self.line_ref) + tp_errors
            case _:
                # `name` resolves more than one way — commonly a top-level
                # namespace versus an import-relative one (loading a library can
                # introduce such a clash). There is no precedence rule: the user
                # must qualify. List every candidate's fully-qualified spelling so
                # they know which reading each one selects.
                candidates = ", ".join(sorted({d.unique_name for d in datas}))
                return [Error(self.line_ref,
                    f"Ambiguous reference '{self.name}' — qualify it. Candidates: {candidates}")] + tp_errors

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        x = resolver.find_data(self.name)
        if not x:
            raise ValueError(f"Could not find {self.name}")
        x = x[0]
        match (x.scope, x.statement):
            case (g.ResolvedScope.GLOBAL, stmt) if isinstance(stmt, s.FunctionStatement):
                return g.OperationBundle((), (), cg_p.GlobalFunction(self.name, c_symbol=_foreign_symbol(stmt), impure=_is_impure(stmt), sync=_is_sync(stmt)))
            case (g.ResolvedScope.GLOBAL, stmt) if isinstance(stmt, s.LetStatement):
                xtype = stmt.declared_type
                if not xtype: raise ValueError(f"Failed to resolve {self.name} due to missing type")
                # Deferred-init lets are stored as a DataPointer to their
                # Lazy$<T> stub — not as the user-visible value type.
                # Any NamedExpression that survives lower_lazy_lets
                # (lambdas-pass capture sites, class-field initialisers)
                # needs the stub pointer, not the value.
                storage = cg_t.DataPointer() if stmt.is_deferred_init() else xtype.generate(resolver)
                return g.OperationBundle((), (), cg_p.GlobalVar(storage, self.name))
            case (g.ResolvedScope.LOCAL, stmt) if isinstance(stmt, s.LetStatement):
                xtype = stmt.declared_type
                if not xtype: raise ValueError(f"Failed to resolve {self.name} due to missing type")
                storage = cg_t.DataPointer() if stmt.is_deferred_init() else xtype.generate(resolver)
                return g.OperationBundle((), (), cg_p.StackVar(storage, self.name))
            case (scope, stmt):
                raise ValueError(f"Reference to {scope} / {type(stmt)} for named reference {self.name} not implemented yet")



@dataclass
class ArrayReadExpression(Expression):
    """Read element `index` of an array class's trailing storage, aborting if the
    index is out of range. This is the "function out" half of an array: the
    generated accessor method `(Int32): Elem` (created alongside the constructor)
    has this as its body. `object` is the array instance; `index` is the Int32
    offset. Lowers to a single `cg_p.ArrayElement` — the bounds check lives in
    the `array_bounds_check` runtime helper."""
    object: Expression
    index: Expression

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver, Any], Any]) -> Expression:
        return rw.rewrite(self, replace, resolver,
            object=self.object.search_and_replace(resolver, replace),
            index=self.index.search_and_replace(resolver, replace))

    def __array_info(self, resolver: g.Resolver):
        """(class_name, element_spec, length_field_name) for `object`'s array
        class, or None if its type isn't resolved/an array class yet."""
        otype = self.object.get_type(resolver)
        if not isinstance(otype, t.ClassSpec):
            return None
        found = resolver.find_type(otype.name)
        if len(found) != 1 or not isinstance(found[0].statement, s.ClassStatement):
            return None
        classstmt = checked_cast(s.ClassStatement, found[0].statement)
        af = classstmt.array_field(resolver)
        if af is None:
            return None
        af_spec = checked_cast(t.ArrayFieldSpec, af.declared_type)
        len_name = next((f.name for f in classstmt.get_fields(resolver)
                         if g.name_matches(f.name, af_spec.length_field)), None)
        if len_name is None:
            return None
        return otype.name, af_spec.element, len_name

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        info = self.__array_info(resolver)
        return info[1] if info is not None else None

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement]]:
        obj, oglb = self.object.compile(resolver, None)
        idx, iglb = self.index.compile(resolver, t.BuiltinSpec(self.line_ref, "int32"))
        return dataclasses.replace(self, object=obj, index=idx), oglb + iglb

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        return self.object.check(resolver, None) + self.index.check(resolver, None)

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        info = self.__array_info(resolver)
        assert info is not None, "ArrayReadExpression on a non-array-class object"
        cname, elem_spec, len_name = info

        obj_b = self.object.generate(resolver).with_prefix("arr")
        idx_b = self.index.generate(resolver).with_prefix("idx")

        # Materialise object and index into single-assignment vars so the
        # ArrayElement param can name each once (it reads the base, the length,
        # and the index from them).
        obj_var = cg_p.StackVar(cg_t.DataPointer(), "aobj")
        idx_var = cg_p.StackVar(cg_t.Int(32), "aidx")
        elem = cg_p.ArrayElement(elem_spec.generate(resolver), obj_var, cname, "array", len_name, idx_var)

        return obj_b + idx_b + g.OperationBundle(
            stack_vars=(obj_var, idx_var),
            operations=(cg_o.Move(obj_var, obj_b.result_var), cg_o.Move(idx_var, idx_b.result_var)),
            result_var=elem)


@dataclass
class LazyExpression(Expression):
    """Auto-forced reference to a `[lazy]` let.

    Three modes, selected by where the reference textually appears:

    * **Local-scope** (default): the stub lives in a `StackVar` named
      `stub_name` in the enclosing function.  Emitted by
      `lower_lazy_lets` for every reference to a `[lazy]` local.
    * **Global-scope**: the stub is a static `Lazy$<T>` instance
      accessed as a `GlobalVar`.  Selected at `generate` time when
      `resolver.find_data` reports `ResolvedScope.GLOBAL`.
    * **Captured** (`captured_class` set): the reference is inside a
      lifted lambda body and the stub is held in `this.<stub_name>`
      on the closure class.  Set by `lambdas.__redirect_references_to_class`
      after the lambdas pass discovers the lazy reference as a free
      variable inside the body.

    Orthogonally, `stub_only` selects the *raw stub pointer* instead of
    the forced value: `generate` hands back the stub slot without the
    `lazy_fetch` call.  Used at a closure's capture site so a lambda can
    capture an as-yet-unforced `[lazy]` value of *any* shape — the stub
    is always a DataPointer, whereas reading the value would (for a
    struct-shaped let) read the slot as the wrong, value-shaped type.
    """
    stub_name: str
    target_type: t.TypeSpec
    captured_class: str | None = None
    stub_only: bool = False

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        if self.stub_only:
            return t.LazyStubSpec(self.line_ref, self.target_type)
        return self.target_type

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement]]:
        # lower_lazy_lets runs after the compile loop has converged, so
        # there's nothing left for LazyExpression to compile.
        return self, []

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        return []

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,Any],Any]) -> Expression:
        return rw.rewrite(self, replace, resolver,
            target_type=self.target_type.search_and_replace(resolver, replace))

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        import lowering.lazy_thunks as lt
        ir_t = self.target_type.generate(resolver)
        # `_ir_mangle` raises NotImplementedError for unsupported IR types.
        lt._ir_mangle(ir_t)

        stub_ref: cg_p.RParam
        if self.captured_class is not None:
            # Inside a lifted lambda — the stub was captured as a field
            # on the closure class.  `this` is the closure instance.
            this_var = cg_p.StackVar(cg_t.DataPointer(), "this")
            stub_ref = cg_p.ObjectField(cg_t.DataPointer(), this_var,
                                        self.captured_class, self.stub_name, None)
        else:
            # Pick GlobalVar vs StackVar based on the resolved scope so
            # the same LazyExpression node works for both `[lazy]` locals
            # and `[lazy]` globals.
            found = resolver.find_data(self.stub_name)
            if found and len(found) == 1 and found[0].scope == g.ResolvedScope.GLOBAL:
                stub_ref = cg_p.GlobalVar(cg_t.DataPointer(), self.stub_name)
            else:
                stub_ref = cg_p.StackVar(cg_t.DataPointer(), self.stub_name)

        # Capture-site read: hand back the raw stub pointer without forcing
        # it, so a closure can capture an unforced `[lazy]` value of any
        # shape (the stub is always a DataPointer).
        if self.stub_only:
            return g.OperationBundle(
                stack_vars=(),
                operations=(),
                result_var=stub_ref,
            )

        sv_result = cg_p.StackVar(ir_t, "$force_result")
        # The fetch function takes `this` as its single parameter, which —
        # under the YAFL ABI — comes from the GlobalFunction's `.object`
        # field (the implicit self).  No additional struct args.
        # async_lower wraps the register to wrap_return_type(ir_t) and
        # inserts the IS_TASK + unwrap dance automatically.
        call = cg_o.Call(
            function=cg_p.GlobalFunction(lt.fetch_function_name(ir_t), stub_ref),
            parameters=cg_p.NewStruct(()),
            register=sv_result,
        )
        return g.OperationBundle(
            stack_vars=(sv_result,),
            operations=(call,),
            result_var=sv_result,
        )



