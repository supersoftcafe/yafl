from __future__ import annotations

import dataclasses
import pyast.statement as s
import pyast.expression as e

import pyast.resolver as g
import pyast.typespec as t
from codegen.typedecl import Type, Struct
from codegen.ops import Call, Op
from codegen.gen import Application
from codegen.param import GlobalFunction
from codegen.things import Function

from langtools import cast
from pyast.statement import ImportGroup


__CUTOFF_COMPLEXITY = 10




def __do_inlining(fn: Function, others: dict[str, Function]) -> Function:
    return fn # TODO: need to finish this inlining code

    new_ops: list[Op] = []
    new_vars: list[tuple[str, Type]] = []

    def replace_op_with_func(op: Op, index: int):
        if not isinstance(op, Call) or not isinstance(op.function, GlobalFunction) or op.musttail:
            return [op] # Not a candidate for inlining
        target = others[op.function.name]
        if len(target.ops) >= __CUTOFF_COMPLEXITY:
            return [op] # Target is too big to inline

        # For each param and stack_var, create a variable with a unique name
        variable_mapping: dict[str, tuple[str, Type]] =\
            {name: (f"inl{index}${name}", type) for name, type in (target.params + target.stack_vars).fields}


        # Convert each call parameter to a Move into the parameter variables
        # Insert the target code, renaming every variable use
        # Replace every return with a Move and jump to an end label
        # Replace every musttail=True with musttail=False

    for index, old_op in enumerate(fn.ops): replace_op_with_func(old_op, index)
    return dataclasses.replace(fn, ops=tuple(new_ops), stack_vars=fn.stack_vars+Struct(fields=tuple(new_vars)))


def inline_small_functions(app: Application) -> Application:

    new_app = Application()
    new_app.globals = app.globals
    new_app.objects = app.objects
    new_app.functions = {name: __do_inlining(func, app.functions    ) for name, func in app.functions.items()}
    return new_app

