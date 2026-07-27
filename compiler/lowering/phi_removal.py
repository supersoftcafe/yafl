"""Leave SSA before async lowering: lower Phis to edge Moves, then coalesce.

Runs after the SSA-dependent stages (the known-value fixpoint, sroa) and
immediately before async_lower. Two steps per function:

1. `Function.lower_phis()` — every Phi becomes per-edge Moves on its
   predecessors' exits (the same translation emission used to do last).
2. Copy coalescing — a phi web's edge copy `Move(T, src)` usually follows
   `src`'s only definition directly; when `src` is defined once, read once
   (by the copy), and nothing touches `T` in between, the definition is
   renamed to write `T` and the copy disappears. Each firing removes one
   local and one move.

Fewer locals is the point: every local a suspension carries is a state-object
field, a boundary load/store and a GC-barriered write, and every local in a
merged (fused) body is register pressure for the C compiler. A phi web that
took N SSA names collapses towards one.

From this stage on the IR is deliberately NOT single-assignment (edge moves
and coalesced webs multi-define); the final ssa_validate pass checks control
flow and termination only.
"""
from __future__ import annotations

import dataclasses

from codegen.gen import Application
from codegen.ir import Function
from codegen.ops import Move, Label, Jump, JumpIf, SwitchJump, IfTask, Return, ReturnVoid, Abort
from codegen.param import StackVar, RParam


def __coalesce_copies(fn: Function) -> Function:
    defs: dict[str, int] = {}
    reads: dict[str, int] = {}
    for op in fn.ops:
        op_reads, op_writes = op.get_live_vars()
        for sv in op_reads:
            reads[sv.name] = reads.get(sv.name, 0) + 1
        for sv in op_writes:
            defs[sv.name] = defs.get(sv.name, 0) + 1
        for sv in op.saved_vars:
            reads[sv.name] = reads.get(sv.name, 0) + 1

    ops = list(fn.ops)
    removed: set[int] = set()
    for i, op in enumerate(ops):
        if not (isinstance(op, Move) and not op.keep
                and isinstance(op.target, StackVar) and isinstance(op.source, StackVar)):
            continue
        t_name, s_name = op.target.name, op.source.name
        if t_name == s_name:
            removed.add(i)
            continue
        if defs.get(s_name) != 1 or reads.get(s_name) != 1:
            continue
        # Walk back to src's definition within this block; bail if T is
        # touched (read or written) in between, or the block boundary or a
        # call intervenes (a Call's register write is a fine def, but the
        # scan must not cross labels/jumps — value flow beyond the block is
        # not visible here).
        j = i - 1
        def_idx = None
        while j >= 0 and def_idx is None:
            prev = ops[j]
            if isinstance(prev, (Label, Jump, JumpIf, SwitchJump, IfTask,
                                 Return, ReturnVoid, Abort)):
                break
            p_reads, p_writes = prev.get_live_vars()
            if any(sv.name == s_name for sv in p_writes):
                def_idx = j
                break
            if any(sv.name in (t_name, s_name) for sv in p_reads | p_writes):
                break
            j -= 1
        if def_idx is None:
            continue
        # The defining op itself may read T (e.g. T' = T + 1): reads happen
        # before the write in every op shape, so renaming its target to T is
        # still safe. Substitute T's OWN spelling (name AND type), not a
        # name-only rename: keeping the source's type minted the same name
        # at two precisions (e.g. an i16 union-slot shard coalesced into an
        # i8 Bool constructor param), and the twin spelling broke the
        # (type,name)-keyed liveness kill in async_lower — the def never
        # killed the use spelling, the var looked upward-exposed from the
        # function head, and frame layouts grew spurious extra slots.
        t_sv = op.target
        def _sub(p: RParam, s=s_name, t_sv=t_sv) -> RParam:
            return t_sv if isinstance(p, StackVar) and p.name == s else p
        ops[def_idx] = ops[def_idx].replace_params(_sub)
        removed.add(i)
        defs[t_name] = defs.get(t_name, 0) + 1

    if not removed:
        return fn
    kept = tuple(op for i, op in enumerate(ops) if i not in removed)
    dead = {ops[i].source.name for i in removed if isinstance(ops[i], Move)
            and isinstance(ops[i].source, StackVar)
            and ops[i].source.name != ops[i].target.name}
    stack_vars = dataclasses.replace(fn.stack_vars, fields=tuple(
        (n, t) for n, t in fn.stack_vars.fields if n not in dead))
    return dataclasses.replace(fn, ops=kept, stack_vars=stack_vars)


def remove_phis(app: Application) -> Application:
    new_functions = {name: __coalesce_copies(fn.lower_phis())
                     for name, fn in app.functions.items()}
    return dataclasses.replace(app, functions=new_functions)
