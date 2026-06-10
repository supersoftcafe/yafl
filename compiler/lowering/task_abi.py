"""Task ABI shared between async_lower and tail_trampoline.

These helpers describe how YAFL functions communicate "the result is a
task" to their callers — both at the IR level (constructing tagged task
values, inspecting them) and at the type level (which return shapes need
a TaskWrapper).

Kept here rather than in async_lower so passes that synthesise task-aware
code (notably tail_trampoline and lazy_thunks) can share one source of
truth for the ABI.
"""
from __future__ import annotations

from codegen.param import RParam, StructField, Invoke, NewStruct
from codegen.things import Object
from codegen.typedecl import (
    Type, DataPointer, FuncPointer, Int, Struct, TaskWrapper, Void,
    ImmediateStruct, first_pointer_field,
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


def task_subtype_name(result_type: Type) -> str | None:
    """Canonical name of the compiler-generated task subtype carrying
    `result_type`, or None for Void (base task_t).

    Shared between `async_lower` (which auto-emits the subtype Object
    while collecting per-function task subtypes) and any other pass that
    needs to read the result of a completed task — agreement on the
    subtype name means cross-pass ObjectField casts land on the *same*
    C struct rather than two distinct structs with merely matching
    layouts.

    Types that store the same C value in the result field share one
    subtype.  Distinct struct layouts get a unique name (hash collision
    is negligible within one compilation).
    """
    if isinstance(result_type, Void):
        return None
    # DataPointer (covers bigint, str, class pointers) — all stored as object_t*.
    # Maps to yafllib's pre-declared task_obj_t (yafl.h).
    if isinstance(result_type, DataPointer):
        return "task_obj"
    if isinstance(result_type, FuncPointer):
        return "task$FuncPointer"
    if isinstance(result_type, Int):
        return f"task$Int{result_type.precision}"
    if isinstance(result_type, TaskWrapper):
        return task_subtype_name(result_type.inner)
    # Struct (and any other type): unique subtype per distinct layout.
    return f"task$T{abs(hash(result_type))}"


def make_task_foreign_object() -> Object:
    """Foreign 'task' Object — its typedef lives in yafl.h; we publish
    the field list so subtypes can extend it via normal YAFL inheritance
    and ObjectField accesses to inherited fields resolve at the correct
    offsets."""
    return Object(
        name="task",
        extends=(),
        functions=(),
        fields=ImmediateStruct(TASK_FIELDS),
        comment="foreign task_t — declared in yafllib/yafl.h",
        is_foreign=True,
    )


def make_task_subtype_object(subtype_name: str, result_type: Type) -> Object:
    """A task subtype carrying `result_type` in its trailing `result`
    field.  `task_obj` is pre-declared in yafllib (yafl.h's task_obj_t
    + TASK_OBJ_VTABLE aliased as obj_task_obj) so we mark it foreign;
    other subtypes are compiler-emitted via the usual class machinery."""
    return Object(
        name=subtype_name,
        extends=("task",),
        functions=(),
        fields=ImmediateStruct(TASK_FIELDS + (("result", result_type),)),
        comment=f"task subtype for result type {result_type}",
        is_foreign=subtype_name == "task_obj",
        is_mutable=True,   # state/result/next written after construction — not compactable
    )


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
