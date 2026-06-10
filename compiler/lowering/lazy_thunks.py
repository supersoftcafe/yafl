"""Lazy thunk infrastructure.

For each unique IR value-type T, generates a compiler-emitted stub
class `Lazy$<mangle>`, a waiter task subtype `LazyWaiter$<mangle>`, a
fetch function `lazy_fetch$<mangle>`, an async finisher, and a per-
IR-type chain drain function `lazy_drain$<mangle>`.  Two source types
that lower to the same IR type share one set.

Supported value types:

  DataPointer       -> "ptr"   (Int (bigint), String, classes, pointer-
                                 distinguishable unions)
  Int(8/16/32/64)   -> "iN"
  Float(32/64)      -> "fN"
  Struct (and ImmediateStruct: tuples, mixed-union containers,
          [simple]-flattened classes) -> "s_<sha1[:12]>"

The runtime contributes only two atomic chain primitives
(`lazy_chain_swap_sentinel` and `lazy_chain_step`) plus the existing
`task_*` family — the type-aware result-slot write happens in IR via
`ObjectField(..., waiter_subtype, "result", ...)`, which routes through
`GC_WRITE_BARRIER` for pointer-containing struct fields automatically.

Stub layout (`lazy_thunk_t` prefix + type-specialised value):

    type    : DataPointer    -- vtable
    flag    : DataPointer    -- _Atomic(task_t*): NULL / chain / (task_t*)1
    closure : FuncPointer    -- init fun_t; cleared after value is stored
    value   : <T>            -- the lazy value

Waiter subtype layout (TASK_FIELDS + result):

    type, state, thread_id, callback, next, result: <T>

Fetch protocol (`bypass_async=True`: hand-built IS_TASK branching,
fetch's declared result = `wrap_return_type(T)`, returns wrapped via
`SyncWrap` or `TagTask`):

    lazy_fetch$<mangle>(this) -> wrapped(T):
        if lazy_global_init_complete(this.flag): return SyncWrap(this.value)
        waiter = NewObject(LazyWaiter$<mangle>); task_init(waiter)
        status = lazy_thunk_enqueue(&this.flag, waiter)
        match status:
            2 -> return SyncWrap(this.value)             -- raced; init complete
            0 -> return TagTask(waiter)                  -- appended; await
            1 -> result_wrapped = this.closure()
                 if IS_TASK(result_wrapped):
                     task_on_complete(closure_task, finisher(this))
                     return TagTask(waiter)
                 else:
                     value = unwrap(result_wrapped)
                     this.value = value
                     this.closure = {NULL, NULL}
                     lazy_drain$<mangle>(&this.flag, value)
                     return SyncWrap(value)

Drain protocol (`bypass_async=True`, loop with $sv-prefixed multi-write
locals):

    lazy_drain$<mangle>(this, flag_field, value: T):
        head = lazy_chain_swap_sentinel(flag_field)
        while head:
            head.result = value          -- per-IR-type Move via ObjectField
            next = lazy_chain_step(head)
            task_complete_deferred(head)
            head = next
"""
from __future__ import annotations

import hashlib

from codegen.gen import Application
from codegen.things import Function, Object
from codegen.ops import Op, Move, Return, ReturnVoid, Call, JumpIf, Jump, Label, NewObject
from codegen.param import (
    StackVar, ObjectField, StructField, GlobalFunction, NullPointer,
    NewStruct, Invoke, TagTask, RParam, IntEqConst, ZeroOf, PointerTo,
    SyncWrap,
)
from codegen.typedecl import (
    DataPointer, Float, Int, Struct, Type, FuncPointer, ImmediateStruct,
    TaskWrapper,
)
from lowering.task_abi import (
    TASK_FIELDS, wrap_return_type, is_task_param, task_ptr_from,
    task_subtype_name, make_task_foreign_object, make_task_subtype_object,
)


# Registry of struct-shape mangles → IR Type.  Populated lazily as
# `_ir_mangle` is called; consulted by `ir_mangle_to_type` to recover
# the IR type from a Lazy$<mangle> class name (sha1 isn't reversible).
# Module-level state is acceptable here: the mapping is monotonic
# (same struct shape always hashes to the same mangle) and consistent
# across compile-runs within a process.
_STRUCT_REGISTRY: dict[str, Type] = {}


# ─── Naming ───────────────────────────────────────────────────────────────

