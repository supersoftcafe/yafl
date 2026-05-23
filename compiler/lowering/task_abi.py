"""Task ABI shared between async_lower and tail_trampoline.

These helpers describe how YAFL functions communicate "the result is a
task" to their callers — both at the IR level (constructing tagged task
values, inspecting them) and at the type level (which return shapes need
a TaskWrapper).

Kept here rather than in async_lower so passes that synthesise task-aware
code (notably tail_trampoline) can share one source of truth for the ABI.
"""
from __future__ import annotations

from codegen.param import RParam, StructField, Invoke, NewStruct
from codegen.typedecl import (
    Type, DataPointer, FuncPointer, Int, Struct, TaskWrapper, Void,
    first_pointer_field,
)


# Layout of every task subtype's prefix — must match `task_t` in yafl.h
# byte-for-byte so a `(task_t*)` cast of any subtype hits each field at
# the right offset.
TASK_FIELDS: tuple[tuple[str, Type], ...] = (
    ("type",       DataPointer()),   # object_t.vtable
    ("state",      Int(32)),         # _Atomic(int32_t)
    ("thread_id",  Int(32)),         # originating worker thread index
    ("callback",   FuncPointer()),   # fun_t
    ("next",       DataPointer()),   # _Atomic(task_t*) — intrusive queue link
)


def wrap_return_type(t: Type) -> Type:
    """Adjust a function's return type so it can carry the task-pending
    signal. A pointer-shaped type carries the tag in-band; anything else
    is wrapped in `TaskWrapper {value, task*}`."""
    if isinstance(t, (Void, DataPointer, FuncPointer)):
        return t
    if isinstance(t, Struct) and first_pointer_field(t) is not None:
        return t
    return TaskWrapper(t)


def is_task_param(result_var: RParam, wrapped_type: Type) -> RParam:
    """Truthy (Int(32)) when `result_var` carries a task signal.
    `wrapped_type` is the *already-wrapped* return type."""
    if isinstance(wrapped_type, DataPointer):
        return Invoke("PTR_IS_TASK", NewStruct((("p", result_var),)), Int(32))
    if isinstance(wrapped_type, FuncPointer):
        return Invoke("PTR_IS_TASK",
                      NewStruct((("p", StructField(result_var, "o")),)), Int(32))
    if isinstance(wrapped_type, TaskWrapper):
        return StructField(result_var, "task")
    if isinstance(wrapped_type, Struct):
        fname = first_pointer_field(wrapped_type)
        if fname is not None:
            return Invoke("PTR_IS_TASK",
                          NewStruct((("p", StructField(result_var, fname)),)),
                          Int(32))
    raise ValueError(f"Cannot emit IS_TASK check for type {wrapped_type}")


def task_ptr_from(result_var: RParam, wrapped_type: Type) -> RParam:
    """Return the pointer-to-task (suitable for TASK_UNTAG) from a
    task-carrying result."""
    if isinstance(wrapped_type, DataPointer):
        return result_var
    if isinstance(wrapped_type, FuncPointer):
        return StructField(result_var, "o")
    if isinstance(wrapped_type, TaskWrapper):
        return StructField(result_var, "task")
    if isinstance(wrapped_type, Struct):
        fname = first_pointer_field(wrapped_type)
        if fname is not None:
            return StructField(result_var, fname)
    raise ValueError(f"Cannot extract task pointer from type {wrapped_type}")
