"""Tail-call trampoline lowering for functions marked `[tail]`.

For every `[tail]`-marked function `fn`, this pass produces:

  * `fn$tailimpl` — the original body, renamed. `async_lower` then
                   processes it as an ordinary function.
  * `fn`         — a wrapper that user code actually calls. It allocates a
                   state task carrying the args, posts a dispatch action
                   to the worker queue, and returns the state as a tagged
                   task. The caller's IS_TASK check fires immediately and
                   they wait on the state.
  * `fn$tailcallback(state, _)` — runs on the worker when the dispatch
                   action fires. Calls `fn$tailimpl` with args read from
                   state, then either deferred-completes the state task
                   (sync impl result) or registers `fn$tailchain` on the
                   impl's inner task (async impl result).
  * `fn$tailchain(state, completed)` — registered when the impl returned
                   a task. Copies the inner task's result into the state
                   task and deferred-completes it.
  * `fn$tailstate` (Object) — task subtype extending the runtime `task`,
                   with a `result` slot at the standard subtype offset and
                   one extra field per call arg.

The wrapper returns a tagged pointer to the state object. Every call to
`fn` (from anywhere) crosses the worker queue — the calling C frame
unwinds before the impl runs. Recursive paths through `fn` therefore use
O(1) C stack regardless of recursion depth.

Completion uses `task_complete_deferred` (yafllib) which queues the
state task rather than firing its callback synchronously. Without this,
a long [tail] chain's completion would cascade through the callback chain
and overflow the C stack in lockstep with what the dispatch was avoiding.
"""
from __future__ import annotations

import dataclasses

from codegen.gen import Application
from codegen.things import Function, Object
from codegen.ops import Op, Move, Return, Call, JumpIf, Label, NewObject
from codegen.param import (
    StackVar, ObjectField, GlobalFunction, NullPointer, NewStruct, Invoke,
    StructField, TagTask, RParam,
)
from codegen.typedecl import (
    DataPointer, Int, Struct, Type, TaskWrapper, Void, ImmediateStruct,
)
from lowering.task_abi import TASK_FIELDS, wrap_return_type, is_task_param, task_ptr_from


def _impl_name(name: str) -> str:     return f"{name}$tailimpl"
def _state_name(name: str) -> str:    return f"{name}$tailstate"
def _callback_name(name: str) -> str: return f"{name}$tailcallback"
def _chain_name(name: str) -> str:    return f"{name}$tailchain"


# A scratch slot that absorbs the unused return value of every runtime
# call. `$sv_…` is the convention recognised by the SSA validator as
# multi-write-allowed.
_DISCARD = StackVar(DataPointer(), "$sv_tail_discard")


def _runtime_call(name: str, **args: RParam) -> Op:
    """Emit a side-effecting call to a runtime C function — the
    `Move(discard, Invoke(name, args), keep=True)` boilerplate as one
    line. All runtime task primitives return `object_t*` (always NULL)
    so they're usable here uniformly."""
    return Move(_DISCARD,
                Invoke(name, NewStruct(tuple(args.items())), DataPointer()),
                keep=True)


def lower_tail_trampolines(app: Application) -> Application:
    """Expand every `[tail]`-marked Function into wrapper + impl + state
    object + dispatch callback + chain callback."""
    new_functions: dict[str, Function] = {}
    new_objects:   dict[str, Object]   = dict(app.objects)

    for name, fn in app.functions.items():
        if not fn.tail:
            new_functions[name] = fn
            continue

        if isinstance(fn.result, Void):
            raise ValueError(
                f"[tail] on {fn.name}: void-returning [tail] functions are "
                f"not supported (the state task has no result slot to chain "
                f"through). Return a value, or call the function without "
                f"[tail] if no result is needed.")

        impl_n  = _impl_name(name)
        state_n = _state_name(name)
        cb_n    = _callback_name(name)
        chain_n = _chain_name(name)

        # Rename the original to the impl; clear [tail] so the pass is idempotent.
        new_functions[impl_n] = dataclasses.replace(
            fn, name=impl_n, tail=False,
            comment=f"[tail-impl] {fn.comment or fn.name}")

        # State Object: task subtype that also stores the call args. The
        # `result` slot sits at the canonical subtype offset so callers can
        # cast state to any task subtype with the same result type and read
        # it through the normal task interface.
        arg_fields = tuple((nm, typ) for nm, typ in fn.params.fields[1:])
        new_objects[state_n] = Object(
            name=state_n,
            extends=("task",),
            functions=(),
            fields=ImmediateStruct(TASK_FIELDS + (("result", fn.result),) + arg_fields),
            comment=f"[tail] dispatch state for {fn.name}",
            is_foreign=False,
        )

        new_functions[name]    = _build_wrapper (name,    fn, state_n, cb_n)
        new_functions[cb_n]    = _build_callback(cb_n,    fn, state_n, impl_n, chain_n)
        new_functions[chain_n] = _build_chain   (chain_n, fn, state_n)

    return dataclasses.replace(app, functions=new_functions, objects=new_objects)