def _ir_mangle(t: Type) -> str:
    if isinstance(t, DataPointer):
        return "ptr"
    if isinstance(t, Int):
        if t.precision in (8, 16, 32, 64):
            return f"i{t.precision}"
    if isinstance(t, Float):
        if t.precision in (32, 64):
            return f"f{t.precision}"
    if isinstance(t, Struct):
        # Hash the field signature for a stable, unique mangle.  Field
        # names are part of the signature: tuples (`_0`, `_1`, …) and
        # union containers (discriminator + payload) collide otherwise.
        # 64 bits is plenty within one compilation and assert-on-collision
        # makes any silent-miscompile fail loudly if it ever happens.
        sig = "|".join(f"{n}:{_ir_mangle(ft)}" for n, ft in t.fields)
        h = hashlib.sha1(sig.encode()).hexdigest()[:16]
        mangle = f"s_{h}"
        existing = _STRUCT_REGISTRY.get(mangle)
        if existing is not None and existing != t:
            raise RuntimeError(
                f"lazy stub mangle collision: {mangle!r} maps to both "
                f"{existing!r} and {t!r}.  Widen the hash prefix or "
                f"include more identity in the signature.")
        _STRUCT_REGISTRY[mangle] = t
        return mangle
    raise NotImplementedError(
        f"lazy_thunks does not yet support {t!r}; extend `_ir_mangle`.")


def stub_class_name(t: Type)        -> str: return f"Lazy${_ir_mangle(t)}"
def fetch_function_name(t: Type)    -> str: return f"lazy_fetch${_ir_mangle(t)}"
def finisher_function_name(t: Type) -> str: return f"lazy_finish${_ir_mangle(t)}"
def drain_function_name(t: Type)    -> str: return f"lazy_drain${_ir_mangle(t)}"


def waiter_subtype_name(t: Type) -> str:
    """Name of the task subtype every `[lazy]` waiter is an instance of.
    Shared with async_lower's task-subtype naming so reads of a
    completed task's `result` field cast to the actual emitted struct
    (no cross-type punning of identical-layout structs).

    Goes through `wrap_return_type` because async_lower emits subtypes
    keyed by *unwrapped* result types, which is what we need for the
    `result: T` field anyway."""
    name = task_subtype_name(wrap_return_type(t))
    if name is None:
        raise ValueError(f"no task subtype for value type {t!r}")
    return name


def ir_mangle_to_type(suffix: str) -> Type:
    """Inverse of `_ir_mangle`; used by `__ensure_lazy_machinery` in
    compiler.py to decode Lazy$X references back into IR types."""
    if suffix == "ptr": return DataPointer()
    if suffix.startswith("i"):
        bits = int(suffix[1:])
        if bits in (8, 16, 32, 64): return Int(bits)
    if suffix.startswith("f"):
        bits = int(suffix[1:])
        if bits in (32, 64): return Float(bits)
    if suffix.startswith("s_"):
        if suffix not in _STRUCT_REGISTRY:
            raise ValueError(
                f"struct mangle {suffix!r} referenced but not registered — "
                f"`_ir_mangle` must run on its IR type first.")
        return _STRUCT_REGISTRY[suffix]
    raise ValueError(f"unknown lazy thunk IR suffix {suffix!r}")


# ─── Shared helpers ───────────────────────────────────────────────────────

_DISCARD = StackVar(DataPointer(), "$sv_lazy_discard")


def _runtime_call(name: str, **args: RParam) -> Op:
    return Move(_DISCARD,
                Invoke(name, NewStruct(tuple(args.items())), DataPointer()),
                keep=True)


def _extract_value(sv_wrapped: StackVar, value_type: Type, wrapped: Type) -> RParam:
    """Recover the raw value from the wrapped form returned by an
    async-ABI callee.  Pass-through wrap (DataPointer, FuncPointer,
    Struct-with-pointer-first-field) → the wrapped form *is* the value.
    `TaskWrapper(inner)` → extract via `.value`."""
    if wrapped is value_type or wrapped == value_type:
        return sv_wrapped
    if isinstance(wrapped, TaskWrapper):
        return StructField(sv_wrapped, "value")
    raise NotImplementedError(
        f"can't extract value from wrapped {wrapped!r}; add a case here.")


def _sync_wrap(value: RParam, wrapped: Type) -> RParam:
    """SyncWrap applies only when the return type was promoted to
    `TaskWrapper(inner)`.  For pass-through wraps the raw value already
    has the correct ABI shape."""
    if isinstance(wrapped, TaskWrapper):
        return SyncWrap(value, wrapped)
    return value


# ─── Stub class + waiter subtype ──────────────────────────────────────────

