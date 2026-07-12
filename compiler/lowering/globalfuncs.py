from __future__ import annotations

import dataclasses

from codegen.param import GlobalFunction, VirtualFunction, StackVar, StructField, NewStruct, RParam
from codegen.ops import Call, Move, Phi
from codegen.gen import Application
from codegen.ir import Object, Function
from langtools import group_by_key


def _fun_value_map(func: Function) -> dict[str, RParam]:
    """Single-assigned StackVar name → source, for tracing an indirect call's
    fun_t value back to the known function it holds."""
    counts: dict[str, int] = {}
    values: dict[str, RParam] = {}
    for op in func.ops:
        if isinstance(op, Move) and isinstance(op.target, StackVar):
            counts[op.target.name] = counts.get(op.target.name, 0) + 1
            values[op.target.name] = op.source
        elif isinstance(op, (Phi, Call)):
            tgt = op.target if isinstance(op, Phi) else op.register
            if isinstance(tgt, StackVar):
                counts[tgt.name] = counts.get(tgt.name, 0) + 2  # opaque
    return {n: v for n, v in values.items() if counts[n] == 1}


def _resolve_fun(rp: RParam, vmap: dict[str, RParam], depth: int = 16) -> GlobalFunction | None:
    """Chase an indirect call's fun_t expression through single-assignment
    copies (and fields of known structs) to a GlobalFunction, or None."""
    while depth > 0:
        depth -= 1
        if isinstance(rp, GlobalFunction):
            return rp
        if isinstance(rp, StackVar):
            nxt = vmap.get(rp.name)
            if nxt is None:
                return None
            rp = nxt
            continue
        if isinstance(rp, StructField):
            base = rp.struct
            if isinstance(base, StackVar):
                base = vmap.get(base.name)
            if isinstance(base, NewStruct):
                val = next((v for n, v in base.values if n == rp.field), None)
                if val is not None:
                    rp = val
                    continue
            return None
        return None
    return None


def __optimize_call(call: Call, slots: dict[str, list[str]], vmap: dict[str, RParam]) -> Call:
    func_expr = call.function
    if isinstance(func_expr, VirtualFunction):
        globals = slots[func_expr.name]
        if len(globals) == 1:
            global_function = GlobalFunction(globals[0], func_expr.object)
            return dataclasses.replace(call, function=global_function)
    # An indirect fun_t call whose value traces to one known function — e.g.
    # the array fill loop calling its init closure — becomes a direct call,
    # which the inliner can then absorb (an indirect call inside a loop
    # blocks clang's vectoriser outright).
    elif isinstance(func_expr, (StackVar, StructField)):
        resolved = _resolve_fun(func_expr, vmap)
        if resolved is not None:
            return dataclasses.replace(call, function=resolved)
    return call

def __optimize_function_calls(func: Function, slots: dict[str, list[str]]) -> Function:
    vmap = _fun_value_map(func)
    ops = tuple((__optimize_call(op, slots, vmap) if isinstance(op, Call) else op) for op in func.ops)
    return dataclasses.replace(func, ops=ops)


# Convert call sites to Call of GlobalFunction where possible
# - If the slot only ever has one implementing function
# - If an indirect fun_t call's value traces to a single known function
def discover_global_function_calls(app: Application) -> Application:
    all_slots: list[tuple[str, str]] = [(slot_name, func_name) for obj in app.objects.values() for slot_name, func_name in obj.functions]
    slot_funcs: dict[str, list[str]] = group_by_key(all_slots, lambda s: s[0], lambda s: [x for _,x in s])
    new_functions = {name: __optimize_function_calls(func, slot_funcs) for name, func in app.functions.items()}

    return dataclasses.replace(app, functions=new_functions)
