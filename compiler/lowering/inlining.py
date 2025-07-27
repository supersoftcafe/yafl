from __future__ import annotations

import dataclasses
import pyast.statement as s
import pyast.expression as e

import pyast.resolver as g
import pyast.typespec as t
from codegen.typedecl import Type, Struct
from codegen.ops import Call, Op, Move, Label, Return, Jump
from codegen.gen import Application
from codegen.param import GlobalFunction, NewStruct, StackVar
from codegen.things import Function

from langtools import cast
from pyast.statement import ImportGroup


__CUTOFF_COMPLEXITY = 10




def __do_inlining(fn: Function, others: dict[str, Function]) -> Function:
    new_ops: list[Op] = []
    new_vars: list[tuple[str, Type]] = []
    all_labels: set[str] = {label.name for label in fn.ops if isinstance(label, Label)}

    def replace_op_with_func(op: Op, unique_id: str):
        if (not isinstance(op, Call) or
                not isinstance(op.function, GlobalFunction) or
                not isinstance(op.parameters, NewStruct) or
                fn.name == op.function.name or op.musttail or
                len((target := others[op.function.name]).ops) >= __CUTOFF_COMPLEXITY):
            new_ops.append(op)
            return # Not a candidate for inlining

        # For each param and stack_var, create a new stack_var with a unique name
        variable_mapping: dict[str, StackVar] =\
            {name: StackVar(type, f"inl{unique_id}${name}") for name, type in (target.params + target.stack_vars).fields}
        renames: dict[str, str] =\
            {name: sv.name for name, sv in variable_mapping.items()} |\
            {label.name: f"inl{unique_id}${label.name}" for label in target.ops if isinstance(label, Label)}
        new_vars.extend((sv.name, sv.type) for sv in variable_mapping.values())

        # Capture 'this'
        if op.function.object:
            new_ops.append(Move(variable_mapping[target.params.fields[0][0]], op.function.object))

        # Convert each call parameter to a Move into the parameter variables.
        for (_, value), (param_name, _) in zip(op.parameters.values, target.params.fields[1:]):
            new_ops.append(Move(variable_mapping[param_name], value))

        end_label = f"inl{unique_id}end"
        end_jump = Jump(end_label)

        # Insert the target code, renaming every variable use
        for target_op in target.ops:
            if isinstance(target_op, Return):
                # Replace every return with a Move and jump to an end label
                if op.register:
                    new_ops.append(Move(op.register, target_op.value.rename_vars(renames)))
                new_ops.append(end_jump)
            elif isinstance(target_op, Call) and target_op.musttail:
                # Replace every musttail=True with musttail=False
                new_ops.append(dataclasses.replace(target_op, musttail=False).rename_vars(renames))
            else:
                # Just rename the variable references
                new_ops.append(target_op.rename_vars(renames))

        if end_jump in new_ops:
            if new_ops.index(end_jump) < len(new_ops)-1:
                new_ops.append(Label(end_label)) # Needs a jump target
            else:
                new_ops.pop() # The only jump is just prior to the label

    for index, old_op in enumerate(fn.ops):
        replace_op_with_func(old_op, f"{len(fn.ops)}${index}")
    stack_vars = fn.stack_vars+Struct(fields=tuple(new_vars))
    return dataclasses.replace(fn, ops=tuple(new_ops), stack_vars=stack_vars)


def inline_small_functions(app: Application) -> Application:
    functions: dict[str, Function] = {name: __do_inlining(func, app.functions) for name, func in app.functions.items()}
    new_app = Application()
    new_app.globals = app.globals
    new_app.objects = app.objects
    new_app.functions = functions
    return new_app

