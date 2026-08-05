"""`[hashed]` — cache a structural hash inside the value (plan §3b).

Two annotations, one feature:

  * `[hashed]` on an ENUM: every leaf object gains a hidden `$hash: Int32`
    directly after the vtable pointer (the layout half lives in
    EnumStatement.global_codegen; the boxing force in complex_enums). The
    fixed offset is what lets the runtime accessors exist once, not per type.
  * `[hashed]` on a FUNCTION `(v: T): Int32`, T the hashed enum or a variant
    of it: THIS pass splits the function in two —

        fun f(v: T): Int32                      # the original name: the wrap
          let $hcache = __builtin_op__<int32>("yafl_hash_peek", v)
          ret $hcache == 0i32
            ? __builtin_op__<int32>("yafl_hash_store", v, f$hraw(v))
            : $hcache

    with the original body moved to the hidden sibling `f$hraw`. Self-calls
    inside the body still name `f`, so a recursive hash reaches CHILD nodes
    through their caches — that is the whole point.

Nothing else can reach the slot: the builtins appear only in the code this
pass emits, so no user program can observe the empty-versus-filled
nondeterminism.

Validation is here too, so the rules live in one file: `[hashed]` is
enum-only (a flattened class value has nowhere to keep a slot), and a
`[hashed]` function takes exactly one parameter of a hashed enum type and
returns Int32.
"""
from __future__ import annotations

import dataclasses

import pyast.expression as e
import pyast.statement as s
import pyast.typespec as t
import pyast.resolver as g
from parsing.parselib import Error


def lower_hashed(statements: list[s.Statement]) -> tuple[list[s.Statement], list[Error], bool]:
    resolver = g.ResolverRoot(statements)
    errors: list[Error] = []

    hashed_roots: set[str] = set()
    for st in statements:
        if isinstance(st, s.EnumStatement) and "hashed" in st.attributes:
            hashed_roots.add(st.name)
        if isinstance(st, s.ClassStatement) and "hashed" in st.attributes:
            errors.append(Error(st.line_ref,
                "[hashed] applies to enum types only — a class may be "
                "flattened to a by-value struct, which has nowhere to keep "
                "the cached hash"))

    def is_hashed_type(spec: t.TypeSpec | None) -> bool:
        # The parameter may name the root or any variant; both carry the
        # ROOT's unique name in root_name, and the attribute lives on the
        # root statement.
        return isinstance(spec, t.EnumSpec) and spec.root_name in hashed_roots

    out: list[s.Statement] = []
    changed = False
    for st in statements:
        if isinstance(st, s.FunctionStatement) and "refeq" in st.attributes:
            params = st.parameters.flatten()
            ok_types = (len(params) == 2
                        and is_hashed_type(params[0].declared_type)
                        and is_hashed_type(params[1].declared_type)
                        and isinstance(params[0].declared_type, t.EnumSpec)
                        and isinstance(params[1].declared_type, t.EnumSpec)
                        and params[0].declared_type.root_name == params[1].declared_type.root_name)
            if not ok_types:
                errors.append(Error(st.line_ref,
                    "a [refeq] function must take two parameters of one "
                    "[hashed] enum type — the shortcut is a pointer compare, "
                    "which needs boxed values"))
                out.append(st)
                continue
            rt = st.return_type
            if not (isinstance(rt, t.BuiltinSpec) and rt.type_name == "bool"):
                errors.append(Error(st.line_ref,
                    "a [refeq] function must return Bool"))
                out.append(st)
                continue
            out.extend(__split_refeq(st, params[0], params[1]))
            changed = True
            continue
        if not (isinstance(st, s.FunctionStatement) and "hashed" in st.attributes):
            out.append(st)
            continue

        params = st.parameters.flatten()
        rt = st.return_type
        if len(params) != 1 or not is_hashed_type(params[0].declared_type):
            errors.append(Error(st.line_ref,
                "a [hashed] function must take exactly one parameter of a "
                "[hashed] enum type — the cache lives in that value"))
            out.append(st)
            continue
        if not (isinstance(rt, t.BuiltinSpec) and rt.type_name == "int32"):
            errors.append(Error(st.line_ref,
                "a [hashed] function must return Int32 — the cache slot is "
                "one machine word"))
            out.append(st)
            continue

        out.extend(__split(st, params[0]))
        changed = True
    return out, errors, changed


