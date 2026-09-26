"""Derived enum equality — every qualifying enum gets `BasicEquality` for free.

For each top-level, non-generic enum with no user-written
`BasicEquality<E>` instance, if every member type satisfies equality, the
enum's own compile (inside the fixpoint, like any other statement's extras)
synthesises

    instance [ambient] System::BasicEquality<E>
      fun `==`(left: E, right: E): Bool
        ret yafl_ref_eq(left, right) ? true : <variant-wise compare>
      fun hashOf(value: E): Int32
        let $dhc = yafl_hash_peek(value)
        ret $dhc == 0i32 ? yafl_hash_store(value, <variant-wise hash>) : $dhc

directly after the enum. The three internals are representation-aware at
codegen (a value-repr enum gets no shortcut and no cache, and still computes
correctly), so nothing here forces boxing. A user instance suppresses
derivation — the vacuum rule: derivation fills a gap, never competes.

One question decides everything: does equality already EXIST for a type —
does some instance, in whatever form it now has, cover it (with its `where`
clauses met, so a tuple has equality when its members do)? An enum for which
it does never derives (idempotence), and an enum derives only when it does
for every member. That is COINDUCTIVE: while checking, every candidate enum
is assumed to have equality, so self- and mutually-recursive enums work; the
assumption set then shrinks to a fixpoint as members fail. Anything no
instance covers — unions, function types, generic instantiations — blocks
derivation, and notably `Spec` never derives because `PLine` has no
instance: `eqSpec` keeps sole ownership of spec equality.

Both compilers synthesise IDENTICAL statements (names and line refs derive
from the enum's own), so the AST dumps and emitted C stay byte-comparable.
"""
from __future__ import annotations

import pyast.expression as e
import pyast.statement as s
import pyast.typespec as t
import pyast.resolver as g
from pyast.match import MatchArm, MatchExpression
from typing import NamedTuple


def derivable_enums(statements: list[s.Statement], resolver: g.Resolver) -> frozenset[str]:
    """The top-level enums that derive equality in this pass's program. A
    whole-program fact — ResolverRoot memoises it per pass, and each enum's
    own compile emits its instance (see EnumStatement.compile).

    IDEMPOTENT: an enum that already has equality — a written instance, a
    derived one, either of them lowered or monomorphised — never derives.
    The same question decides every member: equality must exist for it
    (`__has_equality`), or it is a candidate itself (coinductive).

    Empty while the answer is not yet complete — an instance or witness not
    yet resolved may be the one that already covers an enum, and derivation
    must never compete with it — and in a program that does not declare
    `System::BasicEquality` (compiled without the stdlib)."""
    if not resolver.find_type("System::BasicEquality"):
        return frozenset()
    providers = __providers(statements, resolver)
    if providers is None:
        return frozenset()

    candidates: dict[str, list] = {}
    for st in statements:
        # Generic enums never derive — nor, after monomorphisation, their
        # instantiations (`Chain$generic$bigint` has no type params left, but
        # it is still an instance of a generic enum, not a source enum).
        if not (isinstance(st, s.EnumStatement) and not st.type_params
                and "$generic$" not in st.name and st.get_type() is not None):
            continue
        if __has_equality(st.get_type(), frozenset(), providers, resolver):
            continue
        leaves = __collect_leaves(st, [])
        if leaves is None or not leaves:   # uninhabited variant somewhere
            continue
        candidates[st.name] = leaves

    # Coinductive fixpoint: assume every candidate has equality, drop failures.
    ok = set(candidates)
    changed = True
    while changed:
        changed = False
        for name in sorted(ok):
            if not all(__has_equality(let.declared_type, frozenset(ok), providers, resolver)
                       for _leaf, fields in candidates[name] for let in fields):
                ok.discard(name)
                changed = True
    return frozenset(ok)


def derived_instance(st: s.EnumStatement) -> s.TraitInstanceStatement:
    """The synthesised `BasicEquality<st>` instance for a derivable enum."""
    return __synthesise(st, __collect_leaves(st, []))


class _Provider(NamedTuple):
    """One source of `BasicEquality`: the type it covers, as a pattern over
    the instance's own type params, with the `where` constraints a binding
    must meet — or, once monomorphised, the covered type's unique id (the
    `$generic$` suffix of the witness's interface, by construction)."""
    params: frozenset[str]
    covers: "t.TypeSpec | str"
    wheres: tuple = ()


