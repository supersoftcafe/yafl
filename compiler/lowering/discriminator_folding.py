"""Fold vtable-discriminator reads of locally-constructed objects.

Union dispatch over pointer-repr members compares
`VtableDiscriminator(value)` — `value->vtable->discriminator` — against arm
leaves' registry ids. When `value` chases (through single-read SSA copies) to
a `NewObject` in the same function, the discriminator is a per-class
compile-time constant (`Object.discriminator`): the read folds to that
integer, `known_tags` then hardens the comparison and jump in the same
fixpoint round, and the object's remaining uses collapse to plain field
reads — which is exactly what `stack_promotion` needs to delete the
allocation outright. Case-of-known-constructor for vtable-tagged variants.
"""
from __future__ import annotations

import dataclasses

from codegen.gen import Application
from codegen.ops import NewObject
from codegen.param import RParam, StackVar, VtableDiscriminator, Integer
from lowering.ssa_defs import single_defs, MAX_CHASE


def resolve_known_discriminators(app: Application) -> Application:
    new_functions = {}
    for name, fn in app.functions.items():
        newobjs = {op.register.name: op.name for op in fn.ops
                   if isinstance(op, NewObject) and isinstance(op.register, StackVar)}
        if not newobjs:
            new_functions[name] = fn
            continue
        defs = single_defs(fn)

        def class_of(param: RParam, depth: int = MAX_CHASE) -> str | None:
            if depth <= 0 or not isinstance(param, StackVar):
                return None
            if param.name in newobjs:
                return newobjs[param.name]
            source = defs.get(param.name)
            return class_of(source, depth - 1) if source is not None else None

        def replacer(p: RParam) -> RParam:
            if isinstance(p, VtableDiscriminator):
                cls = class_of(p.value)
                if cls is not None:
                    obj = app.objects.get(cls)
                    if obj is not None and obj.discriminator != 0:
                        return Integer(obj.discriminator, 32)
            return p

        new_ops = tuple(op.replace_params(replacer) for op in fn.ops)
        new_functions[name] = dataclasses.replace(fn, ops=new_ops)
    return dataclasses.replace(app, functions=new_functions)
