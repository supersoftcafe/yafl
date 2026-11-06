from __future__ import annotations

# Dead-code elimination over the IR: drop functions/objects/globals not reachable
# from the entrypoint (run between lowering passes).
import dataclasses
from dataclasses import dataclass
from collections.abc import Iterator
from itertools import chain
from typing import Iterable

import langtools
from codegen.gen import Application
from codegen.ops import Op, Call, Return, ReturnVoid, Move, Label, JumpIf, IfTask, AssertNotTask, Jump, NewObject, SwitchJump, Abort, Phi
from codegen.ir import Function, Object, Global
from codegen.typedecl import FuncPointer, Void, Struct, ImmediateStruct, DataPointer, Int, Type
from codegen.param import ObjectField, StackVar, LParam, GlobalVar, NewStruct, GlobalFunction, Integer, Float, RParam, \
    StructField, InitArray, RuntimeInvoke, String, VirtualFunction, PointerTo, NullPointer, NewStructTyped, IntEqConst, NullPattern, TagTask, ZeroOf, SyncWrap, ObjVtableEq, ArrayElement, VtableDiscriminator, StaticObjectRef, FunField, NarrowInt, MakeFun, FieldOffset
from functools import reduce


from codegen.references import References, rparam_references, op_references, global_references, object_references, function_references, union_references

def __removed_unused_stuff(from_app: Application, scan_sets: References, to_app: References) -> Application:
    from_globals   = [global_references(from_app.globals[    name]) for name in scan_sets.globals]
    from_objects   = [object_references(from_app.objects[    name]) for name in scan_sets.objects]
    from_functions = [function_references(from_app.functions[name]) for name in scan_sets.functions]
    seen_sets = scan_sets | union_references(from_globals + from_objects + from_functions)
    new_scan_sets = seen_sets - to_app
    if not new_scan_sets:
        return dataclasses.replace(from_app,
            globals={name: from_app.globals[name] for name in sorted(to_app.globals)},
            objects={name: from_app.objects[name] for name in sorted(to_app.objects)},
            functions={name: from_app.functions[name] for name in sorted(to_app.functions)},
        )
    return __removed_unused_stuff(from_app, new_scan_sets, seen_sets | to_app)


def removed_unused_stuff(app: Application) -> Application:
    return __removed_unused_stuff(app, References(functions=frozenset(["__entrypoint__"])), References())


def recursive_functions(app: Application) -> frozenset[str]:
    """Internal functions on a cycle of the reference graph: each reaches
    itself, directly or through other functions, closures among them.
    Inlining one only unrolls the recursion, a level per round, so no IR
    inlining policy takes them. Built on the same reference model (codegen/references.py)
    as the dead-code pass. Inlining a function that is on no cycle cannot
    make one (each edge it adds was already a path through it), but the
    graph changes between inlining rounds, so each round recomputes this."""
    edges = {name: function_references(fn).functions for name, fn in app.functions.items()}
    return frozenset(v for scc in langtools.strongly_connected_components(sorted(edges), edges)
                     for v in scc if len(scc) > 1 or v in edges[v])


def address_taken_functions(app: Application) -> frozenset[str]:
    """Internal functions whose ADDRESS escapes as a value: every reference
    except the callee slot of a direct call and a vtable slot (the virtual
    call sites enumerate those). Such a function can be called from a site
    the IR cannot enumerate — through a closure, a union slot, the runtime —
    so nothing may be assumed about the arguments it receives. Built on the
    same reference model (codegen/references.py) as the dead-code pass."""
    taken: set[str] = set()
    for fn in app.functions.values():
        for op in fn.ops:
            if isinstance(op, Call) and isinstance(op.function, GlobalFunction):
                taken |= rparam_references(op.parameters).functions
                if op.register:
                    taken |= rparam_references(op.register).functions
                if op.function.object:
                    taken |= rparam_references(op.function.object).functions
            else:
                taken |= op_references(op).functions
    for gl in app.globals.values():
        if gl.lazy_init_function:
            taken.add(gl.lazy_init_function)
        if gl.init:
            taken |= rparam_references(gl.init).functions
    return frozenset(taken)
