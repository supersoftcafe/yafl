"""Call-site generic-parameter inference — the compile-side of the type system.

The compile-fixpoint twin of pyast/typespec/algebra.py: where the algebra
answers questions about types (merge/refine/solve), this module answers
ONE question about a USE of a generic statement — what type arguments should it
carry? — by combining the three sources, strongest first: the argument types,
the expected result type, and the `where` constraints discharged against the
`[trait]` instances in scope (t.solve_trait_constraint). Results may be
PARTIAL (unbound params keep their own placeholder for a later pass) and are
MONOTONE across passes (fresh bindings merge into previously stored ones — inference
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
    # PRE-LOWERING first-class instances: the pattern IS the interface —
    # no witness lookup, no parent substitution.
    for inst in resolver.get_trait_instances():
        if isinstance(inst.pattern, t.ClassSpec):
            out.append(t.TraitInstance(
                frozenset(p.name for p in inst.type_params), inst.pattern))
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
    (`Stream<Pretty<Lexer<Once<String>>>, String, E>` → `E = JsonParseError`)
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


def _unknown_argument_names(covariant: t.TypeSpec, actual: t.TypeSpec,
                            resolver: g.Resolver) -> set[str]:
    """The placeholders of every declared parameter whose argument's type is
    not known yet (absent, unresolved, or holding a hole)."""
    if not isinstance(covariant, t.TupleSpec) or not isinstance(actual, t.TupleSpec):
        return set()
    binding = t.bind_tuple_entries(covariant.entries, [en.name for en in actual.entries])
    if binding is None:
        return set()
    return {name for entry, b in zip(covariant.entries, binding)
            if b is None or not _known(actual.entries[b].type, resolver)
            for name in t.placeholder_names_in(entry.type)}


def interface_arguments(member: t.CallableSpec, expected: t.CallableSpec,
                        names: list[str], resolver: g.Resolver) -> dict[str, t.TypeSpec] | None:
    """The interface's type arguments a call of one of its members implies,
    inferred as a `where`-constrained generic's are: each argument whose type
    the call already settles, merged into its declared parameter — widening
    across arguments, so `(Pay1, Pay2)` gives their common level — then the
    expected result, filling what the arguments left open. Only what binds to
    a settled type is returned; a lambda argument, typed from this very
    binding, says nothing. None when the arguments contradict each other
    (`Int` and `Int32` for one parameter): no instantiation takes them. The
    member's own placeholders are `names`."""
    bindings: dict[str, t.TypeSpec | None] = {n: None for n in names}

    def settled(spec: t.TypeSpec | None) -> bool:
        return (spec is not None and not t.contains_named_spec(spec)
                and not t.has_free_placeholders(spec, resolver)
                and not t.has_missing_arguments(spec, resolver))

    declared = t.without_callable_params(member.parameters)
    actual = expected.parameters
    if isinstance(declared, t.TupleSpec) and isinstance(actual, t.TupleSpec):
        binding = t.bind_tuple_entries(declared.entries, [en.name for en in actual.entries])
        if binding is not None:
            for entry, b in zip(declared.entries, binding):
                if b is None or entry.type is None or isinstance(entry.type, t.CallableSpec):
                    continue
                arg = actual.entries[b].type
                if not settled(arg):
                    continue
                _m, learned, errors = t.merge(entry.type, arg, bindings, resolver, widen_levels=True)
                if errors:
                    return None
                bindings = learned
    if member.result is not None and expected.result is not None and settled(expected.result):
        _r, learned, errors = t.merge(expected.result, member.result, bindings, resolver,
                                      widen_levels=True, callee_left=False)
        if not errors:
            bindings = learned
    return {n: spec for n, spec in bindings.items() if spec is not None and settled(spec)}


def _known(spec: t.TypeSpec | None, resolver: g.Resolver) -> bool:
    """An argument's type is known: present, resolved, and holding no hole."""
    return (spec is not None and spec.is_concrete() and not t.has_free_placeholders(spec, resolver)
            and not t.has_missing_arguments(spec, resolver))


