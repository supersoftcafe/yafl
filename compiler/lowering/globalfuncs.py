from __future__ import annotations

import dataclasses

from codegen.param import GlobalFunction, VirtualFunction
from codegen.ops import Call
from codegen.gen import Application
from codegen.things import Object, Function
from langtools import group_by_key


def __optimize_call(call: Call, slots: dict[str, list[str]]) -> Call:
    func_expr = call.function
    if isinstance(func_expr, VirtualFunction):
        globals = slots[func_expr.name]
        if len(globals) == 1:
            global_function = GlobalFunction(globals[0], func_expr.object)
            return dataclasses.replace(call, function=global_function)
    return call

def __optimize_function_calls(func: Function, slots: dict[str, list[str]]) -> Function:
    ops = tuple((__optimize_call(op, slots) if isinstance(op, Call) else op) for op in func.ops)
    return dataclasses.replace(func, ops=ops)


# Convert call sites to Call of GlobalFunction where possible
# - If the slot only ever has one implementing function
def discover_global_function_calls(app: Application) -> Application:
    all_slots: list[tuple[str, str]] = [(slot_name, func_name) for obj in app.objects.values() for slot_name, func_name in obj.functions]
    slot_funcs: dict[str, list[str]] = group_by_key(all_slots, lambda s: s[0], lambda s: [x for _,x in s])
    new_functions = {name: __optimize_function_calls(func, slot_funcs) for name, func in app.functions.items()}

    new_app = Application()
    new_app.globals = app.globals
    new_app.objects = app.objects
    new_app.functions = new_functions
    return new_app

