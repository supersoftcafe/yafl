"""The type algebra: the algorithms over pyast/typespec/specs.py representations.

Everything here is a pure function of specs (+ a read-only resolver for scope
questions): substitution, placeholder scanning, the meet/refine refinement
rules the compile fixpoint relies on, generic-parameter unification, and
where-constraint solving against trait instances. No spec class calls into
this module; the dependency is strictly specs <- algebra. The `_CONFLICT`
sentinel is internal to the algebra: statement-level callers use `refine`,
which absorbs conflict handling.
"""
from __future__ import annotations

import dataclasses
import pyast.rewrite as rw
from collections.abc import Callable
from typing import NamedTuple

import pyast.resolver as g
from pyast.typespec.specs import (
    TypeSpec, BuiltinSpec, CallableSpec, ClassSpec, CombinationSpec, EnumSpec,
    GenericPlaceholderSpec, NamedSpec, TupleSpec,
)


def substitute_placeholders(spec: "TypeSpec | None", mapping: dict[str, "TypeSpec"],
                            resolver: g.Resolver) -> "TypeSpec | None":
    """Replace every GenericPlaceholderSpec whose name is in `mapping` with its
    mapped concrete type, throughout `spec`. Identity when `spec` is None or
    `mapping` is empty. The single home for the placeholder-to-concrete rewrite
    that generic substitution (class/enum fields, parent interfaces, trait
    dispatch, call-site type params) performs."""
    if spec is None or not mapping:
        return spec
    def replace_fn(_, thing):
        if isinstance(thing, GenericPlaceholderSpec) and thing.name in mapping:
            return mapping[thing.name]
        return rw.UNCHANGED
    return rw.resolved(spec.search_and_replace(resolver, replace_fn), spec)


def placeholder_names_in(spec: "TypeSpec | None") -> set[str]:
    """Every GenericPlaceholderSpec name occurring anywhere in `spec`. A pure
    structural scan — no scope is read, so search_and_replace's resolver slot
    (only ever threaded through to visitors, which ignore it here) gets None."""
    names: set[str] = set()
    if spec is not None:
        def visit(_, thing):
            if isinstance(thing, GenericPlaceholderSpec):
                names.add(thing.name)
            return thing
        spec.search_and_replace(None, visit)
    return names


def has_free_placeholders(spec: "TypeSpec | None", resolver: "g.Resolver") -> bool:
    """True when `spec` contains a GenericPlaceholderSpec that does NOT resolve in
    the current scope — a blank that leaked out of another declaration's generic
    context (e.g. a constructor's own params latched before inference bound them).
    The scope-aware complement of `is_concrete()`: a placeholder is a real type
    inside its declaring generic, a hole everywhere else."""
    return any(not resolver.find_type(name)
               for name in placeholder_names_in(spec))


class _Conflict:
    """Sentinel returned by `meet` for two ground types that cannot be reconciled.
    Distinct from None, which `meet` uses for a hole (no information yet)."""
    __slots__ = ()
_CONFLICT = _Conflict()


def _is_hole(spec: "TypeSpec | None") -> bool:
    """A hole carries no type information yet, so anything refines it: a missing
    (None) slot, an unbound generic placeholder, or a still-unresolved NamedSpec."""
    return spec is None or isinstance(spec, (GenericPlaceholderSpec, NamedSpec))


