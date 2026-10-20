"""Lazy thunk infrastructure.

For each unique IR value-type T, generates a compiler-emitted stub
class `Lazy$<mangle>`, a fetch function `lazy_fetch$<mangle>` and the
`[future]` worker runner `future_run$<mangle>`.  Two source types that
lower to the same IR type share one set.

Supported value types:

  DataPointer       -> "ptr"   (Int (bigint), String, classes, pointer-
                                 distinguishable unions)
  Int(8/16/32/64)   -> "iN"
  Float(32/64)      -> "fN"
  Struct (and ImmediateStruct: tuples, mixed-union containers,
          [simple]-flattened classes) -> "s_<sha1[:12]>"

Stub layout (`lazy_thunk_t` prefix + type-specialised value):

    type    : DataPointer    -- vtable
    flag    : DataPointer    -- the gate: free / held / held + waiters / complete
    closure : FuncPointer    -- init fun_t; cleared after value is stored
    value   : <T>            -- the lazy value

The runtime owns the gate (yafllib lazy.c): two foreign functions,
`lazy_acquire`, which may suspend, and `lazy_release`, which never does.
The fetch is ordinary pre-async code — async_lower makes each call that
may suspend a suspension point, as anywhere else:

    lazy_fetch$<mangle>(this) -> T:
        if lazy_global_init_complete(this.flag): goto done
        lazy_acquire(&this.flag)              -- holds the gate, or waits
        if lazy_global_init_complete(this.flag): goto done
        value = this.closure()                -- this caller holds the gate
        this.value = value
        this.closure = {NULL, NULL}
        lazy_release(&this.flag)              -- completes every waiter
    done:
        return this.value
"""
from __future__ import annotations

import hashlib

from codegen.gen import Application
from codegen.ir import Function, Object
from codegen.ops import Op, Move, Return, Call, JumpIf, Label
from codegen.param import (
    StackVar, ObjectField, GlobalFunction, NullPointer,
    NewStruct, RuntimeInvoke, ZeroOf, PointerTo, RParam,
)
from codegen.typedecl import (
    DataPointer, Float, Int, Struct, Type, FuncPointer, Str, ImmediateStruct,
)
from lowering.task_abi import wrap_return_type


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
    if isinstance(t, FuncPointer):
        return "fun"
    if isinstance(t, Str):
        return "str"
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
def future_runner_name(t: Type)     -> str: return f"future_run${_ir_mangle(t)}"


def ir_mangle_to_type(suffix: str) -> Type:
    """Inverse of `_ir_mangle`; used by `__ensure_lazy_machinery` in
    compiler.py to decode Lazy$X references back into IR types."""
    if suffix == "ptr": return DataPointer()
    if suffix == "fun": return FuncPointer()
    if suffix == "str": return Str()
    if suffix.startswith("i"):
        bits = int(suffix[1:])
        if bits in (8, 16, 32, 64): return Int(bits)
    if suffix.startswith("f") and suffix != "fun":
        bits = int(suffix[1:])
        if bits in (32, 64): return Float(bits)
    if suffix.startswith("s_"):
        if suffix not in _STRUCT_REGISTRY:
            raise ValueError(
                f"struct mangle {suffix!r} referenced but not registered — "
                f"`_ir_mangle` must run on its IR type first.")
        return _STRUCT_REGISTRY[suffix]
    raise ValueError(f"unknown lazy thunk IR suffix {suffix!r}")


# ─── The gate ─────────────────────────────────────────────────────────────

# The runtime's gate around a stub's initialiser (yafllib lazy.c), declared
# as a `[foreign]` function is: it takes the flag's address and its result
# is None. `lazy_acquire` may suspend; `lazy_release` never does.
ACQUIRE = "lazy_acquire"
RELEASE = "lazy_release"

_NONE = Struct(())


def make_gate_function(symbol: str, sync: bool) -> Function:
    return Function(
        name=symbol,
        params=Struct((("this", DataPointer()), ("flag", DataPointer()))),
        result=_NONE,
        stack_vars=Struct(()),
        ops=(),
        comment=symbol,
        foreign_symbol=symbol,
        sync=sync,
    )


def _gate_call(symbol: str, sync: bool, flag_addr: RParam, register: StackVar) -> Call:
    return Call(GlobalFunction(symbol, c_symbol=symbol, impure=True, sync=sync),
                NewStruct((("flag", flag_addr),)), register, impure=True)