def __providers(statements, resolver: g.Resolver) -> "list[_Provider] | None":
    """Every source of equality in the program, in whatever form it now
    has — or None while one of them has not resolved enough to read.
    Equality arrives TRANSITIVELY: `BasicMath<Int>` provides it through the
    interface closure (`_all_parents`)."""
    out: list[_Provider] = []

    def reaches_equality(iface: t.ClassSpec) -> bool | None:
        if iface.name.split("@")[0].split("$generic$")[0] == "System::BasicEquality":
            return True
        found = resolver.find_type(iface.name)
        if len(found) != 1 or not isinstance(found[0].statement, s.ClassStatement):
            return False
        parents = found[0].statement._all_parents
        if parents is None:
            return None
        return any(isinstance(par, t.ClassSpec)
                   and par.name.split("@")[0] == "System::BasicEquality" for par in parents)

    def add(iface, params: frozenset[str], wheres: tuple) -> bool:
        """Record `iface` if it provides equality; False when it cannot be read yet."""
        if not isinstance(iface, t.ClassSpec):
            return False
        reaches = reaches_equality(iface)
        if reaches is None:
            return False
        if reaches:
            if iface.type_params:
                out.append(_Provider(params, iface.type_params[0], wheres))
            elif "$generic$" in iface.name:
                out.append(_Provider(params, iface.name.partition("$generic$")[2]))
        return True

    for st in statements:
        # First-class instances, generic ones with their `where` clauses.
        if isinstance(st, s.TraitInstanceStatement):
            if not add(st.pattern, frozenset(p.name for p in st.type_params), tuple(st.trait_params)):
                return None
        # Lowered instances: a `[trait]` let whose witness CLASS implements
        # the interface (monomorphised, its parents carry mangled names).
        elif isinstance(st, s.LetStatement) and "trait" in st.attributes and not st.type_params:
            if not isinstance(st.declared_type, t.ClassSpec):
                return None
            found = resolver.find_type(st.declared_type.name)
            if len(found) == 1 and isinstance(found[0].statement, s.ClassStatement):
                parents = found[0].statement._all_parents
                if parents is None or not all(add(par, frozenset(), ()) for par in parents):
                    return None
    return out


def __has_equality(spec, ok: frozenset[str], providers: list[_Provider],
                   resolver: g.Resolver) -> bool:
    """Does equality exist for `spec`? Some provider covers it — binding the
    provider's own params makes its pattern `spec` (compared by unique id,
    so enum views stay one type) and every `where` holds for the binding —
    or it is a candidate enum, assumed to while the fixpoint runs."""
    if spec is None:
        return False
    if isinstance(spec, t.EnumSpec) and spec.root_name in ok:
        return True
    uid = spec.as_unique_id_str()
    if uid is None:
        return False

    def covered_by(p: _Provider) -> bool:
        if isinstance(p.covers, str):
            return p.covers == uid
        mapping = t.pattern_binding(p.covers, spec, p.params, resolver)
        if mapping is None or t.substitute_placeholders(p.covers, mapping, resolver).as_unique_id_str() != uid:
            return False
        return all(isinstance(w, t.ClassSpec) and len(w.type_params) == 1
                   and w.name.split("@")[0] == "System::BasicEquality"
                   and __has_equality(t.substitute_placeholders(w.type_params[0], mapping, resolver),
                                      ok, providers, resolver)
                   for w in p.wheres)

    return any(covered_by(p) for p in providers)


def __collect_leaves(st: s.EnumStatement, inherited: list) -> "list | None":
    """(leaf unique name, all fields root-down) per constructible leaf, in
    declaration order — the same accumulation the leaf constructors use.
    None when any variant is uninhabited (no param list, no variants):
    such an enum is out of scope for v1."""
    own = inherited + list(st.parameters.flatten())
    if not st.variants:
        if not st.has_param_list:
            return None
        return [(st.name, own)]
    leaves: list = []
    for v in st.variants:
        sub = __collect_leaves(v, own)
        if sub is None:
            return None
        leaves.extend(sub)
    return leaves


# ── synthesis ────────────────────────────────────────────────────────────────

def __synthesise(st: s.EnumStatement, leaves: list) -> s.TraitInstanceStatement:
    lr = st.line_ref
    tag = lr.hash6()
    ns = st.name.rpartition("::")[0]
    iname = f"{ns}::instance$eq{tag}" if ns else f"instance$eq{tag}"
    pattern = t.NamedSpec(lr, "System::BasicEquality",
                          (t.NamedSpec(lr, st.name),))
    return s.TraitInstanceStatement(
        lr, iname, st.imports, {"ambient": None}, (),
        trait_params=(), pattern=pattern, ambient=True,
        statements=[__eq_member(st, leaves, tag),
                    __hash_member(st, leaves, tag)])


def __ref(lr, name): return e.NamedExpression(lr, name)
def __true(lr): return e.BoolExpression(lr, True)
def __false(lr): return e.BoolExpression(lr, False)


