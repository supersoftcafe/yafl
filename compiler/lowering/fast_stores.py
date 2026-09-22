"""Elide the write barrier on stores into an object that is still brand new.

`ObjectField.fresh` already carries the fact this pass proves: the object was
allocated moments ago, straight-line before this store, and nothing has
published it. Two duties fall away when it holds —

  * the SATB deletion barrier (`codegen/param.py`): no cycle can have OPENED
    inside the window, because opening one needs a safe point and there is
    none. So either the cycle opened before the allocation, where the object
    did not exist and none of its fields can be a snapshot path, or after the
    last store. Nothing is owed either way. (That the field also still holds
    the allocator's zero-fill is a second, narrower reason — it is why a field
    written twice inside one window is covered too.)
  * the relocation resolve (`lowering/pinnable_reads.py`): no safe point means
    no compaction, so the pointer cannot have gone stale.

Construction codegen sets `fresh` on the stores it emits itself. Nothing else
did — so the async state object, allocated at every suspension and immediately
filled with that site's live set, paid a barrier on every save. That was the
bulk of the barriers in a self-compile.

THE PROOF, per store `Move(ObjectField(pointer=StackVar n, …), src)`: on every
path reaching it, `n` holds an object created by a `NewObject` in this function,
and since that allocation nothing has run a safe point (any `Call`,
`ParallelCall`, `NewObject` or `RuntimeInvoke`) and nothing has published the
pointer (`lowering/escapes.py`).

Runs LAST, after `async_lower` — which is what creates the state stores — and
after `pinnable_reads`, so every `ObjectField` the pipeline can produce is
already in place. Matching only a bare `StackVar` base is what keeps
`[pinnable]` objects out of the pass for free: `pinnable_reads` has already
wrapped those bases in an `object_resolve` call, so they no longer match.

This is POST-SSA, so `ssa_defs` does not apply and a def-chase would be wrong:
`$async` functions are exempt from single-definition, and `$state` names the
freshly allocated object on the suspend path and the state PARAMETER on the
resume path. It has to be a dataflow.

THE DATAFLOW is a forward must-analysis run as a repeated LINEAR SWEEP rather
than over a built CFG — the facts are the same, and a sweep needs nothing but a
label→fact map:

  * carry a fact set through the ops in order;
  * a jump to L intersects the carried fact into `arriving[L]`;
  * a Label L starts from `carried ∩ arriving[L]`;
  * after a terminator the carried fact is the UNIVERSE, so the unreachable run
    up to the next label contributes nothing to it.

Every set starts at the universe and only ever shrinks, so sweeping to a
fixpoint gives the greatest fixpoint — which is what lets a loop whose body
holds no safe point keep its window. An unreachable block keeps the universe,
which is harmless: its stores never run.
"""
from __future__ import annotations

import dataclasses

from codegen.gen import Application
from codegen.ir import Function
from codegen.ops import (
    Op, Move, Call, ParallelCall, NewObject, Return, ReturnVoid, Abort,
    Label, Jump, JumpIf, IfTask, AssertNotTask, SwitchJump, Phi,
)
from codegen.param import StackVar, ObjectField, RuntimeInvoke
from lowering.escapes import op_publishes


# Ops whose effect on the fact set this pass models. Anything else — a new op
# kind added later — falls to the `__kills_everything` default, so an
# unmodelled op costs optimisation, never soundness.
_MODELLED = (Move, Label, Jump, JumpIf, IfTask, AssertNotTask, SwitchJump,
             Return, ReturnVoid, Abort, Phi)

# Control does not fall through past these.
_TERMINAL = (Jump, Return, ReturnVoid, Abort)

_MAX_SWEEPS = 8     # bounded; the sets are finite and shrink monotonically


def __kills_everything(op: Op) -> bool:
    """Can this op reach a GC safe point? An allocation polls, a call may
    allocate inside the callee, and a runtime helper is opaque. Any of them
    can open a cycle or relocate, which ends every window at once."""
    if isinstance(op, (Call, ParallelCall, NewObject)):
        return True
    if any(isinstance(p, RuntimeInvoke) for p in op.all_params()):
        return True
    return not isinstance(op, _MODELLED)