# ─── Stub class ───────────────────────────────────────────────────────────

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


# ─── Fetch function ────────────────────────────────────────────────────────

def make_fetch_function(value_type: Type) -> Function:
    cls      = stub_class_name(value_type)
    this     = StackVar(DataPointer(), "this")
    closure  = StackVar(FuncPointer(), "closure")
    value    = StackVar(value_type,    "value")
    acquired = StackVar(_NONE,         "acquired")
    released = StackVar(_NONE,         "released")

    flag_f    = ObjectField(DataPointer(), this, cls, "flag",    None)
    closure_f = ObjectField(FuncPointer(), this, cls, "closure", None)
    value_f   = ObjectField(value_type,    this, cls, "value",   None)

    is_complete = RuntimeInvoke("lazy_global_init_complete",
                                NewStruct((("p", flag_f),)), Int(32))

    ops: tuple[Op, ...] = (
        JumpIf("$done", is_complete),
        _gate_call(ACQUIRE, False, PointerTo(flag_f), acquired),
        # Complete now: another caller held the gate, and this one waited.
        JumpIf("$done", is_complete),
        Move(closure, closure_f),
        Call(closure, NewStruct(()), value),
        Move(value_f, value),
        Move(closure_f, ZeroOf(FuncPointer())),
        _gate_call(RELEASE, True, PointerTo(flag_f), released),
        Label("$done"),
        Return(value_f),
    )

    return Function(
        name=fetch_function_name(value_type),
        params=Struct((("this", DataPointer()),)),
        result=value_type,
        stack_vars=Struct((
            ("closure",  FuncPointer()),
            ("value",    value_type),
            ("acquired", _NONE),
            ("released", _NONE),
        )),
        ops=ops,
        comment=f"lazy fetch for {_ir_mangle(value_type)}",
    )


# ─── Future runner (worker-pool entry for `[future]` lets) ────────────────

def make_future_runner_function(value_type: Type) -> Function:
    """The task callback a `[future]` let posts at bind time (via the runtime's
    `future_post`): fire signature `(this=stub, task) -> object_t*`, matching
    `_task_fire`'s invocation exactly — the fetch itself must NOT be fired
    directly, since its wrapped(T) result can be a struct return (hidden sret)
    and would misread the fire's two-pointer frame.

    Body: run the ordinary fetch on the stub and discard the result. Taking
    the gate evaluates the thunk on this worker and releases any waiters;
    finding it held (a reader got in first) leaves a callback-less waiter on
    the stub's chain — completed by the release later, harmless. Either way
    every reader's own fetch sees the gate's state."""
    fname   = future_runner_name(value_type)
    fetch   = fetch_function_name(value_type)
    wrapped = wrap_return_type(value_type)

    this     = StackVar(DataPointer(), "this")
    rwrapped = StackVar(wrapped,       "result_wrapped")

    return Function(
        name=fname,
        params=Struct((("this", DataPointer()), ("$task", DataPointer()))),
        result=DataPointer(),
        stack_vars=Struct((("result_wrapped", wrapped),)),
        ops=(
            # The stub is the fetch's `this` (bound to the callback) — the
            # fetch takes no further parameters.
            Call(function=GlobalFunction(fetch, this),
                 parameters=NewStruct(()),
                 register=rwrapped),
            Return(NullPointer()),
        ),
        comment=f"[future] worker runner for {_ir_mangle(value_type)}",
        sync=False,
        bypass_async=True,
    )


# ─── Registration ─────────────────────────────────────────────────────────

def ensure_lazy_machinery(app: Application, value_type: Type) -> str:
    """Idempotently add the stub class, the fetch and the `[future]` runner
    for `value_type`, and the runtime's gate functions.  Returns the stub
    class name."""
    cls = stub_class_name(value_type)
    if cls in app.objects:
        return cls
    for symbol, sync in ((ACQUIRE, False), (RELEASE, True)):
        if symbol not in app.functions:
            app.functions[symbol] = make_gate_function(symbol, sync)
    app.objects[cls]                               = make_stub_object(value_type)
    app.functions[fetch_function_name(value_type)] = make_fetch_function(value_type)
    app.functions[future_runner_name(value_type)]  = make_future_runner_function(value_type)
    return cls