def make_stub_object(value_type: Type) -> Object:
    _ir_mangle(value_type)
    return Object(
        name=stub_class_name(value_type),
        extends=(),
        functions=(),
        fields=ImmediateStruct((
            ("type",    DataPointer()),
            ("flag",    DataPointer()),
            ("closure", FuncPointer()),
            ("value",   value_type),
        )),
        comment=f"lazy stub for {_ir_mangle(value_type)}",
        is_mutable=True,   # flag/value memoised after construction — not compactable
    )


# ─── Drain function ───────────────────────────────────────────────────────

def make_drain_function(value_type: Type) -> Function:
    """Walk the waiter chain, write `value` into each waiter's `result`
    slot, complete each waiter via task_complete_deferred.  The chain
    swap-with-sentinel happens up front so any threads that race to
    enqueue after this returns observe the (task_t*)1 sentinel and take
    the fast path on their next force."""
    waiter_ty = waiter_subtype_name(value_type)
    fname     = drain_function_name(value_type)

    flag_field = StackVar(DataPointer(), "flag_field")
    value      = StackVar(value_type,    "value")
    sv_head    = StackVar(DataPointer(), "$sv_head")
    sv_next    = StackVar(DataPointer(), "$sv_next")

    ops: tuple[Op, ...] = (
        Move(sv_head,
             Invoke("lazy_chain_swap_sentinel",
                    NewStruct((("flag", flag_field),)),
                    DataPointer())),

        Label("$loop"),
        JumpIf("$done", sv_head, invert=True),

        # head.result = value — per-IR-type write; ObjectField.to_c_store
        # emits GC_WRITE_BARRIER for pointer-containing field types.
        Move(ObjectField(value_type, sv_head, waiter_ty, "result", None), value),

        Move(sv_next,
             Invoke("lazy_chain_step",
                    NewStruct((("head", sv_head),)),
                    DataPointer())),
        _runtime_call("task_complete_deferred", self=sv_head),
        Move(sv_head, sv_next),
        Jump("$loop"),

        Label("$done"),
        Return(NullPointer()),
    )

    return Function(
        name=fname,
        params=Struct((
            ("this",       DataPointer()),
            ("flag_field", DataPointer()),
            ("value",      value_type),
        )),
        result=DataPointer(),
        stack_vars=Struct((
            ("$sv_head",        DataPointer()),
            ("$sv_next",        DataPointer()),
            (_DISCARD.name,     DataPointer()),
        )),
        ops=ops,
        comment=f"lazy chain drain for {_ir_mangle(value_type)}",
        sync=False,
        bypass_async=True,
    )


def _emit_drain_call(value_type: Type, flag_addr_expr: RParam,
                     value: RParam) -> Op:
    """`this`-less call to the per-IR-type drain function (the implicit
    `this` arg is NULL — drain ignores it)."""
    return Call(
        function=GlobalFunction(drain_function_name(value_type)),
        parameters=NewStruct((
            ("flag_field", flag_addr_expr),
            ("value",      value),
        )),
        register=None,
        result_type=DataPointer(),
    )


# ─── Fetch function ────────────────────────────────────────────────────────

