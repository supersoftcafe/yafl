from __future__ import annotations

import dataclasses

from codegen.param import GlobalFunction, GlobalVar, Invoke, NewStruct, PointerTo
from codegen.ops import Call, Op, JumpIf, Label
from codegen.gen import Application
from codegen.things import Function, Global
from codegen.typedecl import DataPointer, Int


# Add code to the start of each function to ensure that referenced globals that
# require lazy initialisation have been initialised, and to initialise them if
# not. It's not perfect, but that's not the goal here, the goal is just to defer
# the cost of expensive or complex global init away from startup.


def __create_global_init_ops(glb: Global, index: Int) -> list[Op]:
    label = Label(f"skip_global_init${index}")

    check_params = NewStruct( (("p1", GlobalVar(DataPointer(), glb.lazy_init_flag)),) )
    check = JumpIf(label.name, Invoke("lazy_global_init_complete", check_params, Int(8)))

    init_params = NewStruct( (
        ("flag", PointerTo(GlobalVar(DataPointer(), glb.lazy_init_flag))),
        ("init", GlobalFunction(glb.lazy_init_function))
        # Continuation parameter will be added by the CPS conversion later
    ))
    invoke = Call(GlobalFunction("lazy_global_init", external=True), init_params)

    return [check, invoke, label]


def __add_global_init_ops(app: Application, fn: Function) -> Function:
    glb_list = [app.globals[param.name] for op in fn.ops for param in op.all_params() if isinstance(param, GlobalVar)]
    ops = tuple(op for index, glb in enumerate(glb_list) if glb.lazy_init_function for op in __create_global_init_ops(glb, index)) + fn.ops
    return dataclasses.replace(fn, ops=ops)


def add_ops_to_support_global_lazy_init(app: Application) -> Application:
    updated_functions = {name: __add_global_init_ops(app, fn) for name, fn in app.functions.items()}

    new_app = Application()
    new_app.globals = app.globals
    new_app.objects = app.objects
    new_app.functions = updated_functions
    return new_app


