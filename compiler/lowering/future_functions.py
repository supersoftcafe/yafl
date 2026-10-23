"""`[future]` functions: the body runs on a worker, and a call answers later.

A `[future]` function's first step is the runtime's `future_yield` (yafllib
task.c), a foreign call that may suspend. It hands back a task that is
already complete, so async_lower suspends on it like any latent await: the
function saves its frame and returns its own task to the caller, and
registering the continuation is what posts it to another worker, which runs
the body and completes that task with the result. The caller holds the task
like any other async result. When the pool is not accepting, `future_yield`
answers None at once and the body runs in place.

The inliners leave `[future]` functions alone (`Function.future`): inlined,
the yield would hand the rest of the CALLER to the worker instead.
"""
from __future__ import annotations

import dataclasses

from codegen.gen import Application
from codegen.ir import Function
from codegen.ops import Call
from codegen.param import GlobalFunction, NewStruct, StackVar
from codegen.typedecl import DataPointer, Struct


YIELD = "future_yield"

_NONE = Struct(())
_REGISTER = "$future_yield"


def _yield_function() -> Function:
    return Function(
        name=YIELD,
        params=Struct((("this", DataPointer()),)),
        result=_NONE,
        stack_vars=Struct(()),
        ops=(),
        comment=YIELD,
        foreign_symbol=YIELD,
    )


def _with_entry_yield(fn: Function) -> Function:
    call = Call(GlobalFunction(YIELD, c_symbol=YIELD, impure=True),
                NewStruct(()), StackVar(_NONE, _REGISTER), impure=True)
    return dataclasses.replace(fn, ops=(call,) + fn.ops,
                               stack_vars=fn.stack_vars + Struct(((_REGISTER, _NONE),)))


def add_future_entries(app: Application) -> Application:
    """Open every `[future]` function with the call to `future_yield`, and
    declare the runtime function when any does."""
    if not any(fn.future for fn in app.functions.values()):
        return app
    functions = {name: _with_entry_yield(fn) if fn.future else fn
                 for name, fn in app.functions.items()}
    functions.setdefault(YIELD, _yield_function())
    return dataclasses.replace(app, functions=functions)