def meet(a: "TypeSpec | None", b: "TypeSpec | None") -> "TypeSpec | None | _Conflict":
    """The most-refined common form of two possibly-partial types, or `_CONFLICT`
    if they genuinely cannot be reconciled (None means both sides were holes — no
    information either way).

    A HOLE (see `_is_hole`) is refined by the other side; compounds meet
    element-wise and propagate a conflict in any element; two ground leaves must
    be equal. This is the read-through refinement the inference fixpoint relies on,
    so a freshly arg-derived binding (`Lex<One>`) and a stale expected-result view
    of the same slot (`Lex<_>`) reconcile to the ground form instead of colliding
    to a hard failure. Symmetric: `meet(a, b)` and `meet(b, a)` agree."""
    if _is_hole(a):
        return b
    if _is_hole(b):
        return a
    # ClassSpec / generic EnumSpec: a generic instantiation, refined by its type
    # arguments positionally. EnumSpec needs this explicitly because `type_params`
    # is excluded from EnumSpec equality (it is metadata for the generics-redirect
    # pass), so the leaf `a == b` below would judge `Result<Int,_>` and
    # `Result<Int,Bool>` equal and keep the hole. `a == b` fixes the enum identity
    # (root_name + active leaves, type_params aside) before refining the arguments.
    if (isinstance(a, ClassSpec) and isinstance(b, ClassSpec)
            and a.name == b.name and len(a.type_params) == len(b.type_params)):
        return _meet_params(a, a.type_params, b.type_params)
    if (isinstance(a, EnumSpec) and isinstance(b, EnumSpec) and a == b
            and len(a.type_params) == len(b.type_params)):
        return _meet_params(a, a.type_params, b.type_params) if a.type_params else a
    if (isinstance(a, TupleSpec) and isinstance(b, TupleSpec)
            and len(a.entries) == len(b.entries)):
        out = []
        for ea, eb in zip(a.entries, b.entries):
            m = meet(ea.type, eb.type)
            if m is _CONFLICT:
                return _CONFLICT
            out.append(dataclasses.replace(ea, type=(None if m is None else m),
                                           name=ea.name or eb.name))
        return dataclasses.replace(a, entries=tuple(out))
    if isinstance(a, CombinationSpec) and isinstance(b, CombinationSpec):
        # A union is a SET, and `types` is NOT canonically ordered (only the id is
        # sorted), so meet set-wise, never positionally. Two fully-ground unions
        # meet iff they are the same set. If one side is ground, the other's ground
        # members must all be present in it — its holes then absorb the remainder —
        # otherwise it carries a member the ground side lacks: a real conflict.
        # Both sides still holey: defer (CONFLICT here just skips this pass; a later
        # pass grounds one side and resolves it).
        ua, ub = a.as_unique_id_str(), b.as_unique_id_str()
        if ua is not None and ub is not None:
            return a if ua == ub else _CONFLICT
        ga = {u for u in (m.as_unique_id_str() for m in a.types) if u is not None}
        gb = {u for u in (m.as_unique_id_str() for m in b.types) if u is not None}
        if ua is not None:
            return a if gb <= ga else _CONFLICT
        if ub is not None:
            return b if ga <= gb else _CONFLICT
        return _CONFLICT
    if isinstance(a, CallableSpec) and isinstance(b, CallableSpec):
        p = meet(a.parameters, b.parameters)
        r = meet(a.result, b.result)
        if p is _CONFLICT or r is _CONFLICT:
            return _CONFLICT
        return dataclasses.replace(a,
                                   parameters=a.parameters if p is None else p,
                                   result=None if r is None else r)
    # Ground leaves (BuiltinSpec, non-generic EnumSpec, resolved types of differing
    # kinds): reconcilable only if equal.
    return a if a == b else _CONFLICT


def join(a: "TypeSpec | None", b: "TypeSpec | None", resolver: "g.Resolver") -> "TypeSpec | None":
    """Least upper bound: the narrowest type both `a` and `b` widen into — the
    type of a branch (a `match`, a `?:`) whose sides yield `a` and `b`.

    If one side already widens into the other, THAT wider type is the join — a
    member folds into its union (`A ⊔ (A|None)` = `A|None`) and a variant into
    its enum (`Ok ⊔ Result` = `Result`), never a redundant `Result | Ok`. Tuples
    otherwise join FIELD-WISE (`(T, C) ⊔ (None, C)` = `(T|None, C)`, so tuple-
    building arms reconcile to one tuple with union fields, matching a declared
    tuple return). Anything else is a genuine SET UNION of distinct types.
    Identical types and holes short-circuit. Unlike `meet` — which REFINES and
    conflicts on incompatible leaves — join never fails."""
    if a is None:
        return b
    if b is None:
        return a
    if a == b:
        return a
    if b.trivially_assignable_from(resolver, a) is True:
        return b
    if a.trivially_assignable_from(resolver, b) is True:
        return a
    if (isinstance(a, TupleSpec) and isinstance(b, TupleSpec)
            and len(a.entries) == len(b.entries)):
        entries = tuple(dataclasses.replace(ea, type=join(ea.type, eb.type, resolver),
                                            name=ea.name or eb.name)
                        for ea, eb in zip(a.entries, b.entries))
        return dataclasses.replace(a, entries=entries)
    # Genuine set union: build it and read its canonical (flattened, deduped)
    # members; one member left ⇒ the singleton rule (`A ⊔ A` = `A`).
    members = CombinationSpec(a.line_ref, (a, b)).repr_members()
    return members[0] if len(members) == 1 else CombinationSpec(a.line_ref, members)


