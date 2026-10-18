"""Mutable stores — tell each field store whether its container is mutable.

Whether an object is mutable is a fact about its class (`Object.is_mutable`),
known here and not to the runtime without a read of the object's page header.
A store into a mutable object takes GC_STORE_MUTABLE_IN, which skips the
nursery's private test: a mutable object is never private (yafl.h, "Pointer
stores"). Every other store keeps GC_STORE_IN, which is correct for either.

Runs at every optimisation level, last, after the representation merge, so
the object names it reads are the ones emitted.
"""
from __future__ import annotations

import dataclasses

from codegen.gen import Application
from codegen.ir import Function
from codegen.ops import Move
from codegen.param import ObjectField


def __rewrite(fn: Function, mutable_classes: frozenset[str]) -> Function:
    new_ops = [dataclasses.replace(op, target=dataclasses.replace(op.target, mutable=True))
               if isinstance(op, Move) and isinstance(op.target, ObjectField)
                  and op.target.object_name in mutable_classes
               else op
               for op in fn.ops]
    return dataclasses.replace(fn, ops=tuple(new_ops))


def mark_mutable_stores(app: Application) -> Application:
    """Set `mutable` on every field store into an object of a mutable class."""
    mutable_classes = frozenset(name for name, obj in app.objects.items() if obj.is_mutable)
    return dataclasses.replace(app, functions={
        name: __rewrite(fn, mutable_classes) for name, fn in app.functions.items()})
