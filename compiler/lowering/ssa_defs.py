"""SSA def-chain analysis over the pre-async IR — a LIBRARY, not a pass.

Pre-async, every StackVar has at most one definition (ssa_validate enforces
it), so "what value does this local hold?" is answerable by chasing Moves.
Several pipeline stages share that question — struct-read folding, known-tag
resolution, string-append flattening — and this module is its single home.
Nothing here rewrites anything: pure queries, safe to call from any stage.
"""
from __future__ import annotations

from codegen.ir import Function
from codegen.ops import Move, Call, Phi
from codegen.param import (
    RParam, StackVar, StructField, NewStruct, Integer, IntEqConst, String,
    Float, NullPointer, GlobalVar, GlobalFunction,
)

# A value simple enough to duplicate into each read site: pure, no evaluation
# order, no code growth beyond a name. (RuntimeInvoke and friends are excluded —
# side effects / non-trivial C expressions must stay anchored where they are.)
DUPLICABLE = (StackVar, Integer, String, Float, NullPointer, GlobalVar, GlobalFunction)

MAX_CHASE = 8   # def-chain depth bound (copies of copies of packs)


def single_defs(fn: Function) -> dict[str, RParam | None]:
    """Each StackVar's sole defining source, or None for an unknowable def
    (Phi merge, call result, or — defensively — a repeated definition)."""
    defs: dict[str, RParam | None] = {}

    def define(name: str, source: RParam | None) -> None:
        defs[name] = None if name in defs else source

    for op in fn.ops:
        if isinstance(op, Move) and isinstance(op.target, StackVar):
            define(op.target.name, op.source)
        elif isinstance(op, Call) and isinstance(op.register, StackVar):
            define(op.register.name, None)
        elif isinstance(op, Phi) and isinstance(op.target, StackVar):
            define(op.target.name, None)
    return defs


def read_counts(fn: Function) -> dict[str, int]:
    """How many ops read each StackVar (a def whose value is read exactly once
    can be absorbed into its sole reader). `saved_vars` count as reads — a var
    marked to persist across a call has a future reader (async lowering's
    state machine) that get_live_vars cannot see; deadstores applies the same
    rule, and dropping such a def segfaults at resumption."""
    counts: dict[str, int] = {}
    for op in fn.ops:
        reads, _ = op.get_live_vars()
        for sv in reads:
            counts[sv.name] = counts.get(sv.name, 0) + 1
        for sv in op.saved_vars:
            counts[sv.name] = counts.get(sv.name, 0) + 1
    return counts


def resolve_value(param: RParam, defs: dict[str, RParam | None],
                  depth: int = MAX_CHASE) -> RParam | None:
    """Chase `param` through StackVar copies to its defining value, if that
    value is statically known. Returns a NewStruct/Integer/... or None."""
    if depth <= 0:
        return None
    if isinstance(param, StackVar):
        source = defs.get(param.name)
        if source is None:
            return None
        return resolve_value(source, defs, depth - 1)
    if isinstance(param, StructField):
        base = resolve_value(param.struct, defs, depth - 1)
        if isinstance(base, NewStruct):
            for fname, fval in base.values:
                if fname == param.field:
                    return resolve_value(fval, defs, depth - 1) or fval
        return None
    if isinstance(param, (NewStruct, Integer, String, Float, NullPointer,
                          GlobalVar, GlobalFunction)):
        return param
    return None


def static_int(param: RParam, defs: dict[str, RParam | None]) -> int | None:
    """The compile-time integer value of `param`, or None if not decidable."""
    if isinstance(param, IntEqConst):
        v = static_int(param.value, defs)
        return None if v is None else int(v == param.const_val)
    resolved = resolve_value(param, defs)
    if isinstance(resolved, Integer):
        return resolved.value
    return None