def __step(op: Op, fresh: frozenset[str]) -> frozenset[str]:
    """The fact set after `op`, given the set before it."""
    if __kills_everything(op):
        # The allocation itself is the one safe point that also OPENS a
        # window: relocation can only happen at a LATER safe point, so the
        # object is clean from the instruction after its own allocation.
        if isinstance(op, NewObject) and isinstance(op.register, StackVar):
            return frozenset({op.register.name})
        return frozenset()

    # `Move(StackVar t, StackVar s)` with `s` fresh is a second NAME for the
    # one object, not a publication.
    if (isinstance(op, Move) and isinstance(op.target, StackVar)
            and isinstance(op.source, StackVar) and op.source.name in fresh):
        return fresh | {op.target.name}

    survivors = {n for n in fresh if not op_publishes(op, n)}
    # Anything this op WRITES no longer holds what it held: `op_publishes`
    # only inspects reads, so the kill has to be explicit.
    written = {sv.name for sv in op.get_live_vars()[1]}
    if isinstance(op, IfTask):
        # IfTask assigns `task_lhs` and `call_id_lhs` on the side and reports
        # NO writes at all from get_live_vars, so it needs naming here.
        written |= {p.name for p in (op.task_lhs, op.call_id_lhs)
                    if isinstance(p, StackVar)}
    return frozenset(survivors - written)


def __jump_targets(op: Op) -> list[str]:
    if isinstance(op, Jump):
        return [op.name]
    if isinstance(op, JumpIf):
        return [op.label]
    if isinstance(op, IfTask):
        return [op.target]
    if isinstance(op, SwitchJump):
        return [lbl for _v, lbl in op.cases]
    return []


def __arriving(ops: tuple[Op, ...], universe: frozenset[str]) -> dict[str, frozenset[str]]:
    """label → the intersection of the facts on every jump edge into it."""
    arriving = {op.name: universe for op in ops if isinstance(op, Label)}
    for _ in range(_MAX_SWEEPS):
        before = dict(arriving)
        fact = frozenset()                      # function entry owns nothing
        for op in ops:
            if isinstance(op, Label):
                fact = fact & arriving[op.name]
            # AFTER the step, not before: a branch whose condition consumes
            # the bare pointer publishes it before control transfers, so the
            # taken edge must carry the post-kill fact.
            fact = __step(op, fact)
            for target in __jump_targets(op):
                if target in arriving:
                    arriving[target] &= fact
            if isinstance(op, _TERMINAL) or (isinstance(op, Call) and op.musttail):
                fact = universe                 # unreachable until the next Label
        if arriving == before:
            return arriving
    # Not converged inside the budget. This is a GREATEST fixpoint, so the
    # sets are still too LARGE — stopping here would claim freshness the
    # sweep has not yet disproved. Fall back to the safe bottom instead:
    # nothing arrives fresh at any label, which leaves only the straight-line
    # run before the first label optimisable.
    return {name: frozenset() for name in arriving}


def __rewrite(fn: Function) -> Function:
    ops = fn.ops
    universe = frozenset(op.register.name for op in ops
                         if isinstance(op, NewObject) and isinstance(op.register, StackVar))
    if not universe:
        return fn                               # nothing this pass could prove

    arriving = __arriving(ops, universe)
    new_ops = list(ops)
    changed = False
    fact = frozenset()
    for i, op in enumerate(ops):
        if isinstance(op, Label):
            fact = fact & arriving[op.name]
        if (isinstance(op, Move) and isinstance(op.target, ObjectField)
                and not op.target.fresh
                and isinstance(op.target.pointer, StackVar)
                and op.target.pointer.name in fact):
            new_ops[i] = dataclasses.replace(
                op, target=dataclasses.replace(op.target, fresh=True))
            changed = True
        fact = __step(op, fact)
        if isinstance(op, _TERMINAL) or (isinstance(op, Call) and op.musttail):
            fact = universe
    return dataclasses.replace(fn, ops=tuple(new_ops)) if changed else fn


def mark_fast_stores(app: Application) -> Application:
    """Set `fresh` on every store this pass can prove needs no barrier."""
    return dataclasses.replace(app, functions={
        name: __rewrite(fn) for name, fn in app.functions.items()})