def refine_widening(current: "TypeSpec | None", resolver: "g.Resolver",
                    infer: "Callable[[], TypeSpec | None]", source_changed: bool) -> "TypeSpec | None":
    """`refine` for a type inferred from a source that can WIDEN across passes.

    A match/branch broadens its arms to their least upper bound, and that grows
    as arms resolve late (`A`, then `A|None`). Plain `refine` latches the first
    concrete view and its `meet` rejects the wider one as a conflict, freezing
    the narrow type. So any receiver inferring from such a source — an undeclared
    return, an untyped `let` — must be free to WIDEN: when the fresh view is a
    strict superset of the settled current type, adopt it.

    Gated on `source_changed` (the receiver's source expression differing from
    last pass): a SETTLED source — a grounded generic call whose type is stable —
    must not be re-derived every pass, which churns its monomorphisation. Only a
    still-converging source is re-read, and only a genuine widening is taken, so
    a stable or re-monomorphised-but-equal view neither churns nor accretes."""
    refined = refine(current, resolver, infer)
    if source_changed and refined is not None and refined.is_concrete():
        fresh = infer()
        if (fresh is not None and fresh.is_concrete()
                and fresh.trivially_assignable_from(resolver, refined) is True
                and refined.trivially_assignable_from(resolver, fresh) is not True):
            return fresh
    return refined


def _meet_params(base: "TypeSpec", a_params: "tuple", b_params: "tuple") -> "TypeSpec | _Conflict":
    """Meet two positional type-argument lists of a generic class/enum and return
    `base` rebuilt with the refined arguments, or `_CONFLICT` if any argument
    conflicts. Class/enum arguments are never None, so a `None` from `meet` (both
    holes) keeps the original argument."""
    merged = [meet(x, y) for x, y in zip(a_params, b_params)]
    if any(m is _CONFLICT for m in merged):
        return _CONFLICT
    return dataclasses.replace(base, type_params=tuple(
        o if m is None else m for m, o in zip(merged, a_params)))


def refine(current: "TypeSpec | None", resolver: "g.Resolver",
           infer: "Callable[[], TypeSpec | None]") -> "TypeSpec | None":
    """The single rule for a statement that stores an inferred type across
    compile passes (an untyped `let`'s declared_type, an undeclared function's
    return_type): keep refining the stored type from the freshly inferred view
    while it still carries a hole, and never let it get worse.

    Gate — refinable only while `current` is missing (None) or carries an
    out-of-scope placeholder blank; anything else is finished and returned
    untouched with `infer` never called (which is why `infer` is a callable:
    a settled type pays nothing per pass). In particular a NON-CONCRETE
    `current` is a DECLARATION whose names haven't resolved yet — its own
    compile resolves it and check owns any mismatch; inference never
    overwrites it. Only inference-stored types can carry a free placeholder,
    so the gate reopens exactly for inference's own partial answers.
    Threshold — an inferred view is adopted only if concrete: placeholder
    blanks may travel across a statement boundary and fill later, but an
    unresolved NAME may not (a callee's raw `T` would land in a scope that
    cannot resolve it). Merge — `meet`, so information only ever accumulates;
    a conflict (check's job to report) leaves `current` unchanged."""
    if current is not None and not has_free_placeholders(current, resolver):
        return current
    inferred = infer()
    if inferred is None or not inferred.is_concrete():
        return current
    merged = meet(current, inferred)
    return merged if isinstance(merged, TypeSpec) else current