def _build_wrapper(name: str, fn: Function, state_n: str, cb_n: str) -> Function:
    """The public entry. Allocates the state task, copies args into it,
    posts a dispatch action to the worker queue, and returns the state as
    a tagged task. The Return value uses `TagTask` to produce the
    wrapped-shape async-pending value directly; async_lower's idempotent
    SyncWrap recognises that and leaves it alone."""
    sv_state = StackVar(DataPointer(), "$tailstate")
    wrapped  = wrap_return_type(fn.result)

    ops: list[Op] = [
        NewObject(state_n, sv_state),
        _runtime_call("task_init", self=sv_state),
    ]
    for arg_name, arg_type in fn.params.fields[1:]:
        ops.append(Move(
            ObjectField(arg_type, sv_state, state_n, arg_name, None),
            StackVar(arg_type, arg_name)))
    # thread_dispatch posts a fresh dispatch task that fires `cb_n(state, _)`
    # on the next worker iteration; state is the callback's closure.
    ops.append(_runtime_call("thread_dispatch",
                             action=GlobalFunction(cb_n, sv_state)))
    ops.append(Return(TagTask(sv_state, wrapped)))

    return Function(
        name=name,
        params=fn.params,
        result=fn.result,                          # async_lower wraps as needed
        stack_vars=Struct((("$tailstate", DataPointer()), (_DISCARD.name, DataPointer()))),
        ops=tuple(ops),
        comment=f"[tail] wrapper for {fn.name}",
        sync=False,
    )


def _build_callback(cb_n: str, fn: Function, state_n: str,
                    impl_n: str, chain_n: str) -> Function:
    """Runs on a worker thread. Calls the impl with args from state; on a
    sync result, copies it into state and deferred-completes; on an async
    result, registers the chain callback on the impl's inner task.

    `bypass_async=True` because this function operates on a task that
    isn't its own — it completes the *outer* state task in the sync path
    and chains on a separate inner task in the async path. async_lower's
    "one return-task per function" model doesn't fit, so we hand-craft
    the IS_TASK branching ourselves."""
    sv_state  = StackVar(DataPointer(), "$state")
    wrapped   = wrap_return_type(fn.result)
    sv_result = StackVar(wrapped, "$result")
    # On a TaskWrapper-wrapped sync result, the value lives in `.value`;
    # on a pointer-shaped sync result, the register itself is the value.
    sync_value = (StructField(sv_result, "value")
                  if isinstance(wrapped, TaskWrapper) else sv_result)

    ops: tuple[Op, ...] = (
        Call(function=GlobalFunction(impl_n),
             parameters=NewStruct(tuple(
                 (nm, ObjectField(typ, sv_state, state_n, nm, None))
                 for nm, typ in fn.params.fields[1:])),
             register=sv_result),

        JumpIf("$tail_async",
               Invoke("UNLIKELY",
                      NewStruct((("x", is_task_param(sv_result, wrapped)),)),
                      Int(32))),

        # Sync path: copy result into state, defer-complete, return.
        Move(ObjectField(fn.result, sv_state, state_n, "result", None), sync_value),
        _runtime_call("task_complete_deferred", self=sv_state),
        Return(NullPointer()),

        # Async path: chain on the impl's inner task.
        Label("$tail_async"),
        _runtime_call(
            "task_on_complete",
            task=Invoke("TASK_UNTAG",
                        NewStruct((("p", task_ptr_from(sv_result, wrapped)),)),
                        DataPointer()),
            cb=GlobalFunction(chain_n, sv_state)),
        Return(NullPointer()),
    )

    return Function(
        name=cb_n,
        params=Struct((("$state", DataPointer()), ("$completed", DataPointer()))),
        result=DataPointer(),
        stack_vars=Struct((("$result", wrapped), (_DISCARD.name, DataPointer()))),
        ops=ops,
        comment=f"[tail] dispatch callback for {fn.name}",
        sync=True,
        bypass_async=True,
    )


def _build_chain(chain_n: str, fn: Function, state_n: str) -> Function:
    """Runs when the impl's inner task completes. Copies the inner
    result into the state task and deferred-completes it."""
    sv_state    = StackVar(DataPointer(), "$state")
    sv_complete = StackVar(DataPointer(), "$completed")

    return Function(
        name=chain_n,
        params=Struct((("$state", DataPointer()), ("$completed", DataPointer()))),
        result=DataPointer(),
        stack_vars=Struct(((_DISCARD.name, DataPointer()),)),
        ops=(
            # Cast the inner task through state_n's layout to read `result`.
            # The field sits at the same offset in every task subtype with
            # this result type, so the cast is well-defined.
            Move(ObjectField(fn.result, sv_state,    state_n, "result", None),
                 ObjectField(fn.result, sv_complete, state_n, "result", None)),
            _runtime_call("task_complete_deferred", self=sv_state),
            Return(NullPointer()),
        ),
        comment=f"[tail] chain callback for {fn.name}",
        sync=True,
    )