def make_fetch_function(value_type: Type) -> Function:
    cls       = stub_class_name(value_type)
    fname     = fetch_function_name(value_type)
    finisher  = finisher_function_name(value_type)
    waiter_ty = waiter_subtype_name(value_type)
    wrapped   = wrap_return_type(value_type)

    this      = StackVar(DataPointer(), "this")
    waiter    = StackVar(DataPointer(), "waiter")
    status    = StackVar(Int(32),       "status")
    flag_addr = StackVar(DataPointer(), "flag_addr")
    closure   = StackVar(FuncPointer(), "closure")
    rwrapped  = StackVar(wrapped,       "result_wrapped")
    value     = StackVar(value_type,    "value")

    flag_f    = ObjectField(DataPointer(), this, cls, "flag",    None)
    closure_f = ObjectField(FuncPointer(), this, cls, "closure", None)
    value_f   = ObjectField(value_type,    this, cls, "value",   None)

    is_complete = Invoke("lazy_global_init_complete",
                         NewStruct((("p", flag_f),)),
                         Int(32))

    closure_value = _extract_value(rwrapped, value_type, wrapped)

    ops: tuple[Op, ...] = (
        JumpIf("$slow", is_complete, invert=True),
        Return(_sync_wrap(value_f, wrapped)),

        Label("$slow"),
        NewObject(waiter_ty, waiter),
        _runtime_call("task_init", self=waiter),
        Move(flag_addr, PointerTo(flag_f)),
        Move(status,
             Invoke("lazy_thunk_enqueue",
                    NewStruct((("flag", flag_addr), ("waiter", waiter))),
                    Int(32))),

        JumpIf("$already_done", IntEqConst(status, 2)),
        JumpIf("$return_waiter", IntEqConst(status, 0)),

        # status == 1: won init race.
        Move(closure, closure_f),
        Call(function=closure,
             parameters=NewStruct(()),
             register=rwrapped),

        JumpIf("$async_init",
               Invoke("UNLIKELY",
                      NewStruct((("x", is_task_param(rwrapped, wrapped)),)),
                      Int(32))),

        # Sync init: unwrap, store, clear closure, drain.
        Move(value, closure_value),
        Move(value_f, value),
        Move(closure_f, ZeroOf(FuncPointer())),
        _emit_drain_call(value_type, PointerTo(flag_f), value),
        Return(_sync_wrap(value, wrapped)),

        Label("$async_init"),
        _runtime_call(
            "task_on_complete",
            task=Invoke("TASK_UNTAG",
                        NewStruct((("p", task_ptr_from(rwrapped, wrapped)),)),
                        DataPointer()),
            cb=GlobalFunction(finisher, this)),
        Return(TagTask(waiter, wrapped)),

        Label("$already_done"),
        Return(_sync_wrap(value_f, wrapped)),

        Label("$return_waiter"),
        Return(TagTask(waiter, wrapped)),
    )

    return Function(
        name=fname,
        params=Struct((("this", DataPointer()),)),
        result=wrapped,
        stack_vars=Struct((
            ("waiter",          DataPointer()),
            ("status",          Int(32)),
            ("flag_addr",       DataPointer()),
            ("closure",         FuncPointer()),
            ("result_wrapped",  wrapped),
            ("value",           value_type),
            (_DISCARD.name,     DataPointer()),
        )),
        ops=ops,
        comment=f"lazy fetch for {_ir_mangle(value_type)}",
        sync=False,
        bypass_async=True,
    )


# ─── Finisher (async-completion callback) ─────────────────────────────────

def make_finisher_function(value_type: Type) -> Function:
    cls       = stub_class_name(value_type)
    fname     = finisher_function_name(value_type)
    waiter_ty = waiter_subtype_name(value_type)

    this      = StackVar(DataPointer(), "this")
    completed = StackVar(DataPointer(), "completed")
    value     = StackVar(value_type,    "value")

    closure_f = ObjectField(FuncPointer(), this, cls, "closure", None)
    value_f   = ObjectField(value_type,    this, cls, "value",   None)
    flag_f    = ObjectField(DataPointer(), this, cls, "flag",    None)
    completed_result = ObjectField(value_type, completed, waiter_ty, "result", None)

    ops: tuple[Op, ...] = (
        Move(value, completed_result),
        Move(value_f, value),
        Move(closure_f, ZeroOf(FuncPointer())),
        _emit_drain_call(value_type, PointerTo(flag_f), value),
        Return(NullPointer()),
    )

    return Function(
        name=fname,
        params=Struct((("this", DataPointer()), ("completed", DataPointer()))),
        result=DataPointer(),
        stack_vars=Struct((
            ("value",       value_type),
            (_DISCARD.name, DataPointer()),
        )),
        ops=ops,
        comment=f"lazy fetch async-finisher for {_ir_mangle(value_type)}",
        sync=True,
        bypass_async=True,
    )


# ─── Registration ─────────────────────────────────────────────────────────

def ensure_lazy_machinery(app: Application, value_type: Type) -> str:
    """Idempotently add the stub class, the canonical task subtype, the
    fetch + finisher + drain for `value_type`.  Returns the stub class
    name.

    The task subtype is registered here under the same name async_lower
    would assign — so every read of a completed task's `result` field
    casts to the actual emitted struct (no cross-type punning).  When
    async_lower later runs `collect_task_subtypes`, its dict-union
    against `app.objects` leaves our pre-registered entry intact."""
    cls = stub_class_name(value_type)
    if cls in app.objects:
        return cls
    if "task" not in app.objects:
        app.objects["task"] = make_task_foreign_object()
    subtype = waiter_subtype_name(value_type)
    if subtype not in app.objects:
        # The subtype's `result` field holds the raw value type — same
        # unwrapping rule async_lower's collect_task_subtypes uses
        # (TaskWrapper → inner; pass-through otherwise).
        app.objects[subtype] = make_task_subtype_object(subtype, value_type)
    app.objects[cls]                                   = make_stub_object(value_type)
    app.functions[fetch_function_name(value_type)]     = make_fetch_function(value_type)
    app.functions[finisher_function_name(value_type)]  = make_finisher_function(value_type)
    app.functions[drain_function_name(value_type)]     = make_drain_function(value_type)
    return cls
