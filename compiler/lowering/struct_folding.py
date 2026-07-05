"""Fold field reads of locally-built structs (case-of-known-field).

After fusion, a former stage boundary packs a NewStruct into a local and reads
fields off it a few ops later. In SSA the pack is the local's only definition
(lowering/ssa_defs.py), so `StructField(sv, f)` folds to the packed field's
value whenever that value is simple enough to duplicate. The bypassed pack
then falls to deadstores. Runs in the pre-async fixpoint at -O1+: every value
deleted here is a slot never saved across a suspension.

Phi-safe: substitution only at read positions, no labels touched; Phi/Call-
defined locals are unknown by construction.
"""
from __future__ import annotations

import dataclasses

from codegen.gen import Application
from codegen.param import RParam, StackVar, StructField, NewStruct
from lowering.ssa_defs import DUPLICABLE, single_defs, resolve_value


def fold_struct_reads(app: Application) -> Application:
    new_functions = {}
    for name, fn in app.functions.items():
        defs = single_defs(fn)

        def replacer(p: RParam) -> RParam:
            if isinstance(p, StructField) and isinstance(p.struct, StackVar):
                base = resolve_value(p.struct, defs)
                if isinstance(base, NewStruct):
                    for fname, fval in base.values:
                        if fname == p.field and isinstance(fval, DUPLICABLE):
                            return fval
            return p

        new_ops = tuple(op.replace_params(replacer) for op in fn.ops)
        new_functions[name] = dataclasses.replace(fn, ops=new_ops)
    return dataclasses.replace(app, functions=new_functions)
