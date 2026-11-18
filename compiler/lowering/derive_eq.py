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

One question decides everything: does a type have equality — would the
calls the synthesised members make on a value of it, `==` and `hashOf`,
resolve? They are looked up as a written call is, in the enum's own scope:
the ordinary overload resolution, which finds `Payload`'s `==` for two
`Pay1`s as it would for `hPay == hPay2`. A generic instance the lookup
reaches needs its `where` clauses met, and a `where` is exact, so a tuple has
equality when its members have instances of their own. An enum with equality
never derives (idempotence), and an enum derives only when every member has
it. That is COINDUCTIVE: while checking, every candidate enum is assumed to
have equality, so self- and mutually-recursive enums work; the assumption set
then shrinks to a fixpoint as members fail. Anything without — a union, a
function type — blocks derivation, and notably `Spec` never derives
because `PLine` has no `==`: `eqSpec` keeps sole ownership of spec
equality.

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
    The same question decides every member: its `==` and `hashOf` resolve
    (`__has_equality`), or it is a candidate itself (coinductive).

    Empty while the answer is not yet complete — an instance not yet
    resolved may be the one that already covers an enum, and derivation
    must never compete with it; an enum or a candidate's field still a name
    may change every answer — and in a program that does not declare
    `System::BasicEquality` (compiled without the stdlib)."""
    if not resolver.find_type("System::BasicEquality"):
        return frozenset()
    providers = __providers(statements, resolver)
    if providers is None:
        return frozenset()

    # The lookups, once per scope and type: every candidate's fields are
    # asked about on every round of the fixpoint, and most share a type.
    finds: dict = {}
    uses: dict = {}

    def use_of(st: s.EnumStatement, spec: t.TypeSpec) -> "_Use | None":
        own_ns = st.name.rpartition("::")[0]
        scope_key = (own_ns, frozenset(x.path for x in st.imports.imports) if st.imports else frozenset())
        uid = spec.as_unique_id_str()
        if uid is not None and (scope_key, uid) in uses:
            return uses[(scope_key, uid)]
        if scope_key not in finds:
            finds[scope_key] = __finds(st._initialiser_resolver(g.scope_resolver(st, resolver)))
        scope, found = finds[scope_key]
        use = None if found is None else __use(scope, found, spec, st.line_ref)
        if uid is not None:
            uses[(scope_key, uid)] = use
        return use

    candidates: dict[str, list] = {}
    for st in statements:
        # Generic enums never derive — nor, after monomorphisation, their
        # instantiations (`Chain$generic$bigint` has no type params left, but
        # it is still an instance of a generic enum, not a source enum).
        if not (isinstance(st, s.EnumStatement) and not st.type_params
                and "$generic$" not in st.name):
            continue
        # An enum, or a candidate's field, whose type is still a name is an
        # input not known yet: the answer waits for it, as it waits for the
        # providers. Decided without it, `enum Host(hPay: Pay1)` was judged
        # while Pay1 was a name, Payload derived alone, and Host never did
        # (#136).
        if st.get_type() is None:
            return frozenset()
        # Already has equality: an instance for exactly it, in whatever form
        # it now has — written, derived, or lowered to a witness, which no
        # call finds by name — or its own `==` and `hashOf` resolve without
        # one. Derivation fills a gap, never competes.
        if __instance_exists(st.get_type(), frozenset(), providers, resolver):
            continue
        own = use_of(st, st.get_type())
        if own is None:
            return frozenset()
        if __has_equality(st.get_type(), own, frozenset(), providers, resolver):
            continue
        leaves = __collect_leaves(st, [])
        if leaves is None or not leaves:   # uninhabited variant somewhere
            continue
        if any(f.declared_type is None or t.contains_named_spec(f.declared_type)
               for _leaf, fields in leaves for f in fields):
            return frozenset()
        members = [(f.declared_type, use_of(st, f.declared_type)) for _leaf, fields in leaves for f in fields]
        if any(use is None for _spec, use in members):
            return frozenset()
        candidates[st.name] = members

    # Coinductive fixpoint: assume every candidate has equality, drop failures.
    ok = set(candidates)
    changed = True
    while changed:
        changed = False
        for name in sorted(ok):
            if not all(__has_equality(spec, use, frozenset(ok), providers, resolver)
                       for spec, use in candidates[name]):
                ok.discard(name)
                changed = True
    return frozenset(ok)


class _Use(NamedTuple):
    """What the calls a derived instance makes on a value of one type resolve
    to: `fits` when its `==` and its `hashOf` each resolve to one candidate
    that takes it, and the types a generic instance among them then needs an
    instance for, exactly — its `where`."""
    fits: bool
    needs: tuple = ()


def __finds(scope: g.Resolver) -> "tuple[g.Resolver, dict | None]":
    """`scope` with every `==` and `hashOf` it can see — or None while that
    search is incomplete, or a candidate's type is still a name: one not
    known yet may be the one a call would take."""
    from pyast.expression.access import candidate_signature
    found = {}
    for name in ("`==`", "hashOf"):
        candidates = scope.find_data(name)
        if not candidates.complete:
            return scope, None
        for x in candidates:
            sig = candidate_signature(scope, x)
            if sig is None or t.contains_named_spec(sig):
                return scope, None
        found[name] = list(candidates)
    return scope, found


def __use(scope: g.Resolver, found: dict, spec: t.TypeSpec, lr) -> _Use:
    """What the synthesised members' own calls on a value of type `spec` —
    `left.f == right.f` for a Bool, `hashOf(value.f)` for an Int32 — resolve
    to in the enum's scope: the ordinary overload resolution a written call
    gets. A generic instance is taken only when the call binds its
    parameters."""
    from pyast.expression.access import _resolve_overloads, _solve_instance_scope, candidate_signature
    one = t.TupleEntrySpec(None, spec)
    needs = []
    for name, args, result in (("`==`", (one, one), "bool"), ("hashOf", (one,), "int32")):
        want = t.CallableSpec(lr, t.TupleSpec(lr, args), t.BuiltinSpec(lr, result))
        chosen = _resolve_overloads(scope, want, found[name])
        if len(chosen) != 1:
            return _Use(False)
        x = chosen[0]
        if x.instance_params:
            solved = _solve_instance_scope(scope, x, want)
            if solved is None or len(solved.type_params) != 1:
                return _Use(False)
            needs.append(solved.type_params[0])
        elif t.trivially_assignable_equals(scope, want, candidate_signature(scope, x)) is not True:
            return _Use(False)
    return _Use(True, tuple(needs))


def __has_equality(spec, use: _Use, ok: frozenset[str], providers: list[_Provider],
                   resolver: g.Resolver) -> bool:
    """Does `spec` have equality? The calls a derived instance makes on it
    resolve, and every generic instance they reach has what its `where`
    asks for; or it is an enum deriving in this pass, assumed to while the
    fixpoint runs: its instance, once it exists, takes any value of it."""
    if spec is None:
        return False
    if isinstance(spec, t.EnumSpec) and spec.root_name in ok:
        return True
    return use.fits and all(__instance_exists(need, ok, providers, resolver) for need in use.needs)


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
            # The type it covers, or a `where` it needs, still a name: which
            # type it provides for is not known yet. Read as covering nothing,
            # a written `BasicEquality<Payload>` let Payload derive a second
            # instance beside it (#136: a program converged above a settled
            # stdlib met its own instance while the argument was a name).
            if t.contains_named_spec(iface) or any(t.contains_named_spec(w) for w in wheres):
                return False
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


def __instance_exists(spec, ok: frozenset[str], providers: list[_Provider],
                      resolver: g.Resolver) -> bool:
    """Is there an instance for exactly `spec`, as `where BasicEquality<spec>`
    asks? Some provider covers it — binding the provider's own params makes
    its pattern `spec`, compared by unique id — and every `where` holds for
    the binding; or it is an enum deriving in this pass, assumed to while the
    fixpoint runs. A `where` is exact: a level of an enum is not its root."""
    if spec is None:
        return False
    if isinstance(spec, t.EnumSpec) and spec.root_name in ok and not spec.path:
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
                   and __instance_exists(t.substitute_placeholders(w.type_params[0], mapping, resolver),
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
