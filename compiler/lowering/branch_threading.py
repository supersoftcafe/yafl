"""Branch threading: replace `Jump(L)` with a copy of the terminator that
follows `Label(L)`, when that terminator is itself a Return / ReturnVoid /
unconditional Jump."""
from __future__ import annotations

import dataclasses

from codegen.gen import Application
from codegen.things import Function
from codegen.ops import Op, Jump, Label, Return, ReturnVoid


def __terminator_after(ops, label_name):
    for i, op in enumerate(ops):
        if isinstance(op, Label) and op.name == label_name:
            if i + 1 < len(ops):
                nxt = ops[i + 1]
                if isinstance(nxt, (Return, ReturnVoid, Jump)):
                    return nxt
            return None
    return None


def __thread_branches_fn(fn):
    ops = fn.ops
    while True:
        new_ops = []
        changed = False
        for op in ops:
            if isinstance(op, Jump):
                terminator = __terminator_after(ops, op.name)
                if terminator is not None and terminator is not op:
                    new_ops.append(terminator)
                    changed = True
                    continue
            new_ops.append(op)
        if not changed:
            break
        ops = tuple(new_ops)
    if ops is fn.ops:
        return fn
    return dataclasses.replace(fn, ops=ops).strip_unused_operations()


def thread_branches(app):
    return dataclasses.replace(app, functions={
        name: __thread_branches_fn(fn) for name, fn in app.functions.items()})