def __op(lr, rtype: str, name: str, *args) -> e.Expression:
    return e.BuiltinOpExpression(lr, t.BuiltinSpec(lr, rtype),
        e.StringExpression(lr, name),
        e.TupleExpression(lr, [e.TupleEntryExpression(None, a) for a in args]))


def __call(lr, fn: str, *args) -> e.Expression:
    return e.CallExpression(lr, e.NamedExpression(lr, fn),
        e.TupleExpression(lr, [e.TupleEntryExpression(None, a) for a in args]))


def __param(lr, name: str, type_name: str) -> s.LetStatement:
    return s.LetStatement(lr, name, None, {}, (), None, t.NamedSpec(lr, type_name))


def __destructure(lr, lets) -> s.DestructureStatement:
    return s.DestructureStatement(lr, "_", None, {}, (), None, None, lets)


def __bare(name: str) -> str:
    return name.split("@")[0]


def __eq_member(st: s.EnumStatement, leaves: list, tag: str) -> s.FunctionStatement:
    lr = st.line_ref
    left, right = __ref(lr, "left"), __ref(lr, "right")
    arms = []
    for i, (leaf_name, fields) in enumerate(leaves):
        # left is this leaf: right must be the SAME leaf with equal fields.
        # Binder names are unique PER ARM (the parser hashes per line; all of
        # this shares the enum's line, so the index does that job) — match
        # lowering makes one variable per binder name, and a shared name
        # across arms violates SSA single-definition.
        xn, yn, on = f"x{i}", f"y{i}", f"o{i}"
        if fields:
            cmp: e.Expression | None = None
            for let in fields:
                one = __call(lr, "`==`", e.DotExpression(lr, __ref(lr, xn), __bare(let.name)),
                             e.DotExpression(lr, __ref(lr, yn), __bare(let.name)))
                cmp = one if cmp is None else e.TernaryExpression(lr, cmp, one, __false(lr))
        else:
            cmp = __true(lr)
        inner_arms = [MatchArm(lr, f"{yn}@{tag}", t.NamedSpec(lr, leaf_name), cmp)]
        if len(leaves) > 1:
            inner_arms.append(MatchArm(lr, f"{on}@{tag}", t.NamedSpec(lr, st.name), __false(lr)))
        arms.append(MatchArm(lr, f"{xn}@{tag}", t.NamedSpec(lr, leaf_name),
                             MatchExpression(lr, right, arms=inner_arms)))
    body = e.BlockExpression(lr, [],
        e.TernaryExpression(lr, __op(lr, "bool", "yafl_ref_eq", left, right),
                            __true(lr), MatchExpression(lr, left, arms=arms)),
        tag=None)
    params = __destructure(lr, [__param(lr, f"left@{tag}", st.name),
                                __param(lr, f"right@{tag}", st.name)])
    return s.FunctionStatement(lr, f"`==`@{tag}", None, {}, (), params, body,
                               t.BuiltinSpec(lr, "bool"))


def __hash_member(st: s.EnumStatement, leaves: list, tag: str) -> s.FunctionStatement:
    lr = st.line_ref

    def mix(acc: e.Expression, h: e.Expression) -> e.Expression:
        return __op(lr, "int32", "int32_and",
                    __op(lr, "int32", "int32_add",
                         __op(lr, "int32", "int32_mul", acc, e.IntegerExpression(lr, 31, 32)),
                         h),
                    e.IntegerExpression(lr, 2147483647, 32))

    arms = []
    for index, (leaf_name, fields) in enumerate(leaves):
        xn = f"h{index}"
        acc: e.Expression = e.IntegerExpression(lr, index, 32)
        for let in fields:
            acc = mix(acc, __call(lr, "hashOf",
                                  e.DotExpression(lr, __ref(lr, xn), __bare(let.name))))
        arms.append(MatchArm(lr, f"{xn}@{tag}", t.NamedSpec(lr, leaf_name), acc))
    value = __ref(lr, "value")
    cache = f"$dhc@{tag}"
    body = e.BlockExpression(lr,
        [s.LetStatement(lr, cache, None, {}, (),
                        __op(lr, "int32", "yafl_hash_peek", value),
                        t.BuiltinSpec(lr, "int32"))],
        e.TernaryExpression(lr,
            __op(lr, "bool", "int32_test_eq", __ref(lr, "$dhc"), e.IntegerExpression(lr, 0, 32)),
            __op(lr, "int32", "yafl_hash_store", value, MatchExpression(lr, value, arms=arms)),
            __ref(lr, "$dhc")),
        tag=None)
    params = __destructure(lr, [__param(lr, f"value@{tag}", st.name)])
    return s.FunctionStatement(lr, f"hashOf@{tag}", None, {}, (), params, body,
                               t.BuiltinSpec(lr, "int32"))
