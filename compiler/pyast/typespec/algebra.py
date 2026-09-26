"""The type algebra: the algorithms over pyast/typespec/specs.py representations.

Everything here is a pure function of specs (+ a read-only resolver for scope
questions): substitution, placeholder scanning, the one directional type
`merge` (docs/type-merge-design.md) and the refinement rules the compile
fixpoint builds on it, and where-constraint solving against trait instances.
No spec class calls into this module; the dependency is strictly specs <-
algebra.
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
    bind_tuple_entries,
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
    the root (or a wider view), and a widening merge joins views."""
    return (isinstance(spec, EnumSpec)
            and spec.valid_leaf_names < frozenset(spec.all_leaf_names))


def contains_narrowed_view(spec: "TypeSpec | None") -> bool:
    """True when a narrowed enum view appears anywhere in `spec` — `Circle`
    itself, or the `Op{Move}` inside a stored `List<Op{Move}>`. Such an
    inferred type is provisional: a use-site binding re-infers against its
    expected type, and a stored let/return type keeps refining, so the merge
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

    def named(name: str, other, binds, holder_left: bool, invariant: bool, wv: bool):
        """A named hole meeting `other`; `holder_left` says which side it is on."""
        bound = binds[name]
        if bound is None:
            # Nothing to bind yet — a hole, or a type still holding a raw
            # name that only means something in its declaring scope.
            if is_hole(other, binds, False) or _contains_named_spec(other):
                return GenericPlaceholderSpec(other.line_ref if other is not None else None, name), binds, []
            return other, {**binds, name: other}, []
        # Bound: agree with it — holes inside the binding fill, nothing widens
        # it. Both sides are the reference site's types now, so no name in
        # them is a named hole (`S@drain = S@drain` in a self-recursive call
        # is the caller's own S, a real type there).
        if holder_left:
            m, _none, errs = go(bound, other, {}, invariant, True, wv)
            return (None, binds, errs) if errs else (m, {**binds, name: m}, [])
        # On the value side: the same type with its holes filled, or —
        # outside generic arguments — a binding that fits a wider receiver as
        # it is (a lambda over `String | ()` takes T = String; T stays String).
        filled, _none, errs = go(bound, other, {}, True, True, wv)
        if not errs:
            return filled, {**binds, name: filled}, []
        if invariant:
            return None, binds, errs
        m, _none, errs = go(other, bound, {}, False, True, wv)
        return (None, binds, errs) if errs else (m, binds, [])

    def args(l_args, r_args, binds, cl, wv):
        """Invariant generic arguments; an argument list left unspelled is all holes."""
        if not l_args:
            return tuple(r_args), binds, []
        if not r_args:
            return tuple(l_args), binds, []
        if len(l_args) != len(r_args):
            return None, binds, [Error(l_args[0].line_ref, "cannot merge: generic argument counts differ")]
        out, errs = [], []
        for la, ra in zip(l_args, r_args):
            m, binds, e = go(la, ra, binds, True, cl, wv)
            out.append(m)
            errs += e
        return (None if errs else tuple(out)), binds, errs

    def go(l, r, binds, invariant: bool, cl: bool, wv: bool):
        name = named_name(l, binds, cl)
        if name is not None:
            return named(name, r, binds, True, invariant, wv)
        name = named_name(r, binds, not cl)
        if name is not None:
            return named(name, l, binds, False, invariant, wv)
        if is_hole(l, binds, cl):
            return r, binds, []
        if is_hole(r, binds, not cl):
            return l, binds, []
        if isinstance(l, CombinationSpec) or isinstance(r, CombinationSpec):
            return unions(l, r, binds, invariant, cl, wv)
        # A 1-tuple is its element.
        if isinstance(l, TupleSpec) and len(l.entries) == 1 and not isinstance(r, TupleSpec):
            return go(l.entries[0].type, r, binds, invariant, cl, wv)
        if isinstance(r, TupleSpec) and len(r.entries) == 1 and not isinstance(l, TupleSpec):
            return go(l, r.entries[0].type, binds, invariant, cl, wv)
        if isinstance(l, GenericPlaceholderSpec) or isinstance(r, GenericPlaceholderSpec):
            # In scope on both sides: a real type, equal only to itself.
            return (l, binds, []) if l == r else conflict(l, r, binds, "different types")
        if isinstance(l, TupleSpec) and isinstance(r, TupleSpec):
            return tuples(l, r, binds, invariant, cl, wv)
        if isinstance(l, EnumSpec) and isinstance(r, EnumSpec):
            return enums(l, r, binds, invariant, cl, wv)
        if isinstance(l, ClassSpec) and isinstance(r, ClassSpec):
            return classes(l, r, binds, invariant, cl, wv)
        if isinstance(l, CallableSpec) and isinstance(r, CallableSpec):
            # Reversed, and never widening: a callable parameter only fills
            # a provisional view (`map(circles, (v) => named(v))` keeps T =
            # Circle though the lambda takes a Shape).
            p, binds, pe = go(r.parameters, l.parameters, binds, invariant, not cl, False)
            res, binds, re_ = go(l.result, r.result, binds, invariant, cl, wv)
            if pe or re_:
                return None, binds, pe + re_
            return dataclasses.replace(l, parameters=p, result=res), binds, []
        return (l, binds, []) if l == r else conflict(l, r, binds, "different types")

    def tuples(l, r, binds, invariant, cl, wv):
        binding = bind_tuple_entries(l.entries, [en.name for en in r.entries])
        if binding is None:
            return conflict(l, r, binds, "tuple shapes differ")
        out, errs = [], []
        for le, b in zip(l.entries, binding):
            if b is None:
                out.append(le)
                continue
            m, binds, e = go(le.type, r.entries[b].type, binds, invariant, cl, wv)
            out.append(dataclasses.replace(le, type=m, name=le.name or r.entries[b].name))
            errs += e
        return (None if errs else dataclasses.replace(l, entries=tuple(out))), binds, errs

    def enums(l, r, binds, invariant, cl, wv):
        if l.root_name != r.root_name:
            return conflict(l, r, binds, "different enums")
        if wv:
            if not l.valid_leaf_names >= r.valid_leaf_names:
                l = dataclasses.replace(l, valid_leaf_names=l.valid_leaf_names | r.valid_leaf_names)
        elif invariant and l.valid_leaf_names != r.valid_leaf_names:
            return conflict(l, r, binds, "different views of one enum are different types")
        elif not l.valid_leaf_names >= r.valid_leaf_names:
            return conflict(l, r, binds, "the receiver cannot hold every variant of the value")
        a, binds, errs = args(l.type_params, r.type_params, binds, cl, wv)
        return (None if errs else dataclasses.replace(l, type_params=a)), binds, errs

    def classes(l, r, binds, invariant, cl, wv):
        if l.name == r.name:
            a, binds, errs = args(l.type_params, r.type_params, binds, cl, wv)
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
            # Not known yet is not a fit: the fixpoint asks again once it is.
            return conflict(l, r, binds, "the value's ancestry is not known yet")
        ancestor = next((p for p in cls._all_parents
                         if isinstance(p, ClassSpec) and p.name == l.name), None)
        if ancestor is None:
            return conflict(l, r, binds, "the value's class does not implement the receiver")
        own = {p.name: a for p, a in zip(cls.type_params, r.type_params)}
        return go(l, substitute_placeholders(ancestor, own, resolver), binds, False, cl, wv)

    def unions(l, r, binds, invariant, cl, wv):
        """A union is a SET. Value members pair with receiver members first;
        then a single callee-side named hole takes what is left by set
        difference — on the value side the receiver members nobody matched,
        on the receiver side the value members nobody placed (the
        error-growing `E | ParseError` pattern). An anonymous receiver hole
        stands for the rest and becomes what it took. Several holes on one
        side have no partition and stay as they are. A BOUND name is no hole:
        it is its binding's members, on either side (`TIn | E` with TIn = Int,
        against `Int | Oops`, leaves E the Oops; `E | ParseError` with E =
        `Never | ParseError` is `Never | ParseError`)."""
        def expanded(members, callee_side: bool) -> list:
            out: list = []
            for m in members:
                name = named_name(m, binds, callee_side)
                bound = binds[name] if name is not None else None
                spelt = ([m] if bound is None else
                         list(bound.repr_members()) if isinstance(bound, CombinationSpec) else [bound])
                out += [x for x in spelt if not any(x == o for o in out)]
            return out
        l_members = expanded(l.repr_members() if isinstance(l, CombinationSpec) else [l], cl)
        r_members = expanded(r.repr_members() if isinstance(r, CombinationSpec) else [r], not cl)
        if not isinstance(l, CombinationSpec):
            # Every member of the value must fit the one receiver.
            out, errs = l, []
            for rm in r_members:
                out, binds, e = go(out, rm, binds, invariant, cl, wv)
                errs += e
                if out is None:
                    break
            return (None if errs else out), binds, errs

        def unbound_named(lm) -> bool:
            name = named_name(lm, binds, cl)
            return name is not None and binds[name] is None

        def left_hole(lm) -> bool:
            return is_hole(lm, binds, cl) or unbound_named(lm)
        r_holes = [rm for rm in r_members if named_name(rm, binds, not cl) is not None]
        # A value member not known yet (an unresolved name) pairs with
        # nothing, and leaves the partition open: no set difference binds
        # and nothing is judged unmatched until it resolves.
        unknown = any(is_hole(rm, binds, not cl) for rm in r_members)
        matched: set[int] = set()
        absorbed: list[TypeSpec] = []
        errs: list[Error] = []
        for rm in r_members:
            if any(rm is h for h in r_holes) or is_hole(rm, binds, not cl):
                continue
            for i, lm in enumerate(l_members):
                if left_hole(lm):
                    continue
                m, b2, e = go(lm, rm, binds, invariant, cl, wv)
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
                _m, binds, e = named(named_name(r_holes[0], binds, not cl), as_type(rest), binds,
                                     False, invariant, wv)
                errs += e
                matched.update(i for i, lm in enumerate(l_members) if any(lm is x for x in rest))
        # A receiver-side hole: the value members nobody placed.
        l_named = [lm for lm in l_members if unbound_named(lm)]
        if absorbed and len(l_named) == 1 and not unknown and not any(is_hole(lm, binds, cl) for lm in l_members):
            _m, binds, e = named(l_named[0].name, as_type(absorbed), binds, True, invariant, wv)
            errs += e
            matched.update(i for i, lm in enumerate(l_members) if lm is l_named[0])
        if invariant and not errs and not unknown and any(i not in matched and not left_hole(lm)
                                          for i, lm in enumerate(l_members)):
            errs += conflict(l, r, binds, "different unions")[2]
        if errs:
            return None, binds, errs
        if not absorbed and l_members == list(l.repr_members() if isinstance(l, CombinationSpec) else [l]):
            return l, binds, []                   # nothing filled: the receiver as spelt
        members = [lm for lm in l_members if not left_hole(lm)] + absorbed if absorbed else l_members
        out = CombinationSpec(l.line_ref, tuple(members)).repr_members()
        return (out[0] if len(out) == 1 else CombinationSpec(l.line_ref, tuple(out))), binds, []

    return go(left, right, dict(bindings), False, callee_left, widen_views)


def receives(receiver: "TypeSpec", value: "TypeSpec", resolver: "g.Resolver") -> bool:
    """Does `value` fit `receiver` as it stands — both complete (nothing for
    the merge to fill on either side: a bare `List` shape is no `List<Int>`),
    and a merge that contradicts nothing?"""
    def complete(spec: "TypeSpec") -> bool:
        return (spec.is_concrete() and not has_free_placeholders(spec, resolver)
                and not has_missing_arguments(spec, resolver))
    return complete(receiver) and complete(value) and not merge(receiver, value, {}, resolver)[2]


def pattern_binding(pattern: "TypeSpec", concrete: "TypeSpec", names: "Iterable[str]",
                    resolver: "g.Resolver") -> "dict[str, TypeSpec] | None":
    """Does `concrete` fit `pattern`, whose own params `names` are its holes —
    the question every instance lookup asks (a trait instance, a drop, a
    derived equality, a generic witness)? `merge` with the pattern as the
    receiver. Returns what the pattern's params bound, or None on a
    contradiction. The binding may be partial: a param nothing pins (`E` in
    `E | Bool` against `Bool`) stays unbound, and a caller that needs every
    param bound says so."""
    _m, learned, errors = merge(pattern, concrete, {n: None for n in names}, resolver)
    return None if errors else {n: spec for n, spec in learned.items() if spec is not None}


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
    `A ⊔ A` is `A`. Unlike `merge` — which REFINES and can contradict — join
    never fails."""
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
        if all(x == wide or receives(wide, x, resolver) for x in types):
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