def __split(fn: s.FunctionStatement, param: s.LetStatement) -> list[s.Statement]:
    lr = fn.line_ref
    tag = lr.hash6()
    attrs = {k: v for k, v in fn.attributes.items() if k != "hashed"}
    # Path-based, collision-free: the original unique name is `path::bare@tag`;
    # the sibling reuses both parts with a suffix nothing else generates.
    bare, _at, _hash = fn.name.rpartition("@")
    raw_name = f"{bare}$hraw@{tag}"

    raw = dataclasses.replace(fn, name=raw_name, attributes=attrs)

    def int32(): return t.BuiltinSpec(lr, "int32")
    def op(name: str, *args: e.Expression) -> e.Expression:
        return e.BuiltinOpExpression(lr, int32(), e.StringExpression(lr, name),
            e.TupleExpression(lr, [e.TupleEntryExpression(None, a) for a in args]))
    def ref(name: str) -> e.Expression:
        return e.NamedExpression(lr, name)

    cache_name = f"$hcache@{tag}"
    peek = op("yafl_hash_peek", ref(param.name))
    raw_call = e.CallExpression(lr, ref(f"{bare.rpartition('::')[2]}$hraw"),
        e.TupleExpression(lr, [e.TupleEntryExpression(None, ref(param.name))]))
    store = op("yafl_hash_store", ref(param.name), raw_call)
    is_empty = e.BuiltinOpExpression(lr, t.BuiltinSpec(lr, "bool"),
        e.StringExpression(lr, "int32_test_eq"),
        e.TupleExpression(lr, [
            e.TupleEntryExpression(None, ref("$hcache")),
            e.TupleEntryExpression(None, e.IntegerExpression(lr, 0, 32))]))

    body = e.BlockExpression(lr,
        [s.LetStatement(lr, cache_name, None, {}, (), peek, int32())],
        e.TernaryExpression(lr, is_empty, store, ref("$hcache")),
        tag=None)
    wrap = dataclasses.replace(fn, attributes=attrs, body=body)
    return [wrap, raw]


def __split_refeq(fn: s.FunctionStatement, lp: s.LetStatement,
                  rp: s.LetStatement) -> list[s.Statement]:
    """`[refeq]` — plan §3c, the user's opt-in ruling. Same object means equal
    WITHOUT running the compare — sound because [hashed] values are boxed and
    immutable, so reference equality implies value equality. Opt-in is the
    whole NaN answer: a non-reflexive equality does not opt in.

        fun f(l: T, r: T): Bool                 # the original name: the wrap
          ret __builtin_op__<bool>("yafl_ref_eq", l, r)
            ? true
            : f$reraw(l, r)

    Self-calls in the moved body still name `f`, so a recursive deep compare
    short-circuits at SHARED SUBSTRUCTURE — with canonical-snapped graphs
    that is depth 1, which is what makes a precise key affordable."""
    lr = fn.line_ref
    tag = lr.hash6()
    attrs = {k: v for k, v in fn.attributes.items() if k != "refeq"}
    bare, _at, _hash = fn.name.rpartition("@")
    raw_name = f"{bare}$reraw@{tag}"
    raw = dataclasses.replace(fn, name=raw_name, attributes=attrs)

    def ref(name: str) -> e.Expression:
        return e.NamedExpression(lr, name)
    args = e.TupleExpression(lr, [e.TupleEntryExpression(None, ref(lp.name)),
                                  e.TupleEntryExpression(None, ref(rp.name))])
    same = e.BuiltinOpExpression(lr, t.BuiltinSpec(lr, "bool"),
                                 e.StringExpression(lr, "yafl_ref_eq"), args)
    raw_call = e.CallExpression(lr, ref(f"{bare.rpartition('::')[2]}$reraw"),
        e.TupleExpression(lr, [e.TupleEntryExpression(None, ref(lp.name)),
                               e.TupleEntryExpression(None, ref(rp.name))]))
    body = e.BlockExpression(lr, [],
        e.TernaryExpression(lr, same, e.BoolExpression(lr, True), raw_call),
        tag=None)
    wrap = dataclasses.replace(fn, attributes=attrs, body=body)
    return [wrap, raw]