def unify_generic(generic: "TypeSpec", concrete: "TypeSpec",
                  placeholder_names: set[str],
                  mapping: dict[str, "TypeSpec"] | None = None) -> dict[str, "TypeSpec"] | None:
    """Match a generic type tree against a concrete type tree; return a
    {placeholder_name: concrete_type} mapping, or None if they don't unify.

    Only recognises placeholders whose name appears in `placeholder_names`.
    Unknown / unresolved branches are skipped (return the current mapping
    unchanged) — the caller should treat a partial mapping as a failure if
    every placeholder must be resolved.
    """
    if mapping is None:
        mapping = {}

    if isinstance(generic, GenericPlaceholderSpec) and generic.name in placeholder_names:
        # Don't let a placeholder bind to itself (or to any other placeholder):
        # the concrete side is not concrete enough to pin down.
        if isinstance(concrete, GenericPlaceholderSpec):
            return mapping
        existing = mapping.get(generic.name)
        if existing is None:
            mapping[generic.name] = concrete
            return mapping
        if existing == concrete:
            return mapping
        # Two bindings for the same placeholder. They MEET rather than collide:
        # one may be a freshly arg-derived ground type and the other a stale,
        # hole-bearing view of the same slot back-propagated as an expected type
        # (e.g. `Lex<One>` from the argument vs `Lex<_>` carried down from a prior
        # pass's result expectation). A hole refines to ground; only a genuine
        # ground-vs-ground mismatch is a real conflict.
        merged = meet(existing, concrete)
        if merged is _CONFLICT:
            return None
        mapping[generic.name] = existing if merged is None else merged
        return mapping

    # Same concrete leaf types — nothing to infer, but compatible.
    if isinstance(generic, BuiltinSpec) and isinstance(concrete, BuiltinSpec):
        return mapping if generic.type_name == concrete.type_name else None

    if isinstance(generic, ClassSpec) and isinstance(concrete, ClassSpec):
        if generic.name != concrete.name:
            return mapping  # can't unify further, accept what we have
        if len(generic.type_params) != len(concrete.type_params):
            return mapping
        m: dict[str, TypeSpec] | None = mapping
        for gp, cp in zip(generic.type_params, concrete.type_params):
            m = unify_generic(gp, cp, placeholder_names, m)
            if m is None:
                return None
        return m

    if isinstance(generic, TupleSpec) and isinstance(concrete, TupleSpec):
        if len(generic.entries) != len(concrete.entries):
            return mapping
        m = mapping
        for ge, ce in zip(generic.entries, concrete.entries):
            if ge.type is None or ce.type is None:
                continue
            m = unify_generic(ge.type, ce.type, placeholder_names, m)
            if m is None:
                return None
        return m

    if isinstance(generic, CombinationSpec) and isinstance(concrete, CombinationSpec):
        # Align by position; this is a weak match but works for the common
        # case where the union variants appear in the same order.
        if len(generic.types) != len(concrete.types):
            return mapping
        m = mapping
        for gv, cv in zip(generic.types, concrete.types):
            m = unify_generic(gv, cv, placeholder_names, m)
            if m is None:
                return None
        return m

    if isinstance(generic, CallableSpec) and isinstance(concrete, CallableSpec):
        m = unify_generic(generic.parameters, concrete.parameters, placeholder_names, mapping)
        if m is None:
            return None
        if generic.result is not None and concrete.result is not None:
            m = unify_generic(generic.result, concrete.result, placeholder_names, m)
            if m is None:
                return None
        return m

    # Unknown / mismatched shapes — return current mapping unchanged rather
    # than failing hard; the caller decides whether it's complete enough.
    return mapping


def bind_from_constraint_match(constraint: "ClassSpec", iface: "ClassSpec",
                               target_names: set[str]) -> dict[str, "TypeSpec"] | None:
    """Positionally match an already-substituted `where` constraint against a
    concrete instance interface, to bind type parameters that argument inference
    (or interface unification) left undetermined.

    Example: with `S` known to be `One`, the constraint `Stream<One, Int, E>`
    matched against the concrete instance `Stream<One, Int, Never>` binds
    `E = Never`. Returns the bindings for `target_names`, or None if the match is
    rejected or adds nothing.

    Strict and positional, deliberately NOT unify_generic. At each position a
    target placeholder is bound to the instance's type; a concrete anchor must
    equal the instance's exactly; anything else — a name/arity mismatch, or an
    anchor that is itself still an unbound placeholder — rejects the whole match.
    A lenient match would bind a target from an unrelated instance and cascade
    into runaway Map<Map<...>> instantiation."""
    if constraint.name != iface.name or len(constraint.type_params) != len(iface.type_params):
        return None
    binding: dict[str, TypeSpec] = {}
    for c_arg, i_arg in zip(constraint.type_params, iface.type_params):
        if isinstance(c_arg, GenericPlaceholderSpec) and c_arg.name in target_names:
            # Bind only from a position the instance itself has resolved: an
            # unresolved NAME here means "not known yet this pass", and binding
            # it would copy the raw name into the caller's type arguments —
            # possibly into a scope that cannot resolve it. Reject the match
            # and let the fixpoint retry once the instance's interface has
            # compiled. (A placeholder is fine — is_concrete rejects names
            # only — so an enclosing generic's param still threads through.)
            if not i_arg.is_concrete():
                return None
            binding[c_arg.name] = i_arg
        elif c_arg.as_unique_id_str() is not None and c_arg.as_unique_id_str() == i_arg.as_unique_id_str():
            continue
        else:
            return None
    return binding or None



