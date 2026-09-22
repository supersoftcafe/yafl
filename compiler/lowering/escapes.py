"""Does this op let a local's BARE POINTER get away? — a LIBRARY, not a pass.

Two stages ask the same question of the IR and must answer it identically:

  * `stack_promotion` dissolves a heap object into per-field locals, which is
    only sound while the pointer never leaves the function;
  * `fast_stores` elides a store's write barrier while the object is still
    private to the allocating function.

Reading a FIELD of the object is fine — the base pointer is consumed by the
load, not published. The pointer TRAVELLING is what matters: stored into
another object, packed into a struct, captured, returned, handed to a callee.

Nothing here rewrites anything: pure queries, safe to call from any stage,
either side of the SSA boundary.
"""
from __future__ import annotations

from codegen.ops import (
    Op, Move, Call, ParallelCall, NewObject, Return, Phi, JumpIf, SwitchJump,
)
from codegen.param import RParam, StackVar, ObjectField


def bare_pointer_in(param: RParam | None, name: str) -> bool:
    """True if `name` occurs in `param`'s tree anywhere other than as the
    base of a plain ObjectField read — i.e. the raw pointer is consumed."""
    if param is None:
        return False
    if isinstance(param, StackVar):
        return param.name == name
    if isinstance(param, ObjectField):
        base_ok = isinstance(param.pointer, StackVar) and param.pointer.name == name
        if base_ok:
            return bare_pointer_in(param.index, name)
        return (bare_pointer_in(param.pointer, name)
                or bare_pointer_in(param.index, name))
    # Any other compound (NewStruct pack, RuntimeInvoke args, …): the node
    # kinds above are the only ones with field-read structure to see through,
    # so an occurrence anywhere in here is the pointer travelling. Conservative
    # by construction.
    return param.test(lambda q: isinstance(q, StackVar) and q.name == name)


def op_publishes(op: Op, name: str) -> bool:
    """True if `op` lets `name`'s pointer reach anywhere the function does not
    exclusively own: a callee, a heap field, a struct pack, a return value, a
    Phi merge, or the async state saved across a suspension."""
    if any(sv.name == name for sv in op.saved_vars):
        return True
    if isinstance(op, (Call, ParallelCall, Return, Phi)):
        return any(sv.name == name for sv in op.get_live_vars()[0])
    if isinstance(op, Move):
        if bare_pointer_in(op.source, name):
            return True
        if isinstance(op.target, ObjectField):
            # Store INTO the candidate = constructor write; the pointer
            # is the base, not the value. An indexed store needs the
            # index checked.
            if (isinstance(op.target.pointer, StackVar)
                    and op.target.pointer.name == name):
                return bare_pointer_in(op.target.index, name)
            return bare_pointer_in(op.target.pointer, name)
        return False
    if isinstance(op, JumpIf):
        return bare_pointer_in(op.condition, name)
    if isinstance(op, SwitchJump):
        # `.condition`, not `.value`: SwitchJump has never had a `value`
        # field. The typo was unreachable while `stack_promotion` was the only
        # caller (it runs before async lowering, the only producer of a
        # SwitchJump); `fast_stores` runs after, and hits it on every async
        # function. The port had it right all along (`sw.switchCondition`).
        return bare_pointer_in(op.condition, name)
    if isinstance(op, NewObject):
        return False
    return any(sv.name == name for sv in op.get_live_vars()[0])
