"""Call-site generic-parameter inference — the compile-side of the type system.

The compile-fixpoint twin of pyast/typespec/algebra.py: where the algebra
answers questions about types (meet/refine/unify/solve), this module answers
ONE question about a USE of a generic statement — what type arguments should it
carry? — by combining the three sources, strongest first: the argument types,
the expected result type, and the `where` constraints discharged against the
`[trait]` instances in scope (t.solve_trait_constraint). Results may be
PARTIAL (unbound params keep their own placeholder for a later pass) and are
MONOTONE across passes (fresh bindings meet previously stored ones — inference
refines, never forgets).

`use_site_type_params` is the entry point (NamedExpression.compile); the rest
are its internals.
"""
from __future__ import annotations

import pyast.resolver as g
import pyast.statement as s
import pyast.typespec as t


def _trait_instances(resolver: g.Resolver) -> list[t.TraitInstance]:
    """Every `[trait]` instance in scope, concrete instances first, for
    t.solve_trait_constraint to match a `where` constraint against.

    A non-generic instance (`let [trait] _one: _OneStream`) has empty param_names
    and grounds a constraint directly. A generic provider
    (`let [trait] _stream_pretty<S,E>: _StreamPretty<S,E>`, whose witness implements
    `Stream<Pretty<S,E>, String, E>`) carries its params; matching its interface
    against the constraint binds them all from the constraint's own type args (the
    combinator type spells its error), so the target reads off in one step."""
    out: list[t.TraitInstance] = []
    for st in resolver.get_traits():
        dt = st.declared_type
        if not isinstance(dt, t.ClassSpec):
            continue
        found = resolver.find_type(dt.name)
        if len(found) != 1 or not isinstance(found[0].statement, s.ClassStatement):
            continue
        cls = found[0].statement
        if cls._all_parents is None:            # parents not resolved yet this iteration
            continue
        remap = ({p.name: c for p, c in zip(cls.type_params, dt.type_params)}
                 if cls.type_params and len(cls.type_params) == len(dt.type_params) else {})
        param_names = frozenset(p.name for p in (st.type_params or ()))
        for parent in cls._all_parents:
            if not isinstance(parent, t.ClassSpec):
                continue
            iface = t.substitute_placeholders(parent, remap, resolver) if remap else parent
            if isinstance(iface, t.ClassSpec):
                out.append(t.TraitInstance(param_names, iface))
    out.sort(key=lambda inst: len(inst.param_names))   # concrete instances (no params) first
    return out




def _infer_type_params_via_where(stmt: s.Statement, mapping: dict[str, t.TypeSpec],
                                 resolver: g.Resolver,
                                 declared_params: t.TypeSpec | None) -> dict[str, t.TypeSpec]:
    """Bind type parameters that argument inference *cannot* determine, by solving
    the function's `where` constraints against the trait instances in scope.

    The only candidates are parameters that appear in no value parameter — `E` in
    `drain<S, E>(s: S, ...): Int | E where Stream<S, Int, E>` is never read off an
    argument, so once `S` is bound (from `s: S`), discharging `Stream<S, Int, E>`
    pins `E`. A parameter that DOES appear in the value parameters (e.g. the
    `TVal` of `>=(a: TVal, b: TVal) where BasicCompare<TVal>`) is excluded: it
    must come from the arguments, and binding it from an arbitrary instance would
    pick the wrong one. Discharge handles both a direct concrete instance
    (`Stream<One, Int, Never>` → `E = Never`) and a generic combinator chain
    (`Stream<Pretty<Lexer<StreamIO>>, String, E>` → `E = IOError | JsonParseError`)
    via t.solve_trait_constraint. Additive: leaves the mapping untouched if
    nothing grounds."""
    type_params = getattr(stmt, "type_params", None) or ()
    arg_inferrable = t.placeholder_names_in(declared_params)
    targets = {p.name for p in type_params
               if p.name not in mapping and p.name not in arg_inferrable}
    if not targets:
        return mapping
    instances = _trait_instances(resolver)
    for wc in getattr(stmt, "trait_params", ()):
        if not targets:
            break
        wc_sub = t.substitute_placeholders(wc, mapping, resolver)
        if not isinstance(wc_sub, t.ClassSpec):
            continue
        binding = t.solve_trait_constraint(wc_sub, targets, instances, resolver)
        if binding:
            mapping = {**mapping, **binding}
            targets = {p.name for p in type_params
                       if p.name not in mapping and p.name not in arg_inferrable}
    return mapping