def branch_type(types: "list[TypeSpec | None]", resolver: "g.Resolver") -> "TypeSpec | None":
    """A ternary's or match's type: its branches converged, else their union.

    An arm whose type holds a placeholder that is NOT in scope — a generic
    call that bound nothing, `List()` — has only a SHAPE: `List<T>` names
    List's own parameter, which means nothing here. Such an arm FITS a sibling
    when merging the sibling into it gives back the sibling: the holes filled,
    nothing else changed (no lifting, no other view). It takes the one ground sibling it fits;
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
        if not has_free_placeholders(arm, resolver):
            return arm
        members = [m for x in known
                   for m in (x.repr_members() if isinstance(x, CombinationSpec) else (x,))]
        fitting = [x for x in members if merge(arm, x, {}, resolver)[0] == x]
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
    concrete view and its merge rejects the wider one as a contradiction, freezing
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


def without_callable_params(spec: "TypeSpec") -> "TypeSpec":
    def blank(_, thing):
        if isinstance(thing, CallableSpec) and isinstance(thing.parameters, TupleSpec):
            entries = tuple(dataclasses.replace(en, type=None) for en in thing.parameters.entries)
            return dataclasses.replace(thing, parameters=dataclasses.replace(thing.parameters, entries=entries))
        return rw.UNCHANGED
    return rw.resolved(spec.search_and_replace(None, blank), spec)


def bind_from_constraint_match(constraint: "ClassSpec", iface: "ClassSpec",
                               target_names: set[str]) -> dict[str, "TypeSpec"] | None:
    """Positionally match an already-substituted `where` constraint against a
    concrete instance interface, to bind type parameters that argument inference
    (or interface unification) left undetermined.

    Example: with `S` known to be `One`, the constraint `Stream<One, Int, E>`
    matched against the concrete instance `Stream<One, Int, Never>` binds
    `E = Never`. Returns the bindings for `target_names`, or None if the match is
    rejected or adds nothing.

    Strict and positional. At each position a
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
    grounded interface binds the targets wins. The match keys on the wrapper
    head, so two providers rarely match one constraint. Returns {name: type}
    for the targets, or None.

    This is the CALL-SITE (pre-monomorphisation) where-discharge; its mono-time
    counterpart is lowering/generics.py::__bind_where_params. The two are
    deliberately separate — different questions, different fact bases — see the
    design note in docs/compiler-internals.md §3."""
    # A constraint whose subject type is still a bare placeholder cannot be matched
    # — there is no concrete stream to read the error off. Wait for the fixpoint to
    # make it concrete.
    if constraint.type_params and isinstance(constraint.type_params[0], GenericPlaceholderSpec):
        return None
    for inst in instances:
        mapping = pattern_binding(inst.interface, constraint, inst.param_names, resolver)
        if mapping is None or set(inst.param_names) - set(mapping):
            continue  # the instance's params are not all fixed by the constraint
        grounded = substitute_placeholders(inst.interface, mapping, resolver) if mapping else inst.interface
        if isinstance(grounded, ClassSpec):
            binding = bind_from_constraint_match(constraint, grounded, target_names)
            if binding:
                return binding
    return None
