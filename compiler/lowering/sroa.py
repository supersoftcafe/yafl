from __future__ import annotations

# Scalar replacement of aggregates (SROA) for projection-only locals.
#
# A tuple/struct local that is *only ever field-projected* (never used whole) is
# split into one scalar local per field, so each field's liveness is tracked
# independently. This is a correctness fix, not just an optimisation: the async
# state object roots whatever is live across a suspension at whole-variable
# granularity, so a tuple held across a suspend point keeps ALL its fields alive
# — even fields that are dead there. When such a dead field is the head of a
# lazy/memoised stream, the whole spine is pinned and memory grows with the
# input (see examples/linenumbers.yafl: `src = (io, stream)` held across the
# drain because `src.io` is closed afterwards, pinning `src.stream`). After SROA
# the fields are independent locals, so only the genuinely-live one is rooted.
#
# Runs unconditionally (every -O level) just before async lowering, while the IR
# is still SSA — so every splittable local has exactly one definition.
#
# Soundness: values are immutable (SSA, pure language), so a field read taken
# eagerly right after the definition equals the same field read taken later. The
# split never increases cross-suspension retention — a field live only before a
# suspension simply stops being rooted there — and the predicate is conservative,
# splitting only locals it can prove are never used whole.

import dataclasses
from dataclasses import dataclass

import codegen.typedecl as t
from codegen.gen import Application
from codegen.things import Function
from codegen.ops import Op, Move, Call, Phi
from codegen.param import RParam, StackVar, StructField


@dataclass(frozen=True)
class _Split:
    var: StackVar                       # the original aggregate local (carries its type)
    def_index: int                      # index of its single defining op
    field_locals: dict[str, StackVar]   # field name → replacement scalar local


def __find_splittable(fn: Function, done: set[str]) -> dict[str, _Split]:
    # Read occurrences: a projection `StructField(StackVar v, f)` flattens to
    # BOTH the StructField and the inner StackVar, so a var whose every read is
    # a projection has `sv_reads == proj_reads`. Any whole use (call arg, Phi
    # source, return, heap store, …) is a bare StackVar with no enclosing
    # StructField, tipping `sv_reads` above `proj_reads`. Writes flatten to
    # nothing under `is_reader=False`, so the definition is never miscounted.
    sv_reads: dict[str, int] = {}
    proj_reads: dict[tuple[str, str], int] = {}
    for op in fn.ops:
        for p in op.all_params():
            if isinstance(p, StackVar):
                sv_reads[p.name] = sv_reads.get(p.name, 0) + 1
            elif isinstance(p, StructField) and isinstance(p.struct, StackVar):
                proj_reads[(p.struct.name, p.field)] = proj_reads.get((p.struct.name, p.field), 0) + 1

    # The single definition site of each StackVar (SSA → at most one; a var with
    # two writes is defensively skipped).
    def_index: dict[str, int] = {}
    def_var: dict[str, StackVar] = {}
    multi: set[str] = set()
    for i, op in enumerate(fn.ops):
        for w in op.get_live_vars()[1]:
            if w.name in def_index:
                multi.add(w.name)
            def_index[w.name] = i
            def_var[w.name] = w

    splittable: dict[str, _Split] = {}
    for name in sorted(def_index):
        if name in multi or name in done:
            continue
        var = def_var[name]
        typ = var.get_type()
        # Only plain non-empty structs — never the async TaskWrapper ABI, which
        # async lowering owns and reshapes.
        if not isinstance(typ, t.Struct) or not typ.fields:
            continue
        proj_total = sum(c for (vn, _), c in proj_reads.items() if vn == name)
        reads = sv_reads.get(name, 0)
        if reads == 0 or reads != proj_total:
            continue   # never read, or used whole somewhere
        defop = fn.ops[def_index[name]]
        # Project after an ordinary single-result definition only; a Phi join
        # (loop-carried / merged) and side-effect-anchoring `keep` Moves are
        # left whole.
        if not isinstance(defop, (Move, Call)):
            continue
        if isinstance(defop, Move) and defop.keep:
            continue
        field_types = dict(typ.fields)
        used = sorted({f for (vn, f) in proj_reads if vn == name})
        field_locals = {f: StackVar(field_types[f], f"{name}${f}") for f in used}
        splittable[name] = _Split(var, def_index[name], field_locals)
    return splittable


def __apply(fn: Function, splittable: dict[str, _Split]) -> Function:
    def replacer(p: RParam) -> RParam:
        if (isinstance(p, StructField) and isinstance(p.struct, StackVar)
                and p.struct.name in splittable):
            fl = splittable[p.struct.name].field_locals.get(p.field)
            if fl is not None:
                return fl
        return p

    by_def: dict[int, _Split] = {sp.def_index: sp for sp in splittable.values()}
    new_ops: list[Op] = []
    for i, op in enumerate(fn.ops):
        # Rewrite every projection `v.f` → `v$f`. The freshly inserted projection
        # Moves below are NOT routed through `replacer`, so they keep reading the
        # original `v` and seed each field local exactly once, right after `v` is
        # defined — before any suspension can intervene.
        new_ops.append(op.replace_params(replacer))
        sp = by_def.get(i)
        if sp is not None:
            for f, fl in sp.field_locals.items():
                new_ops.append(Move(fl, StructField(sp.var, f)))

    new_fields = tuple((fl.name, fl.get_type())
                       for sp in splittable.values()
                       for fl in sp.field_locals.values())
    return dataclasses.replace(fn, ops=tuple(new_ops),
                               stack_vars=fn.stack_vars + t.Struct(new_fields))


def split_projected_aggregates(app: Application) -> Application:
    def fix(fn: Function) -> Function:
        done: set[str] = set()
        for _ in range(8):  # bounded; nested aggregates peel one level per round
            sp = __find_splittable(fn, done)
            if not sp:
                break
            fn = __apply(fn, sp)
            done |= set(sp)
        return fn

    return dataclasses.replace(app, functions={n: fix(f) for n, f in app.functions.items()})
