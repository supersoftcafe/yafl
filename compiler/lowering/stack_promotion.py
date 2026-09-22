"""Promote non-escaping heap objects to per-field stack locals.

A `NewObject` creates a blank heap instance which the following ops fill in
by field stores; if the object's pointer never leaves the function, the heap
allocation — and every GC cost attached to it: the allocation itself, tracing,
write barriers on the initialising stores — buys nothing. Immutability makes
the proof easy: with no aliasing writes, a non-escaping object is fully
described by its local construction.

A promoted object dissolves into ONE LOCAL PER FIELD (`reg$field`), not a
struct: field stores and reads become plain Moves and StackVar reads, so the
object scalarises immediately with no downstream folding required, and no
LParam machinery beyond what exists.

ESCAPES (any one disqualifies the candidate register):
  - returned, used as a call / parallel-call argument, or merged in a Phi;
  - its BARE POINTER consumed anywhere (stored into another object's field,
    packed into a NewStruct, captured — reading a field of it is fine, the
    pointer itself travelling is not);
  - saved across a suspension (v1);
  - an op shape the analysis doesn't model (anything beyond Move / JumpIf /
    SwitchJump reading it) — the whole escape question lives in
    `lowering/escapes.py`, shared with `fast_stores`;
  - a multiply-defined register, an arrayed/mutable/foreign class, or a
    sized NewObject.

Runs between phi_removal and async_lower: the per-field locals are
multi-write by nature (conditional construction paths), so this stage lives
on the non-SSA side of the pipeline.
"""
from __future__ import annotations

import dataclasses

from codegen.gen import Application
from codegen.ir import Function
from codegen.ops import Op, Move, NewObject
from codegen.param import (
    RParam, StackVar, ObjectField, ZeroOf, NullPointer, Integer,
)
from codegen import typedecl as t
from lowering.escapes import op_publishes


def __payload_fields(obj) -> tuple[tuple[str, t.Type], ...] | None:
    """The class's payload (fields minus the vtable header), or None when the
    shape isn't promotable."""
    if obj is None or obj.length_field is not None or obj.is_mutable or obj.is_foreign:
        return None
    fields = tuple((n, ft) for n, ft in obj.fields.fields if n != "type")
    if any(isinstance(ft, t.Array) for _, ft in fields):
        return None
    return fields


def __zero_of(ft: t.Type) -> RParam:
    if isinstance(ft, t.DataPointer):
        return NullPointer()
    if isinstance(ft, t.Int):
        return Integer(0, ft.precision)
    return ZeroOf(ft)


def __candidates(fn: Function, app: Application) -> dict[str, tuple[tuple[str, t.Type], ...]]:
    news: dict[str, tuple[tuple[str, t.Type], ...]] = {}
    defs: dict[str, int] = {}
    for op in fn.ops:
        for sv in op.get_live_vars()[1]:
            defs[sv.name] = defs.get(sv.name, 0) + 1
        if isinstance(op, NewObject) and isinstance(op.register, StackVar) and op.size is None:
            payload = __payload_fields(app.objects.get(op.name))
            if payload is not None:
                news[op.register.name] = payload

    return {name: payload for name, payload in news.items()
            if defs.get(name) == 1
            and not any(op_publishes(op, name) for op in fn.ops)}


def promote_to_stack(app: Application) -> Application:
    new_functions = {}
    for fn_name, fn in app.functions.items():
        promoted = __candidates(fn, app)
        if not promoted:
            new_functions[fn_name] = fn
            continue

        field_types = {(name, f): ft
                       for name, payload in promoted.items() for f, ft in payload}

        def field_local(name: str, f: str) -> StackVar:
            return StackVar(field_types[(name, f)], f"{name}${f}")

        def rewrite(p: RParam) -> RParam:
            if (isinstance(p, ObjectField) and isinstance(p.pointer, StackVar)
                    and p.pointer.name in promoted and p.index is None):
                return field_local(p.pointer.name, p.field)
            return p

        new_ops: list[Op] = []
        for op in fn.ops:
            if (isinstance(op, NewObject) and isinstance(op.register, StackVar)
                    and op.register.name in promoted):
                # NewObject zero-fills; the field locals must match so a
                # partially-initialised read stays defined.
                for f, ft in promoted[op.register.name]:
                    new_ops.append(Move(field_local(op.register.name, f), __zero_of(ft)))
                continue
            if (isinstance(op, Move) and isinstance(op.target, ObjectField)
                    and isinstance(op.target.pointer, StackVar)
                    and op.target.pointer.name in promoted and op.target.index is None):
                new_ops.append(Move(
                    field_local(op.target.pointer.name, op.target.field),
                    op.source.replace_params(rewrite)))
                continue
            new_ops.append(op.replace_params(rewrite))

        extra = tuple((f"{name}${f}", ft)
                      for name, payload in promoted.items() for f, ft in payload)
        stack_vars = t.Struct(tuple(
            (n, ft) for n, ft in fn.stack_vars.fields if n not in promoted) + extra)
        new_functions[fn_name] = dataclasses.replace(
            fn, ops=tuple(new_ops), stack_vars=stack_vars)
    return dataclasses.replace(app, functions=new_functions)