class TraitInstance(NamedTuple):
    """A `[trait]` instance as solve_trait_constraint sees it: the implemented
    `interface`, expressed over `param_names` (empty for a non-generic instance)."""
    param_names: frozenset[str]
    interface: "ClassSpec"


def _trait_pattern_compatible(pattern: "TypeSpec", constraint: "TypeSpec") -> bool:
    """Could `pattern` (a provider's interface, still holding its placeholders)
    match `constraint`? A placeholder on either side is a wildcard; two ClassSpecs
    must share a name and arity and agree element-wise; other concrete types must
    have equal ids. A cheap structural prune so the solver only `unify`s a relevant
    provider — without it, `unify_generic`'s leniency on a head mismatch lets every
    `Stream` provider (Map, Filter, …) be tried for a `Stream<Pretty<…>, …>`
    constraint."""
    if isinstance(pattern, GenericPlaceholderSpec) or isinstance(constraint, GenericPlaceholderSpec):
        return True
    if isinstance(pattern, ClassSpec) and isinstance(constraint, ClassSpec):
        if pattern.name != constraint.name or len(pattern.type_params) != len(constraint.type_params):
            return False
        return all(_trait_pattern_compatible(p, c)
                   for p, c in zip(pattern.type_params, constraint.type_params))
    pu, cu = pattern.as_unique_id_str(), constraint.as_unique_id_str()
    if pu is not None and cu is not None:
        return pu == cu
    return True


def solve_trait_constraint(constraint: "ClassSpec", target_names: set[str],
                           instances: "list[TraitInstance]",
                           resolver: g.Resolver) -> dict[str, "TypeSpec"] | None:
    """Ground the `target_names` placeholders of a trait `constraint` — e.g.
    `Stream<Pretty<Lexer<StreamIO, IOError>, IOError|JsonParseError>, String, E>` —
    by matching it against the `[trait]` instances in scope, in a SINGLE step.

    Each stream combinator type carries its element and error params
    (`Pretty<S, E>`, `Map<S, A, B, E>`), so matching the instance interface against
    the constraint binds ALL of the instance's params directly from the
    constraint's own type arguments — there is no need to recurse down the wrapper
    chain (the error is already spelled in the type). The target (`E`) is then read
    off the grounded interface. A concrete leaf instance (no params) binds directly.

    Instances are tried in `instances` order (concrete first); the first whose
    grounded interface binds the targets wins. `_trait_pattern_compatible` keys on
    the wrapper head, so two providers rarely match one constraint. Returns
    {name: type} for the targets, or None.

    This is the CALL-SITE (pre-monomorphisation) where-discharge; its mono-time
    counterpart is lowering/generics.py::__bind_where_params. The two are
    deliberately separate — different questions, different fact bases — see the
    design note in docs/compiler-internals.md §3."""
    # A constraint whose subject type is still a bare placeholder cannot be matched
    # — there is no concrete stream to read the error off. Wait for the fixpoint to
    # make it concrete (also avoids the wildcard prune trying every provider).
    if constraint.type_params and isinstance(constraint.type_params[0], GenericPlaceholderSpec):
        return None
    for inst in instances:
        if not _trait_pattern_compatible(inst.interface, constraint):
            continue
        mapping = unify_generic(inst.interface, constraint, set(inst.param_names)) if inst.param_names else {}
        if mapping is None or set(inst.param_names) - set(mapping):
            continue  # the instance's params are not all fixed by the constraint
        grounded = substitute_placeholders(inst.interface, mapping, resolver) if mapping else inst.interface
        if isinstance(grounded, ClassSpec):
            binding = bind_from_constraint_match(constraint, grounded, target_names)
            if binding:
                return binding
    return None
