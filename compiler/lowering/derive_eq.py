"""Derived enum equality — every qualifying enum gets `BasicEquality` for free.

For each top-level, non-generic enum with no user-written
`BasicEquality<E>` instance, if every member type satisfies equality, this
pass synthesises

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

"Satisfies equality" is COINDUCTIVE: while checking, every candidate enum is
assumed to satisfy, so self- and mutually-recursive enums work; the
assumption set then shrinks to a fixpoint as members fail. A member satisfies
when it is a builtin/class/enum with an instance in scope, a candidate enum,
or a tuple (of an arity the stdlib instances cover) of satisfying members.
Everything else — unions, function types, generics — blocks derivation, and
notably `Spec` never derives because `PLine` has no instance: `eqSpec` keeps
sole ownership of spec equality.

Both compilers synthesise IDENTICAL statements (names and line refs derive
from the enum's own), so the AST dumps and emitted C stay byte-comparable.
"""
from __future__ import annotations

import pyast.expression as e
import pyast.statement as s
import pyast.typespec as t
import pyast.resolver as g
from pyast.match import MatchArm, MatchExpression


def derive_equality(statements: list[s.Statement]) -> tuple[list[s.Statement], bool]:
    instanced, tuple_arities = __collect_instanced(statements)

    candidates: dict[str, tuple] = {}
    for st in statements:
        if not (isinstance(st, s.EnumStatement) and not st.type_params):
            continue
        if ("e", st.name) in instanced:
            continue                       # user instance: never compete
        leaves = __collect_leaves(st, [])
        if leaves is None or not leaves:   # uninhabited variant somewhere
            continue
        candidates[st.name] = (st, leaves)

    # Coinductive fixpoint: assume every candidate satisfies, drop failures.
    ok = set(candidates)
    changed = True
    while changed:
        changed = False
        for name in sorted(ok):
            _st, leaves = candidates[name]
            if not all(__satisfies(let.declared_type, ok, instanced, tuple_arities)
                       for _leaf, fields in leaves for let in fields):
                ok.discard(name)
                changed = True

    if not ok:
        return statements, False
    out: list[s.Statement] = []
    for st in statements:
        out.append(st)
        if isinstance(st, s.EnumStatement) and st.name in ok:
            out.append(__synthesise(st, candidates[st.name][1]))
    return out, True


def __collect_instanced(statements) -> tuple[set, set]:
    """Keys of every type with a BasicEquality instance in scope, plus the
    tuple arities the generic stdlib instances cover.

    Instance PATTERNS keep their typealias spellings (`System::Int`) as
    NamedSpecs — unlike field types, which compile the alias away — so the
    key is built from the RESOLVED statement, following alias chains."""
    resolver = g.ResolverRoot(statements)
    instanced: set = set()
    tuple_arities: set = set()

    def key_of(arg, depth: int = 0):
        if isinstance(arg, t.BuiltinSpec):
            return ("b", arg.type_name)
        if isinstance(arg, t.EnumSpec):
            return ("e", arg.root_name)
        if isinstance(arg, t.ClassSpec):
            return ("c", arg.name)
        if isinstance(arg, t.NamedSpec) and depth < 8:
            found = resolver.find_type(arg.name)
            if len(found) == 1:
                target = found[0].statement
                if isinstance(target, s.TypeAliasStatement):
                    return key_of(target.type, depth + 1)
                if isinstance(target, s.ClassStatement):
                    return ("c", target.name)
                if isinstance(target, s.EnumStatement):
                    return ("e", target.name)
        return None

    def reaches_equality(pat) -> bool:
        # Equality arrives TRANSITIVELY: an instance of BasicMath<Int>
        # provides BasicEquality<Int> because BasicMath : BasicPlus |
        # BasicCompare and BasicCompare : BasicEquality. The interface's
        # _all_parents is exactly that closure.
        name = getattr(pat, "name", "")
        if not isinstance(name, str):
            return False
        if name.split("@")[0].split("$generic$")[0] == "System::BasicEquality":
            return True
        found = resolver.find_type(name)
        if len(found) != 1 or not isinstance(found[0].statement, s.ClassStatement):
            return False
        return any(isinstance(par, t.ClassSpec)
                   and par.name.split("@")[0] == "System::BasicEquality"
                   for par in (found[0].statement._all_parents or ()))

    def record(pat) -> None:
        if not getattr(pat, "type_params", ()) or not reaches_equality(pat):
            return
        arg = pat.type_params[0]
        if isinstance(arg, t.TupleSpec):
            tuple_arities.add(len(arg.entries))
            return
        k = key_of(arg)
        if k is not None:
            instanced.add(k)

    for st in statements:
        # The modern form: first-class `instance` statements.
        if isinstance(st, s.TraitInstanceStatement):
            record(st.pattern)
            continue
        # The older form: a `[trait]` let whose witness CLASS implements the
        # interface — Int/Int32/String/float equality still arrives this way.
        # Same walk __implements_trait uses post-monomorphisation.
        if (isinstance(st, s.LetStatement) and "trait" in st.attributes
                and not st.type_params and isinstance(st.declared_type, t.ClassSpec)):
            found = resolver.find_type(st.declared_type.name)
            if len(found) == 1 and isinstance(found[0].statement, s.ClassStatement):
                for parent in (found[0].statement._all_parents or ()):
                    if isinstance(parent, t.ClassSpec):
                        record(parent)
    return instanced, tuple_arities


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


def __satisfies(spec, ok: set, instanced: set, tuple_arities: set) -> bool:
    if isinstance(spec, t.BuiltinSpec):
        return ("b", spec.type_name) in instanced
    if isinstance(spec, t.EnumSpec):
        return spec.root_name in ok or ("e", spec.root_name) in instanced
    if isinstance(spec, t.ClassSpec):
        return ("c", spec.name) in instanced
    if isinstance(spec, t.TupleSpec):
        return (len(spec.entries) in tuple_arities
                and all(en.type is not None
                        and __satisfies(en.type, ok, instanced, tuple_arities)
                        for en in spec.entries))
    return False


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