def _infer_type_params(stmt: s.Statement, declared: t.CallableSpec,
                       expected: t.CallableSpec,
                       resolver: g.Resolver) -> dict[str, t.TypeSpec] | None:
    """Infer a generic function's type parameters at a call site from the actual
    call types and the function's `where` constraints. The single home for
    call-site type-param inference.

    Three sources, strongest first: the argument types (declared parameter tuple
    vs the actual one), the expected result type, and — for a parameter that
    appears only in a `where` clause — the concrete trait instances in scope.
    Returns the {name: type} mapping, which may be PARTIAL (some params still
    unbound); the caller decides how to apply it. None means the shapes don't
    unify at all."""
    placeholder_names = {tp.name for tp in (getattr(stmt, "type_params", None) or ())}
    mapping = t.unify_generic(declared.parameters, expected.parameters, placeholder_names)
    if mapping is not None and declared.result is not None and expected.result is not None:
        mapping = t.unify_generic(declared.result, expected.result, placeholder_names, mapping)
    if mapping is None:
        return None
    return _infer_type_params_via_where(stmt, mapping, resolver, declared.parameters)


def use_site_type_params(stmt: s.Statement,
                                supplied: tuple[t.TypeSpec, ...],
                                expected_type: t.TypeSpec | None,
                                resolver: g.Resolver) -> tuple[t.TypeSpec, ...]:
    """The type arguments a use of generic `stmt` should carry: `supplied` if it
    is complete, otherwise re-inferred from the enclosing call's expected type.

    "Complete" is scope-aware and structural (t.has_free_placeholders): a
    placeholder that resolves in scope is an enclosing/self generic's param
    passing through — the `S`,`E` of a recursive `drain<S,E>(…) = drain<S,E>(…)`
    — and latches; one that does not resolve is a not-yet-bound leftover, even
    buried inside a compound argument like `Pty<Lex<S>>` where a nested generic
    call's result latched before its own param ground. The structural test is
    what lets this use refresh once the inner hole fills (a bare top-level test
    left `Pty<Lex<S>>` latched forever and crashed at codegen). Placeholder
    names are globally unique (hash6 of the declaration site), so an enclosing
    `U` and a callee's `U` never alias in find_type.

    A PARTIAL inference keeps each unbound param's own placeholder, and is
    threaded back through get_type into the arguments' expected types — so an
    argument whose type depends on a sibling param (a lambda `(x) => …` whose
    `x: T` comes from another argument) can type on a later pass; the fixpoint
    fills the rest."""
    stmt_type_params = getattr(stmt, "type_params", None) or ()
    if not stmt_type_params or not isinstance(expected_type, t.CallableSpec):
        return supplied
    complete = (len(supplied) == len(stmt_type_params)
                and not any(t.has_free_placeholders(tp, resolver) for tp in supplied))
    if complete:
        return supplied
    declared = stmt.get_type() if hasattr(stmt, "get_type") else None
    if not isinstance(declared, t.CallableSpec):
        return supplied
    mapping = _infer_type_params(stmt, declared, expected_type, resolver)
    if mapping is None:
        return supplied
    # MONOTONE re-inference: a param this pass could not re-derive keeps its
    # previously stored binding (meet — a fresh hole must never overwrite a
    # ground binding; types only refine). A param never bound keeps its own
    # placeholder (`p.type`), so the use stays generic until a later pass.
    prior = (dict(zip((p.name for p in stmt_type_params), supplied))
             if len(supplied) == len(stmt_type_params) else {})
    def bound(p) -> t.TypeSpec:
        fresh = mapping.get(p.name, p.type)
        merged = t.meet(prior.get(p.name), fresh)
        return merged if isinstance(merged, t.TypeSpec) else fresh
    return tuple(bound(p) for p in stmt_type_params)
