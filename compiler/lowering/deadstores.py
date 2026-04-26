from __future__ import annotations

import dataclasses

from codegen.gen import Application
from codegen.things import Function
from codegen.ops import Op, Move, Call
from codegen.param import StackVar


def __collect_reads(ops: tuple[Op, ...]) -> set[str]:
    """Collect all StackVar names that are ever read across all ops."""
    reads: set[str] = set()
    for op in ops:
        r, _ = op.get_live_vars()
        reads.update(sv.name for sv in r)
        reads.update(sv.name for sv in op.saved_vars)
    return reads


def __eliminate_once(fn: Function) -> Function:
    reads = __collect_reads(fn.ops)

    new_ops = []
    changed = False
    for op in fn.ops:
        if isinstance(op, Move) and isinstance(op.target, StackVar):
            if op.target.name not in reads and not op.keep:
                changed = True
                continue  # drop dead store entirely
        elif isinstance(op, Call) and isinstance(op.register, StackVar):
            if op.register.name not in reads:
                op = dataclasses.replace(op, register=None, result_type=op.register.get_type())
                changed = True
        new_ops.append(op)

    if not changed:
        return fn

    new_ops_t = tuple(new_ops)

    # Remove stack_var declarations that are no longer mentioned in any op
    mentioned: set[str] = set()
    for op in new_ops_t:
        r, w = op.get_live_vars()
        mentioned.update(sv.name for sv in r | w)

    new_stack_vars = dataclasses.replace(
        fn.stack_vars,
        fields=tuple((n, t) for n, t in fn.stack_vars.fields if n in mentioned)
    )

    return dataclasses.replace(fn, ops=new_ops_t, stack_vars=new_stack_vars)


def __eliminate_dead_stores_fn(fn: Function) -> Function:
    """Eliminate dead stores in a single function to a fixed point."""
    while True:
        new_fn = __eliminate_once(fn)
        if new_fn is fn:
            return fn
        fn = new_fn


def eliminate_dead_stores(app: Application) -> Application:
    """Remove dead StackVar assignments from all functions."""
    return dataclasses.replace(app, functions={name: __eliminate_dead_stores_fn(fn) for name, fn in app.functions.items()})