def _arguments_known(declared: t.CallableSpec, expected: t.CallableSpec,
                     resolver: g.Resolver) -> bool:
    """Every argument whose type this call's binding does not itself decide is
    known. A lambda argument's type is derived from the binding, so it never
    counts; an argument left out (a default, or the checker's arity error) has
    nothing to wait for."""
    params, actual = declared.parameters, expected.parameters
    if not isinstance(params, t.TupleSpec) or not isinstance(actual, t.TupleSpec):
        return True
    binding = t.bind_tuple_entries(params.entries, [en.name for en in actual.entries])
    if binding is None:
        return True
    return all(b is None or isinstance(entry.type, t.CallableSpec)
               or _known(actual.entries[b].type, resolver)
               for entry, b in zip(params.entries, binding))


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
    unbound); the caller decides how to apply it. None means the arguments
    contradict the parameters."""
    placeholder_names = {tp.name for tp in (getattr(stmt, "type_params", None) or ())}

    # The declared parameters RECEIVE the arguments: a merge, the callee's
    # params its named holes. Covariant positions first — a callable
    # parameter's own parameters are contravariant, so they only fill what
    # the rest left open (`map(xs: List<T>, f: (:T): U)` takes T from xs).
    # An argument's view is provisional, so there a binding widens across
    # arguments (`pair(Circle(1), Square(2))` binds T to Shape); a callable
    # parameter only fills it, never widens it (`map(circles, (v) =>
    # named(v))` keeps T = Circle though the lambda takes a Shape), and never
    # binds a parameter whose argument is still unknown — that waits for the
    # argument (`fold(xs, init, (a, x) => …)` takes T from xs, never from x,
    # while xs is untyped). A known argument that cannot decide (`?>`'s
    # `value: TIn | E` against `Int | Oops`) leaves it to the lambda's own
    # `(a: Int)`, and a binding one position learns can decide another, so
    # the merge repeats until nothing more is learned. A contradiction in the
    # covariant positions means this candidate does not take these
    # arguments; a callable parameter's type is only evidence to learn from —
    # a lambda's is derived from this very binding on an earlier pass — and
    # the checker owns its mismatches.
    def settled(spec: t.TypeSpec, bindings: dict[str, t.TypeSpec | None]):
        errors: list = []
        for _ in range(len(bindings) + 1):
            _p, learned, errors = t.merge(spec, expected.parameters, bindings, resolver, widen_levels=True)
            if learned == bindings:
                break
            bindings = learned
        return bindings, errors

    covariant = t.without_callable_params(declared.parameters)
    learned, errors = settled(covariant, {name: None for name in placeholder_names})
    if errors:
        return None
    waiting = {name for name in _unknown_argument_names(covariant, expected.parameters, resolver)
               if name in placeholder_names and learned.get(name) is None}
    learned, _errors = settled(declared.parameters,
                               {name: spec for name, spec in learned.items() if name not in waiting})
    mapping = {name: spec for name, spec in learned.items() if spec is not None}
    # The expected result RECEIVES the callee's result: a merge, with the
    # callee's params as named holes the arguments have already bound — so it
    # fills only what the arguments left open (`List()` against
    # `List<Int> | None` is `List<Int>`). A contradiction is the receiver's to
    # report and never erases what the arguments proved. A binding to a
    # narrowed view is provisional (see use_site_type_params) and widens to
    # the view the receiver expects.
    if declared.result is not None and expected.result is not None:
        bindings = {name: mapping.get(name) for name in placeholder_names}
        _result, learned, errors = t.merge(expected.result, declared.result, bindings, resolver,
                                           widen_levels=True, callee_left=False)
        if not errors:
            mapping = {name: spec for name, spec in learned.items() if spec is not None}
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
    # A binding to a NARROWED enum view (`T = Circle`, from a Circle-valued
    # argument) is provisional too: the context may expect the root — a list
    # of Circles flowing where List<Shape> is declared — and generic type
    # arguments are invariant, so the use must widen rather than latch. The
    # merge widens views, so re-inferring against the expected type widens the
    # binding exactly as far as the context demands and no further.
    complete = (len(supplied) == len(stmt_type_params)
                and not any(t.has_free_placeholders(tp, resolver) for tp in supplied)
                and not any(t.contains_below_root(tp) for tp in supplied))
    if complete:
        return supplied
    declared = stmt.get_type() if hasattr(stmt, "get_type") else None
    if not isinstance(declared, t.CallableSpec):
        return supplied
    mapping = _infer_type_params(stmt, declared, expected_type, resolver)
    if mapping is None:
        return supplied
    # MONOTONE re-inference: the stored binding RECEIVES this pass's — a merge
    # that widens a provisional view — so a fresh hole never overwrites a
    # ground binding; types only refine. A param never bound keeps its own
    # placeholder (`p.type`), so the use stays generic until a later pass. A
    # contradiction takes the fresh binding.
    prior = (dict(zip((p.name for p in stmt_type_params), supplied))
             if len(supplied) == len(stmt_type_params) else {})
    # An unbound param is written as its own placeholder, to be read as "not
    # bound yet" next pass. Inside its own declaration (a recursive use) that
    # placeholder RESOLVES — it is the enclosing generic's param — and reads
    # as a complete answer that latches: `depth(Wrap<T>(x), n - 1)` stayed
    # `depth<T>` once an early pass, its second argument still unknown,
    # bound nothing (#136). While an argument is unknown that answer is a
    # guess, so nothing is decided; once every argument is known, a param
    # they still leave unbound IS the caller's own — recursion at the same
    # type — and the placeholder is the answer.
    if (not _arguments_known(declared, expected_type, resolver)
            and any(p.name not in mapping and p.name not in prior
                    and not t.has_free_placeholders(p.type, resolver) for p in stmt_type_params)):
        return supplied
    def bound(p) -> t.TypeSpec:
        fresh = mapping.get(p.name, p.type)
        merged, _b, errors = t.merge(prior.get(p.name), fresh, {}, resolver, widen_levels=True)
        return merged if merged is not None and not errors else fresh
    return tuple(bound(p) for p in stmt_type_params)
