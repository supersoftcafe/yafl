"""Eager global initialisation.

`lower_lazy_lets` promotes every global that cannot be a C static to `[lazy]`:
a `Lazy$T` stub whose reads go through `lazy_fetch$T`, whose first call may
suspend in `lazy_acquire` (another task may be initialising the same global).
Sync inference must then treat every reader, and every caller of a reader, as
possibly suspending — most of the program.

Lazy initialisation exists for globals whose safe initialisation ORDER cannot
be determined, not to defer work. This pass finds the globals whose order can:

  * the dependencies of a global are the lazy globals its initialiser can
    reach — through direct calls, function values, the vtable of every object
    it names, and the data of every static global it names (the same reference
    model the dead-code pass walks, from codegen/references.py);
  * a global on a dependency cycle (a self-dependency included) stays `[lazy]`;
  * so does one whose initialiser can reach a runtime-owned (foreign) object:
    function values stored in memory the model cannot see are the one flow it
    does not follow, so its dependencies cannot be proven complete;
  * every other global is EAGER: it is initialised before `main`, in dependency
    order, by a synthesised `__start__` that forces each stub in turn and then
    calls `main`. The entry point calls `__start__` in `main`'s place.
    Reads of an eager global become a plain load of the stub's value, with no
    gate and no suspension point.

Forcing goes through the ordinary fetch, so an initialiser that itself
suspends (IO, a still-lazy global) is awaited by async lowering as in any
function. A global that depends on a lazy global that is later in no cycle
with it is still eager: the fetch of the lazy one simply runs on demand.

Runs once, after the first dead-code pass and before inlining, while every
read is still a visible `lazy_fetch` call on a named stub.
"""
from __future__ import annotations

import dataclasses

import langtools
from codegen import references
from codegen.gen import Application
from codegen.ir import Function
from codegen.ops import Call, Move, Return
from codegen.param import GlobalFunction, GlobalVar, NewStruct, ObjectField, StackVar
from codegen.typedecl import DataPointer, Struct

START = "__start__"
_FETCH_PREFIX = "lazy_fetch$"
_STUB_PREFIX = "Lazy$"


def _lazy_stubs(app: Application) -> list[str]:
    return sorted(name for name, gl in app.globals.items()
                  if gl.object_name is not None and gl.object_name.startswith(_STUB_PREFIX))


def _reachable_stubs(app: Application, stubs: list[str]) -> dict[str, frozenset[str]]:
    """For each stub, the stubs its initialiser can reach, itself included if
    it can reach itself. One pass over the condensation of the reference graph,
    each component's reach a bitmask of stub indices."""
    stub_bit = {name: 1 << i for i, name in enumerate(stubs)}
    opaque_bit = 1 << len(stubs)   # reaches a foreign object: dependencies unprovable
    edges: dict[str, list[str]] = {}
    own: dict[str, int] = {}

    for name, fn in app.functions.items():
        refs = references.function_references(fn)
        edges["f:" + name] = (["f:" + n for n in refs.functions if n in app.functions]
                              + ["g:" + n for n in refs.globals if n in app.globals]
                              + ["o:" + n for n in refs.objects if n in app.objects])
    for name, gl in app.globals.items():
        if name in stub_bit:
            own["g:" + name] = stub_bit[name]
            edges["g:" + name] = []   # a stub's closure is a dependency's own business
        else:
            refs = references.global_references(gl)
            edges["g:" + name] = (["f:" + n for n in refs.functions if n in app.functions]
                                  + ["g:" + n for n in refs.globals if n in app.globals]
                                  + ["o:" + n for n in refs.objects if n in app.objects])
    for name, obj in app.objects.items():
        refs = references.object_references(obj)
        if obj.is_foreign:
            own["o:" + name] = opaque_bit
        edges["o:" + name] = (["f:" + n for n in refs.functions if n in app.functions]
                              + ["o:" + n for n in refs.objects if n in app.objects])

    mask: dict[str, int] = {}
    for scc in langtools.strongly_connected_components(sorted(edges), edges):
        members = set(scc)
        m = 0
        for v in scc:
            m |= own.get(v, 0)
            for w in edges[v]:
                if w not in members:
                    m |= mask[w]
        for v in scc:
            mask[v] = m

    result: dict[str, frozenset[str]] = {}
    for name in stubs:
        roots = references.global_references(app.globals[name]).functions
        m = 0
        for fn in roots:
            m |= mask.get("f:" + fn, 0)
        result[name] = (frozenset(stubs) if m & opaque_bit    # unprovable: depends on everything,
                        else frozenset(s for s in stubs if m & stub_bit[s]))  # so on itself
    return result


def _eager_order(app: Application) -> list[str]:
    """The globals to initialise at startup, each after everything it depends on."""
    stubs = _lazy_stubs(app)
    if not stubs:
        return []
    reach = _reachable_stubs(app, stubs)   # an unprovable global reaches itself: a cycle
    order: list[str] = []
    for scc in langtools.strongly_connected_components(stubs, reach):
        if len(scc) == 1 and scc[0] not in reach[scc[0]]:
            order.append(scc[0])
    return order


def _is_fetch_of(op, eager: set[str]) -> bool:
    return (isinstance(op, Call) and not op.musttail and op.register is not None
            and isinstance(op.function, GlobalFunction)
            and op.function.name.startswith(_FETCH_PREFIX)
            and isinstance(op.function.object, GlobalVar)
            and op.function.object.name in eager)


def make_globals_eager(app: Application) -> Application:
    order = _eager_order(app)
    if not order:
        return app
    eager = set(order)

    # Reads of an eager global: a plain load of the stub's value.
    functions: dict[str, Function] = {}
    for name, fn in app.functions.items():
        if any(_is_fetch_of(op, eager) for op in fn.ops):
            ops = tuple(
                Move(op.register, ObjectField(app.functions[op.function.name].result,
                                              op.function.object,
                                              app.globals[op.function.object.name].object_name,
                                              "value", None))
                if _is_fetch_of(op, eager) else op
                for op in fn.ops)
            fn = dataclasses.replace(fn, ops=ops)
        functions[name] = fn

    # `__start__`: force each eager global in order, then `main`.
    entry = functions["__entrypoint__"]
    main_call = entry.ops[0]
    assert isinstance(main_call, Call) and isinstance(main_call.function, GlobalFunction)
    main = functions[main_call.function.name]

    forced: list[tuple[str, object]] = []
    ops: list = []
    for i, g in enumerate(order):
        fetch = GlobalFunction(
            "lazy_fetch$" + app.globals[g].object_name[len(_STUB_PREFIX):],
            GlobalVar(DataPointer(), g))
        ty = functions[fetch.name].result
        var = StackVar(ty, f"$init{i}")
        forced.append((var.name, ty))
        ops.append(Call(fetch, NewStruct(()), var, impure=True))
    result = StackVar(main.result, "$result")
    ops.append(Call(GlobalFunction(main.name), NewStruct(()), result))
    ops.append(Return(result))
    functions[START] = Function(
        name=START,
        params=Struct((("this", DataPointer()),)),
        result=main.result,
        stack_vars=Struct(tuple(forced) + (("$result", main.result),)),
        ops=tuple(ops),
        comment="initialise eager globals, then main",
    )
    functions["__entrypoint__"] = dataclasses.replace(
        entry, ops=(dataclasses.replace(main_call, function=GlobalFunction(START)),) + entry.ops[1:])
    return dataclasses.replace(app, functions=functions)
