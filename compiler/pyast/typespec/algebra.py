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
from parsing.parselib import Error
from pyast.typespec.specs import (
    TypeSpec, BuiltinSpec, CallableSpec, ClassSpec, CombinationSpec, EnumSpec,
    GenericPlaceholderSpec, NamedSpec, TupleSpec,
    bind_tuple_entries, trivially_assignable_equals,
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
    subbed = rw.resolved(spec.search_and_replace(resolver, replace_fn), spec)
    if subbed is spec:
        return spec
    # Substituting a union member can create a GROUND duplicate — `E | X` with
    # E = X|Y rebuilds as `X|Y|X` — and a duplicate must not survive as a
    # SPELLING (see _flatten_union_members: same set identity but a different
    # exact-equality form, so one type splits into two spellings and the
    # inference fixpoint oscillates). Canonicalise every union the substitution
    # touched; repr_members never folds unresolved members, so mid-fixpoint
    # holes are preserved.
    def canonise_unions(_, thing):
        if isinstance(thing, CombinationSpec):
            members = thing.repr_members()
            if len(members) == 1:
                return members[0]
            if len(members) != len(thing.types):
                return dataclasses.replace(thing, types=tuple(members))
        return rw.UNCHANGED
    return rw.resolved(subbed.search_and_replace(resolver, canonise_unions), subbed)


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


def resolves_in_scope(name: str, resolver: "g.Resolver") -> bool:
    """The scope test for a placeholder NAME: it resolves when the use sits
    inside its declaring generic (an enclosing function's own `T`), where the
    placeholder is a real type; anywhere else it is a hole."""
    return bool(resolver.find_type(name))


def is_narrowed_view(spec: "TypeSpec | None") -> bool:
    """True for an enum VIEW narrower than its enum — `Circle` of `Shape`. A
    type inferred from such a value is provisional: the context may ask for
    the root (or a wider view), and `meet` joins views."""
    return (isinstance(spec, EnumSpec)
            and spec.valid_leaf_names < frozenset(spec.all_leaf_names))


def contains_narrowed_view(spec: "TypeSpec | None") -> bool:
    """True when a narrowed enum view appears anywhere in `spec` — `Circle`
    itself, or the `Op{Move}` inside a stored `List<Op{Move}>`. Such an
    inferred type is provisional: a use-site binding re-infers against its
    expected type, and a stored let/return type keeps refining, so `meet`
    widens it exactly as far as the context demands."""
    if isinstance(spec, EnumSpec):
        return is_narrowed_view(spec) or any(contains_narrowed_view(tp) for tp in spec.type_params)
    if isinstance(spec, ClassSpec):
        return any(contains_narrowed_view(tp) for tp in spec.type_params)
    if isinstance(spec, TupleSpec):
        return any(contains_narrowed_view(en.type) for en in spec.entries)
    if isinstance(spec, CombinationSpec):
        return any(contains_narrowed_view(m) for m in spec.types)
    if isinstance(spec, CallableSpec):
        return contains_narrowed_view(spec.parameters) or contains_narrowed_view(spec.result)
    return False


def has_free_placeholders(spec: "TypeSpec | None", resolver: "g.Resolver") -> bool:
    """True when `spec` contains a GenericPlaceholderSpec that does NOT resolve in
    the current scope — a blank that leaked out of another declaration's generic
    context (e.g. a constructor's own params latched before inference bound them).
    The scope-aware complement of `is_concrete()`: a placeholder is a real type
    inside its declaring generic, a hole everywhere else."""
    return any(not resolves_in_scope(name, resolver)
               for name in placeholder_names_in(spec))


def with_opaque_placeholders(spec: "TypeSpec", resolver: "g.Resolver") -> "TypeSpec":
    """`spec` read where its placeholders are in scope: each one stands as an
    opaque ground type, named by its (globally unique) placeholder name and
    equal only to itself — a template's own `T` is a real type there."""
    names = placeholder_names_in(spec)
    if not names:
        return spec
    return substitute_placeholders(
        spec, {name: BuiltinSpec(spec.line_ref, f"${name}") for name in names}, resolver)


def scoped_unique_id(spec: "TypeSpec", resolver: "g.Resolver") -> str | None:
    """`as_unique_id_str` read INSIDE a scope. A placeholder that resolves there
    (a template's own `T`, and so `List<T>`) is a real type with an identity;
    one that does not is still a hole, and anything else not yet ground stays
    None, exactly as the plain id."""
    if has_free_placeholders(spec, resolver):
        return None
    return with_opaque_placeholders(spec, resolver).as_unique_id_str()


def has_missing_arguments(spec: "TypeSpec | None", resolver: "g.Resolver") -> bool:
    """True when `spec` names a GENERIC class or enum without its type
    arguments anywhere inside — a leaf pattern `ListFull`, or a type stored
    from one. That is a shape whose every argument is a hole (merge fills it),
    not a settled type. A monomorphised instantiation carries its arguments in
    its name and is complete."""
    import pyast.statement as st
    found = [False]
    def visit(_, thing):
        name = (thing.root_name if isinstance(thing, EnumSpec)
                else thing.name if isinstance(thing, ClassSpec) else None)
        if name is not None and not thing.type_params and "$generic$" not in name:
            decl = resolver.find_type(name)
            if (len(decl) == 1 and isinstance(decl[0].statement, (st.EnumStatement, st.ClassStatement))
                    and decl[0].statement.type_params):
                found[0] = True
        return thing
    if spec is not None:
        spec.search_and_replace(resolver, visit)
    return found[0]


def _contains_named_spec(spec: "TypeSpec") -> bool:
    """True when `spec` is or contains a raw NamedSpec spelling — a signature
    view that hasn't compiled yet. Its names are only meaningful in the
    declaring scope, so it must never escape into a type-param binding that
    outlives that scope (compiled at a use site, the `T` inside a latched
    `List<T>` can never resolve and survives to the post-converge scan)."""
    found = [False]
    def visit(_, thing):
        if isinstance(thing, NamedSpec):
            found[0] = True
        return thing
    spec.search_and_replace(None, visit)
    return found[0]


class _Conflict:
    """Sentinel returned by `meet` for two ground types that cannot be reconciled.
    Distinct from None, which `meet` uses for a hole (no information yet)."""
    __slots__ = ()
_CONFLICT = _Conflict()


def merge(left: "TypeSpec | None", right: "TypeSpec | None",
          bindings: "dict[str, TypeSpec | None]", resolver: "g.Resolver",
          widen_views: bool = False, callee_left: bool = True
          ) -> "tuple[TypeSpec | None, dict[str, TypeSpec | None], list[Error]]":
    """The one type merge (docs/type-merge-design.md). LEFT is the receiver,
    RIGHT the value: left must be assignable from right. Fills gaps and
    resolves hierarchy, never widens. Returns the best correct answer (None
    when nothing merges), `bindings` extended by what was learned (returned,
    never mutated), and every contradiction found — the caller collects the
    errors and carries on.

    A HOLE is None, an unresolved name, or a placeholder that does not resolve
    in scope; it takes the other side. A placeholder named in `bindings` is a
    NAMED hole — the reference site's mapping (`T@callee = Int`, or another
    scope's `T@caller`): unbound (None) it binds once, bound it must agree —
    holes inside the binding fill, nothing widens it. Generic ARGUMENTS are
    invariant: they merge by hole-filling only (`List<Circle>` is no
    `List<Shape>`), and a generic spelled without arguments (a leaf pattern
    `ListFull`) is a shape whose every argument is a hole. A value lifts to
    the receiver's head through its class's recorded ancestor spelling
    (`_all_parents`: `Car<X,Y>` records `Automobile<Y>`); an ancestor never
    fits a descendant. Callable parameters reverse direction.

    `widen_views` is for a STORED inference only (`refine`): a narrowed enum
    view there is provisional, so a receiver's view widens to the union of
    both views — anywhere, arguments included — instead of conflicting.

    `callee_left` says which side is the CALLEE's own spelling, the only side
    where a name in `bindings` is a hole (it flips through callable
    parameters). On the other side the same name is the reference site's:
    its own type when in scope, otherwise a leaked unbound placeholder — an
    anonymous hole (a nested call to the same generic sees the outer call's
    unbound V under the very name of its own V)."""
    from pyast.expression.call import _type_str

    Binds = "dict[str, TypeSpec | None]"
    Out = "tuple[TypeSpec | None, dict[str, TypeSpec | None], list[Error]]"

    def is_hole(x, binds, callee_side: bool) -> bool:
        return (x is None or isinstance(x, NamedSpec)
                or (isinstance(x, GenericPlaceholderSpec)
                    and not (callee_side and x.name in binds)
                    and not resolves_in_scope(x.name, resolver)))

    def named_name(x, binds, callee_side: bool) -> "str | None":
        return (x.name if callee_side and isinstance(x, GenericPlaceholderSpec) and x.name in binds
                else None)

    def conflict(l, r, binds, why: str):
        where = (r if r is not None else l).line_ref
        return None, binds, [Error(where, f"cannot merge {_type_str(l)} with {_type_str(r)}: {why}")]

    def named(name: str, other, binds, holder_left: bool):
        """A named hole meeting `other`; `holder_left` says which side it is on."""
        bound = binds[name]
        if bound is None:
            if is_hole(other, binds, False):
                return GenericPlaceholderSpec(other.line_ref if other is not None else None, name), binds, []
            return other, {**binds, name: other}, []
        # Bound: agree with it — holes inside the binding fill, nothing widens
        # it. Both sides are the reference site's types now, so no name in
        # them is a named hole (`S@drain = S@drain` in a self-recursive call
        # is the caller's own S, a real type there).
        m, _none, errs = (go(bound, other, {}, True, True) if holder_left
                          else go(other, bound, {}, True, True))
        if errs:
            return None, binds, errs
        return m, {**binds, name: m}, []

    def args(l_args, r_args, binds, cl):
        """Invariant generic arguments; an argument list left unspelled is all holes."""
        if not l_args:
            return tuple(r_args), binds, []
        if not r_args:
            return tuple(l_args), binds, []
        if len(l_args) != len(r_args):
            return None, binds, [Error(l_args[0].line_ref, "cannot merge: generic argument counts differ")]
        out, errs = [], []
        for la, ra in zip(l_args, r_args):
            m, binds, e = go(la, ra, binds, True, cl)
            out.append(m)
            errs += e
        return (None if errs else tuple(out)), binds, errs

    def go(l, r, binds, invariant: bool, cl: bool):
        name = named_name(l, binds, cl)
        if name is not None:
            return named(name, r, binds, True)
        name = named_name(r, binds, not cl)
        if name is not None:
            return named(name, l, binds, False)
        if is_hole(l, binds, cl):
            return r, binds, []
        if is_hole(r, binds, not cl):
            return l, binds, []
        if isinstance(l, CombinationSpec) or isinstance(r, CombinationSpec):
            return unions(l, r, binds, invariant, cl)
        # A 1-tuple is its element.
        if isinstance(l, TupleSpec) and len(l.entries) == 1 and not isinstance(r, TupleSpec):
            return go(l.entries[0].type, r, binds, invariant, cl)
        if isinstance(r, TupleSpec) and len(r.entries) == 1 and not isinstance(l, TupleSpec):
            return go(l, r.entries[0].type, binds, invariant, cl)
        if isinstance(l, GenericPlaceholderSpec) or isinstance(r, GenericPlaceholderSpec):
            # In scope on both sides: a real type, equal only to itself.
            return (l, binds, []) if l == r else conflict(l, r, binds, "different types")
        if isinstance(l, TupleSpec) and isinstance(r, TupleSpec):
            return tuples(l, r, binds, invariant, cl)
        if isinstance(l, EnumSpec) and isinstance(r, EnumSpec):
            return enums(l, r, binds, invariant, cl)
        if isinstance(l, ClassSpec) and isinstance(r, ClassSpec):
            return classes(l, r, binds, invariant, cl)
        if isinstance(l, CallableSpec) and isinstance(r, CallableSpec):
            p, binds, pe = go(r.parameters, l.parameters, binds, invariant, not cl)   # reversed
            res, binds, re_ = go(l.result, r.result, binds, invariant, cl)
            if pe or re_:
                return None, binds, pe + re_
            return dataclasses.replace(l, parameters=p, result=res), binds, []
        return (l, binds, []) if l == r else conflict(l, r, binds, "different types")

    def tuples(l, r, binds, invariant, cl):
        binding = bind_tuple_entries(l.entries, [en.name for en in r.entries])
        if binding is None:
            return conflict(l, r, binds, "tuple shapes differ")
        out, errs = [], []
        for le, b in zip(l.entries, binding):
            if b is None:
                out.append(le)
                continue
            m, binds, e = go(le.type, r.entries[b].type, binds, invariant, cl)
            out.append(dataclasses.replace(le, type=m, name=le.name or r.entries[b].name))
            errs += e
        return (None if errs else dataclasses.replace(l, entries=tuple(out))), binds, errs

    def enums(l, r, binds, invariant, cl):
        if l.root_name != r.root_name:
            return conflict(l, r, binds, "different enums")
        if widen_views:
            if not l.valid_leaf_names >= r.valid_leaf_names:
                l = dataclasses.replace(l, valid_leaf_names=l.valid_leaf_names | r.valid_leaf_names)
        elif invariant and l.valid_leaf_names != r.valid_leaf_names:
            return conflict(l, r, binds, "different views of one enum are different types")
        elif not l.valid_leaf_names >= r.valid_leaf_names:
            return conflict(l, r, binds, "the receiver cannot hold every variant of the value")
        a, binds, errs = args(l.type_params, r.type_params, binds, cl)
        return (None if errs else dataclasses.replace(l, type_params=a)), binds, errs

    def classes(l, r, binds, invariant, cl):
        if l.name == r.name:
            a, binds, errs = args(l.type_params, r.type_params, binds, cl)
            return (None if errs else dataclasses.replace(l, type_params=a)), binds, errs
        if invariant:
            return conflict(l, r, binds, "different types")
        # Lift the value to the receiver's head along its recorded ancestry.
        import pyast.statement as st
        found = resolver.find_type(r.name)
        if len(found) != 1 or not isinstance(found[0].statement, st.ClassStatement):
            return conflict(l, r, binds, "unrelated types")
        cls = found[0].statement
        if cls._all_parents is None:
            return l, binds, []                    # ancestry not known yet: nothing to add
        ancestor = next((p for p in cls._all_parents
                         if isinstance(p, ClassSpec) and p.name == l.name), None)
        if ancestor is None:
            return conflict(l, r, binds, "the value's class does not implement the receiver")
        own = {p.name: a for p, a in zip(cls.type_params, r.type_params)}
        return go(l, substitute_placeholders(ancestor, own, resolver), binds, False, cl)

    def unions(l, r, binds, invariant, cl):
        """A union is a SET. Value members pair with receiver members first;
        then a single callee-side named hole takes what is left by set
        difference — on the value side the receiver members nobody matched,
        on the receiver side the value members nobody placed (the
        error-growing `E | ParseError` pattern). An anonymous receiver hole
        stands for the rest and becomes what it took. Several holes on one
        side have no partition and stay as they are."""
        l_members = list(l.repr_members()) if isinstance(l, CombinationSpec) else [l]
        r_members = list(r.repr_members()) if isinstance(r, CombinationSpec) else [r]
        if not isinstance(l, CombinationSpec):
            # Every member of the value must fit the one receiver.
            out, errs = l, []
            for rm in r_members:
                out, binds, e = go(out, rm, binds, invariant, cl)
                errs += e
                if out is None:
                    break
            return (None if errs else out), binds, errs

        def left_hole(lm) -> bool:
            return is_hole(lm, binds, cl) or named_name(lm, binds, cl) is not None
        r_holes = [rm for rm in r_members if named_name(rm, binds, not cl) is not None]
        matched: set[int] = set()
        absorbed: list[TypeSpec] = []
        errs: list[Error] = []
        for rm in r_members:
            if any(rm is h for h in r_holes):
                continue
            for i, lm in enumerate(l_members):
                if left_hole(lm):
                    continue
                m, b2, e = go(lm, rm, binds, invariant, cl)
                if not e:
                    l_members[i], binds = m, b2
                    matched.add(i)
                    break
            else:
                if any(left_hole(lm) for lm in l_members):
                    absorbed.append(rm)
                else:
                    errs += conflict(l, rm, binds, "the receiver has no member for it")[2]

        def as_type(members):
            return members[0] if len(members) == 1 else CombinationSpec(l.line_ref, tuple(members))

        # A value-side named hole: the receiver members nobody matched.
        if len(r_holes) == 1:
            rest = [lm for i, lm in enumerate(l_members) if i not in matched and not left_hole(lm)]
            if rest:
                _m, binds, e = named(named_name(r_holes[0], binds, not cl), as_type(rest), binds, False)
                errs += e
                matched.update(i for i, lm in enumerate(l_members) if any(lm is x for x in rest))
        # A receiver-side hole: the value members nobody placed.
        l_named = [lm for lm in l_members if named_name(lm, binds, cl) is not None]
        if absorbed and len(l_named) == 1 and not any(is_hole(lm, binds, cl) for lm in l_members):
            _m, binds, e = named(l_named[0].name, as_type(absorbed), binds, True)
            errs += e
        if invariant and not errs and any(i not in matched and not left_hole(lm)
                                          for i, lm in enumerate(l_members)):
            errs += conflict(l, r, binds, "different unions")[2]
        if errs:
            return None, binds, errs
        members = [lm for lm in l_members if not left_hole(lm)] + absorbed if absorbed else l_members
        out = CombinationSpec(l.line_ref, tuple(members)).repr_members()
        return (out[0] if len(out) == 1 else CombinationSpec(l.line_ref, tuple(out))), binds, []

    return go(left, right, dict(bindings), False, callee_left)


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
    # Idempotent: a type meets itself. Every rule below already agrees except
    # the union's set-wise one, which has no ground ids to compare for a union
    # holding placeholder-bearing members (`Leaf<T> | Branch<T>`).
    if a == b:
        return a
    # ClassSpec / generic EnumSpec: a generic instantiation, refined by its type
    # arguments positionally. The FAMILY question is identity-by-name (identity
    # vs state, user ruling): root name — plus, for enums, the narrowing
    # (valid/all leaf names), which is genuine identity. Full equality now
    # includes type_params, so it can no longer double as the family check —
    # `Result<Int,_>` and `Result<Int,Bool>` are UNEQUAL (correctly), and this
    # rule is what refines the hole instead.
    if (isinstance(a, ClassSpec) and isinstance(b, ClassSpec)
            and a.name == b.name and len(a.type_params) == len(b.type_params)):
        return _meet_params(a, a.type_params, b.type_params)
    if (isinstance(a, EnumSpec) and isinstance(b, EnumSpec)
            and a.root_name == b.root_name
            and a.all_leaf_names == b.all_leaf_names
            and len(a.type_params) == len(b.type_params)):
        # Same enum, possibly different VIEWS — a leaf-typed construction
        # meeting the root (or a sibling leaf) from another flow. Views JOIN:
        # the union of the valid leaf sets is what both flows satisfy, and
        # every view shares one representation (the enum-encoding
        # principle), so the join costs nothing.
        joined = (a if a.valid_leaf_names == b.valid_leaf_names
                  else dataclasses.replace(
                      a, valid_leaf_names=a.valid_leaf_names | b.valid_leaf_names))
        return (_meet_params(joined, a.type_params, b.type_params)
                if a.type_params else joined)
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


def join(a: "TypeSpec | None", b: "TypeSpec | None") -> "TypeSpec | None":
    """The type of a branch (a `match`, a `?:`) whose sides yield `a` and `b`:
    the same type when they agree, otherwise their flattened SET UNION. Total —
    a branch always has a type; only the receiver can reject it.

    Pure set semantics, nothing cleverer (user ruling 2026-07-07): NO common-
    parent search (`Child1 ⊔ Child2` = `Child1|Child2`, never their base), NO
    field-wise tuple merging (`String ⊔ (String, Int)` = `String|(String, Int)`;
    heterogeneous tuple arms converge through a DECLARED receiver type threading
    into each arm, not through the join), NO assignability absorption. The one
    collapse is the set's own: flatten + dedupe (repr_members), so a member
    joined with its own union is that union (`A ⊔ (A|None)` = `A|None`) and
    `A ⊔ A` is `A`. Unlike `meet` — which REFINES and conflicts on incompatible
    leaves — join never fails."""
    if a is None:
        return b
    if b is None:
        return a
    if a == b:
        return a
    members = CombinationSpec(a.line_ref, (a, b)).repr_members()
    return members[0] if len(members) == 1 else CombinationSpec(a.line_ref, members)


def converge(types: "list[TypeSpec]", resolver: "g.Resolver") -> "TypeSpec | None":
    """The one type all of `types` fit: the same type, the widest of them,
    their enum's root, or the one interface their classes share."""
    first = types[0]
    if all(x == first for x in types[1:]):
        return first
    for wide in types:
        if all(x == wide or trivially_assignable_equals(resolver, wide, x) is True for x in types):
            return wide
    if all(isinstance(x, EnumSpec) for x in types):
        same_enum = len({(x.root_name, x.type_params) for x in types}) == 1
        return dataclasses.replace(first, valid_leaf_names=frozenset(first.all_leaf_names)) if same_enum else None
    if all(isinstance(x, ClassSpec) for x in types):
        shared = _shared_interfaces(types, resolver)
        return shared[0] if len(shared) == 1 else None
    return None


def _shared_interfaces(specs: "list[ClassSpec]", resolver: "g.Resolver") -> "list[ClassSpec]":
    """The interfaces every class implements, in name order; empty while any
    inheritance graph is unbuilt."""
    import pyast.statement as s
    common: set[str] | None = None
    by_name: dict[str, ClassSpec] = {}
    for spec in specs:
        found = resolver.find_type(spec.name)
        if (not found.complete or len(found) != 1
                or not isinstance(found[0].statement, s.ClassStatement)
                or found[0].statement._all_parents is None):
            return []
        names = set()
        for parent in found[0].statement._all_parents:
            name = getattr(parent, "name", None)
            if name is not None and name != spec.name:
                names.add(name)
                by_name[name] = parent
        common = names if common is None else common & names
    return [by_name[name] for name in sorted(common or ())]


def fits_shape(shape: "TypeSpec", target: "TypeSpec", names: "set[str]",
               resolver: "g.Resolver") -> bool:
    """Does binding `names` in `shape` make it exactly `target`? Compared
    against `target` with ITS placeholders made opaque, so `names` bind to
    ground parts and no scope question arises; the rest of `shape` must match
    as it stands."""
    opaque = with_opaque_placeholders(target, resolver)
    mapping = unify_generic(shape, opaque, names)
    return (mapping is not None and with_opaque_placeholders(
        substitute_placeholders(shape, mapping, resolver), resolver) == opaque)


def branch_type(types: "list[TypeSpec | None]", resolver: "g.Resolver") -> "TypeSpec | None":
    """A ternary's or match's type: its branches converged, else their union.

    An arm whose type holds a placeholder that is NOT in scope — a generic
    call that bound nothing, `List()` — has only a SHAPE: `List<T>` names
    List's own parameter, which means nothing here. Such an arm FITS a sibling
    when binding its free placeholders makes it that sibling (its in-scope
    placeholders must match exactly). It takes the one ground sibling it fits;
    with none, the earliest arm it fits — so shapes of one family collapse to
    one instead of standing as a union of holes; with several ground ones it
    is ambiguous and stays as it is. The candidates are the arms' MEMBERS: the
    branch's type is their set union, so a `List<Spec>` inside a sibling's
    `List<Spec> | None` is as good a sibling as a bare one. Inside the generic
    itself the placeholder IS a type, and nothing is filled."""
    known = [x for x in types if x is not None]
    if not known:
        return None

    def fill(arm: "TypeSpec") -> "TypeSpec":
        free = {n for n in placeholder_names_in(arm) if not resolves_in_scope(n, resolver)}
        if not free:
            return arm
        members = [m for x in known
                   for m in (x.repr_members() if isinstance(x, CombinationSpec) else (x,))]
        fitting = [x for x in members if fits_shape(arm, x, free, resolver)]
        ground = {x for x in fitting if not has_free_placeholders(x, resolver)}
        if ground:
            return ground.pop() if len(ground) == 1 else arm
        return fitting[0] if fitting else arm

    known = [fill(x) for x in known]
    converged = converge(known, resolver)
    if converged is not None:
        return converged
    union = known[0]
    for x in known[1:]:
        union = join(union, x)
    return union


def refine_widening(current: "TypeSpec | None", resolver: "g.Resolver",
                    infer: "Callable[[], TypeSpec | None]") -> "TypeSpec | None":
    """`refine` for a type inferred from a source that can WIDEN across passes.

    A match/branch broadens its arms to their least upper bound, and that grows
    as arms resolve late (`A`, then `A|None`). Plain `refine` latches the first
    concrete view and its `meet` rejects the wider one as a conflict, freezing
    the narrow type. So any receiver inferring from such a source — an undeclared
    return, an untyped `let`, a destructure target — must be free to WIDEN.

    The trigger is purely fresh-vs-stored: re-derive every pass and adopt the
    fresh view iff it is a STRICT superset (assignable from the stored type, not
    the reverse). The type can only grow, so no oscillation (a flip-flop needs
    strict widening both ways) and no equivalent-spelling churn (equivalence
    fails the strictness test); growth is bounded by the program's finite member
    types, so the fixpoint terminates. Deliberately NOT keyed on whether the
    source AST changed: a receiver's type can widen while its own expression is
    value-equal (the widening happened in a callee's statement), so an AST gate
    strands chained inference at the narrow view."""
    refined = refine(current, resolver, infer)
    if refined is not None and refined.is_concrete():
        fresh = infer()
        # A fresh type still holding a hole is not wider, only less finished:
        # adopted, the hole would outlive every later, complete answer.
        if (fresh is not None and fresh.is_concrete()
                and not has_free_placeholders(fresh, resolver)
                and not has_missing_arguments(fresh, resolver)
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

    Gate — refinable only while `current` is missing (None), carries an
    out-of-scope placeholder blank, or names a generic without its arguments
    (a shape — `has_missing_arguments`); anything else is finished and returned
    untouched with `infer` never called (which is why `infer` is a callable:
    a settled type pays nothing per pass). In particular a NON-CONCRETE
    `current` is a DECLARATION whose names haven't resolved yet — its own
    compile resolves it and check owns any mismatch; inference never
    overwrites it. Only inference-stored types can carry a free placeholder,
    so the gate reopens exactly for inference's own partial answers.
    Threshold — an inferred view is adopted only if concrete: placeholder
    blanks may travel across a statement boundary and fill later, but an
    unresolved NAME may not (a callee's raw `T` would land in a scope that
    cannot resolve it). Merge — holes fill by `merge` (the stored type
    receives the inference), so information only ever accumulates; a
    contradiction (check's job to report) leaves `current` unchanged.
    A stored type holding a NARROWED enum view (`List<Op{Move}>`, latched on
    an early pass) stays refinable too: generic arguments are invariant, so it
    must widen with its right-hand side rather than pin the view."""
    if (current is not None and not has_free_placeholders(current, resolver)
            and not has_missing_arguments(current, resolver)
            and not contains_narrowed_view(current)):
        return current
    inferred = infer()
    if inferred is None or not inferred.is_concrete():
        return current
    # The stored type RECEIVES the inference (docs/type-merge-design.md),
    # its narrowed views provisional; a contradiction leaves it unchanged.
    merged, _bindings, errors = merge(current, inferred, {}, resolver, widen_views=True)
    return merged if merged is not None and not errors else current


def _unify_union(generic: "CombinationSpec", concrete: "CombinationSpec",
                 placeholder_names: set[str],
                 mapping: dict[str, "TypeSpec"],
                 in_scope: "Callable[[str], bool] | None" = None) -> dict[str, "TypeSpec"] | None:
    """Union-vs-union unification. Union members are a SET, so `E | X` against
    `A | X` must solve E by set difference, never by positional alignment —
    the error-growing instance pattern (`Stream<Lexer<S,E>, T, E|ParseError>`)
    depends on it, including when E itself grounds to a union that overlaps
    the pattern's ground members (`(A|X) | X` flattens to `A | X`).

    Ground pattern members are matched (and removed) by structural equality;
    a single unbound placeholder member then binds to whatever concrete
    members remain; an already-bound placeholder makes the slot a set-equality
    CHECK against its binding. Patterns with several placeholder-bearing
    members have no set partition to exploit and keep the old positional
    alignment."""
    # Positional alignment first — the historic behaviour, which the inference
    # fixpoint's progression is tuned to (it binds a hole from its written
    # position when the members happen to align). Set-wise matching is the
    # FALLBACK for when position lies: the error-growing instance pattern
    # (`E | ParseError` against a concrete set whose E is itself a union)
    # positionally binds garbage and conflicts; only then re-match as a set.
    if len(generic.types) == len(concrete.types):
        trial: dict[str, TypeSpec] | None = dict(mapping)
        for gv, cv in zip(generic.types, concrete.types):
            trial = _unify(gv, cv, placeholder_names, trial, in_scope)
            if trial is None:
                break
        if trial is not None:
            mapping.clear()
            mapping.update(trial)
            return mapping
    gen = list(generic.repr_members())
    con = list(concrete.repr_members())
    holes = [m for m in gen
             if isinstance(m, GenericPlaceholderSpec) and m.name in placeholder_names]
    ground = [m for m in gen
              if not (isinstance(m, GenericPlaceholderSpec) and m.name in placeholder_names)]
    if len(holes) != 1 or any(placeholder_names & placeholder_names_in(m) for m in ground):
        return mapping  # no single-hole partition either: defer to the caller
    # Deferral, not failure, on any mismatch: mid-fixpoint the concrete side
    # may still hold unresolved members, and this function's contract (like
    # the leaf cases') is to leave the mapping incomplete and let the caller
    # decide — solve_trait_constraint skips an instance whose params stay
    # unbound, and the inference fixpoint simply retries once types ground.
    remaining = list(con)
    for gm in ground:
        idx = next((i for i, cm in enumerate(remaining) if cm == gm), -1)
        if idx < 0:
            return mapping  # ground pattern member absent (or not yet resolved)
        remaining.pop(idx)
    hole = holes[0]
    existing = mapping.get(hole.name)
    if existing is not None:
        # The hole is already pinned (usually by the carrier slot): this slot
        # is a consistency check, not a binding site. `existing ∪ ground` must
        # equal the concrete set: every leftover concrete member is in the
        # binding, and every binding member is in the concrete union.
        bound = list(existing.repr_members()) if isinstance(existing, CombinationSpec) else [existing]
        if all(any(rm == bm for bm in bound) for rm in remaining) \
                and all(any(bm == cm for cm in con) for bm in bound):
            return mapping
        return mapping if any(_is_hole(cm) for cm in con) else None
    if not remaining:
        # `E | X` against bare `X`: E could be any subset of the matched
        # members — ambiguous, so leave it for another slot to pin.
        return mapping
    mapping[hole.name] = remaining[0] if len(remaining) == 1 \
        else CombinationSpec(generic.line_ref, tuple(remaining))
    return mapping


def unify_generic(generic: "TypeSpec", concrete: "TypeSpec",
                  placeholder_names: set[str],
                  mapping: dict[str, "TypeSpec"] | None = None,
                  in_scope: "Callable[[str], bool] | None" = None) -> dict[str, "TypeSpec"] | None:
    """Match a generic type tree against a concrete type tree; return a
    {placeholder_name: concrete_type} mapping, or None if they don't unify.

    Only recognises placeholders whose name appears in `placeholder_names`.
    Unknown / unresolved branches are skipped (return the current mapping
    unchanged) — the caller should treat a partial mapping as a failure if
    every placeholder must be resolved. `in_scope` is the use site's scope
    test (resolves_in_scope): a concrete-side placeholder that passes it is a
    real type there and may be bound to.

    A callable's parameter is contravariant: `(:Shape): Int` is a fine
    `(:Circle): Int`. So it binds only a placeholder that appears nowhere
    else, and otherwise may only refine a binding (names, holes), never widen
    a view.
    """
    if mapping is None:
        mapping = {}
    covariant = _without_callable_params(generic)
    mapping = _unify(covariant, concrete, placeholder_names, mapping, in_scope)
    if mapping is None or covariant is generic:
        return mapping
    upper = _unify(generic, concrete, placeholder_names, {}, in_scope) or {}
    elsewhere = placeholder_names_in(covariant)
    for name, spec in upper.items():
        existing = mapping.get(name)
        if existing is None:
            if name not in elsewhere:
                mapping[name] = spec
            continue
        merged = meet(existing, spec)
        if isinstance(merged, TypeSpec) and not contains_narrowed_view(existing):
            mapping[name] = merged
    return mapping


def _without_callable_params(spec: "TypeSpec") -> "TypeSpec":
    def blank(_, thing):
        if isinstance(thing, CallableSpec) and isinstance(thing.parameters, TupleSpec):
            entries = tuple(dataclasses.replace(en, type=None) for en in thing.parameters.entries)
            return dataclasses.replace(thing, parameters=dataclasses.replace(thing.parameters, entries=entries))
        return rw.UNCHANGED
    return rw.resolved(spec.search_and_replace(None, blank), spec)


def _unify(generic: "TypeSpec", concrete: "TypeSpec",
           placeholder_names: set[str],
           mapping: dict[str, "TypeSpec"],
           in_scope: "Callable[[str], bool] | None") -> dict[str, "TypeSpec"] | None:

    if isinstance(generic, GenericPlaceholderSpec) and generic.name in placeholder_names:
        # A concrete-side placeholder pins nothing down when it is one of this
        # callee's OWN params (binding to itself) or another declaration's
        # unbound leftover (a hole). But an ENCLOSING generic's parameter, in
        # scope at the use site, is a real type there: inside `shorter<T, U>`,
        # `isEnd(b)` with `b: Chain<U>` binds isEnd's T to U. Refusing it left
        # the callee's own placeholder behind, which monomorphisation then
        # completed by bare NAME to the host's T — a silent miscompile. Without
        # a scope test (callers outside use-site inference) every placeholder
        # stays a hole.
        if isinstance(concrete, GenericPlaceholderSpec) and (
                in_scope is None or concrete.name in placeholder_names
                or not in_scope(concrete.name)):
            return mapping
        # Nor to a spec still carrying raw NamedSpec spellings (an uncompiled
        # signature view): those names must not escape their declaring scope
        # (see _contains_named_spec). DEFER — the fixpoint retries once the
        # callee's signature grounds.
        if _contains_named_spec(concrete):
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
            m = _unify(gp, cp, placeholder_names, m, in_scope)
            if m is None:
                return None
        return m

    # Generic ENUM instances — `List<T>` vs `List<Thing>`, `Dict<K,V>` vs a
    # concrete Dict — unify through their type arguments exactly like classes.
    # This is how a call such as `head(l)` binds T from the container argument
    # alone. type_params is empty on a monomorphised (or non-generic) enum:
    # when either side lacks it there is nothing to walk, and the
    # mapping passes through unchanged — deferral, not failure, as everywhere
    # else in this function.
    if isinstance(generic, EnumSpec) and isinstance(concrete, EnumSpec):
        if generic.root_name != concrete.root_name:
            return mapping
        if (not generic.type_params
                or len(generic.type_params) != len(concrete.type_params)):
            return mapping
        m = mapping
        for gp, cp in zip(generic.type_params, concrete.type_params):
            m = _unify(gp, cp, placeholder_names, m, in_scope)
            if m is None:
                return None
        return m

    # Two still-unresolved spellings of the same generic type: infer through
    # the written type arguments (`Wrap<T>` vs `Wrap<Leaf>` before either
    # resolves). Same-name-only, same deferral rules as the branches above.
    if isinstance(generic, NamedSpec) and isinstance(concrete, NamedSpec):
        if generic.name != concrete.name:
            return mapping
        if (not generic.type_params
                or len(generic.type_params) != len(concrete.type_params)):
            return mapping
        m = mapping
        for gp, cp in zip(generic.type_params, concrete.type_params):
            m = _unify(gp, cp, placeholder_names, m, in_scope)
            if m is None:
                return None
        return m

    if isinstance(generic, TupleSpec) and isinstance(concrete, TupleSpec):
        # Pair entries via the shared binding, so named/defaulted arguments
        # unify against the field they BIND (positional zip would infer a
        # placeholder from the wrong field). Default-filled fields contribute
        # nothing — a default is a literal, never placeholder-typed.
        binding = bind_tuple_entries(generic.entries, [en.name for en in concrete.entries])
        if binding is None:
            return mapping
        m = mapping
        for ge, b in zip(generic.entries, binding):
            if b is None:
                continue
            ce = concrete.entries[b]
            if ge.type is None or ce.type is None:
                continue
            m = _unify(ge.type, ce.type, placeholder_names, m, in_scope)
            if m is None:
                return None
        return m

    if isinstance(generic, CombinationSpec) and isinstance(concrete, CombinationSpec):
        return _unify_union(generic, concrete, placeholder_names, mapping, in_scope)

    if isinstance(generic, CallableSpec) and isinstance(concrete, CallableSpec):
        m = _unify(generic.parameters, concrete.parameters, placeholder_names, mapping,
                          in_scope)
        if m is None:
            return None
        if generic.result is not None and concrete.result is not None:
            m = _unify(generic.result, concrete.result, placeholder_names, m, in_scope)
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
