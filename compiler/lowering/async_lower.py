from __future__ import annotations

# Async lowering: convert each function that has non-tail calls into two C functions:
#   1. Hot path  – original name, runs fully inline if all calls are sync.
#      After each non-tail call, emits an UNLIKELY(IS_TASK) check; if true,
#      branches to cold code at the tail that saves locals to a heap state
#      object, creates a task, registers foo$async as callback, and returns
#      the tagged task.
#   2. State machine  – named foo$async, signature void(object_t* $state,
#      object_t* $completed_task).  Dispatches on $state->idx to extract the
#      completed call's result and resume execution.  Each further async call
#      updates $state->idx, re-registers the same foo$async callback, and
#      returns void.  When execution completes it writes the result into the
#      task and calls task_complete.

import dataclasses
from dataclasses import dataclass
from itertools import chain
from typing import Iterable
from functools import reduce

import langtools
from codegen.gen import Application
from codegen.ops import Op, Call, Return, ReturnVoid, Move, Label, JumpIf, IfTask, Jump, NewObject, SwitchJump, Abort, ParallelCall
from codegen.things import Function, Object
from codegen.typedecl import (
    FuncPointer, Void, Struct, ImmediateStruct, DataPointer, Int, Str, Type,
    TaskWrapper, first_pointer_field, is_task_check,
)
from codegen.param import (
    ObjectField, StackVar, LParam, GlobalVar, NewStruct, GlobalFunction, Integer,
    RParam, StructField, NullPointer, Invoke, TagTask, IntEqConst, ZeroOf, SyncWrap,
)


# ─────────────────────────────────────────────────────────────────────────────
# BasicBlock: same data structure as before (liveness analysis unchanged)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class BasicBlock:
    name: str          # label name placed right after the block's terminal call
    ops: list[Op]      # all ops including the terminal call, then Label(name)
    live: dict[StackVar, LParam]  # vars that must be saved before the terminal call
    result: LParam | None         # register that receives the call result


# ─────────────────────────────────────────────────────────────────────────────
# Standard params in the state-machine function
# ─────────────────────────────────────────────────────────────────────────────

__state_param_var     = StackVar(DataPointer(), "$state")
__completed_param_var = StackVar(DataPointer(), "$completed_task")

# Hot-path scratch variables. Reused across every call site within one
# function because the hot path only has a single shared $asynccommon block,
# so a single set of locals is enough. The state-machine function instead
# allocates *per-call-site* StackVars (named $sv_par_sm$i, $sv_launcher_sm$i)
# because each call site emits its own cold block that may run independently.
__sv_state      = StackVar(DataPointer(), "$sv_state")
__sv_task       = StackVar(DataPointer(), "$sv_task")
__sv_discard    = StackVar(DataPointer(), "$sv_discard")
__sv_call_id    = StackVar(Int(32),       "$sv_call_id")    # call-site index for asynccommon
__sv_async_task = StackVar(DataPointer(), "$sv_async_task") # TASK_UNTAG'd task ptr for asynccommon
__sv_par_task   = StackVar(DataPointer(), "$sv_par_task")   # par_task ptr in parallel cold blocks
__sv_launcher   = StackVar(DataPointer(), "$sv_launcher")   # launcher task ptr


# ─────────────────────────────────────────────────────────────────────────────
# Per-pattern emit helpers
#
# Each one returns a tuple of Ops for the caller to extend(...) into its own
# op list.  These patterns appear in both the hot path and the state machine
# with only minor variations (which scratch vars, which fn$async target);
# parameterising the helpers keeps the two emission sites in lockstep.
# ─────────────────────────────────────────────────────────────────────────────

def _emit_par_task_setup(par_task_var: StackVar, par_task_name: str,
                          closures: tuple[RParam, ...]) -> tuple[Op, ...]:
    """Allocate a par_task, init it, set `remaining`, store per-slot closures."""
    par_n = len(closures)
    setup: list[Op] = [
        NewObject(par_task_name, par_task_var),
        Move(__sv_discard,
             Invoke("task_init", NewStruct((("task", par_task_var),)), DataPointer()),
             keep=True),
        Move(ObjectField(Int(32), par_task_var, par_task_name, "remaining", None),
             Integer(par_n, 32)),
    ]
    for k, closure in enumerate(closures):
        setup.append(Move(
            ObjectField(DataPointer(), par_task_var, par_task_name, f"closure_{k}", None),
            closure))
    return tuple(setup)


def _emit_post_launcher(launcher_var: StackVar, par_task_var: StackVar,
                         fn_name: str, call_site: int, slot: int) -> tuple[Op, ...]:
    """Create one launcher task wired to fire slot K's lambda on a worker thread."""
    launcher_cb = GlobalFunction(f"{fn_name}$par${call_site}$launcher${slot}", par_task_var)
    return (
        Move(launcher_var,
             Invoke("task_create", NewStruct((("self", NullPointer()),)), DataPointer())),
        Move(__sv_discard,
             Invoke("task_on_complete",
                    NewStruct((("task", launcher_var), ("cb", launcher_cb))),
                    DataPointer()),
             keep=True),
        Move(__sv_discard,
             Invoke("thread_work_post_parallel",
                    NewStruct((("task", launcher_var),)), DataPointer()),
             keep=True),
    )


def _emit_task_alloc(sv_task: StackVar, task_subtype_name: str | None) -> tuple[Op, ...]:
    """Allocate the task object that this function will fulfil.

    Three paths, all leaving sv_task pointing at a fully task_init'd task:
      - None        : Void-returning function uses the base task_t.
      - "task_obj"  : pre-declared yafllib subtype (task_obj_create initialises).
      - other       : compiler-synthesised subtype, allocate via NewObject + task_init.
    """
    if task_subtype_name is None:
        return (Move(sv_task,
            Invoke("task_create", NewStruct((("self", NullPointer()),)), DataPointer())),)
    if task_subtype_name == "task_obj":
        return (Move(sv_task,
            Invoke("task_obj_create", NewStruct((("self", NullPointer()),)), DataPointer())),)
    return (
        NewObject(task_subtype_name, sv_task),
        Move(__sv_discard,
             Invoke("task_init", NewStruct((("task", sv_task),)), DataPointer()),
             keep=True),
    )


def _emit_suspend_to_async(idx_field: LParam, idx: int, untagged_task: RParam,
                            fn_name: str) -> tuple[Op, ...]:
    """SM cold-block tail: write idx, register fn$async on the in-flight task, return.

    `untagged_task` must already be a clean task_t pointer (no PTR_TAG_TASK bit
    set). Call-site cold blocks should wrap their tagged result in TASK_UNTAG
    before invoking; the parallel-suspend site passes its locally-allocated
    par_task directly.
    """
    callback = GlobalFunction(f"{fn_name}$async", __state_param_var)
    return (
        Move(idx_field, Integer(idx, 32)),
        Move(__sv_discard,
             Invoke("task_on_complete",
                    NewStruct((("task", untagged_task), ("cb", callback))),
                    DataPointer()),
             keep=True),
        ReturnVoid(),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tail-call detection (unchanged from old CPS pass)
# ─────────────────────────────────────────────────────────────────────────────

def __discover_tail_calls(fn: Function) -> Function:
    """Mark Calls in literal tail position as `musttail`.

    A Call qualifies when it is immediately followed by a Return whose value
    is the Call's result register, AND the Call's result type matches
    fn.result. The match is on the *unwrapped* type (this pass runs before
    __wrap_return_type is applied) — once both sides go through the same
    wrapping in lowering, they will still match at the C level.

    For void functions: a void Call followed by ReturnVoid also qualifies.

    Effect downstream:
      * `__create_basic_blocks` partitions on non-musttail Calls only, so
        musttail Calls do NOT split a basic block — a function whose only
        non-trivial calls are tail-calls becomes a single block, taking the
        simple-wrapper path with no state machine generated.
      * Codegen emits `return foo(...)` for musttail Calls, which clang TCOs
        even at -O0. Without this, every recursion accumulates a real C
        stack frame (the IS_TASK check inserted after the call breaks the
        literal tail position the C compiler would otherwise see).

    Currently only applied to **sync** functions (`fn.sync`).  Sync functions
    don't generate a state machine, so the removed Return + musttail Call is
    safe everywhere downstream.  Async functions would also benefit from this
    optimisation but the state machine's terminal-block processing requires
    the original Return to drive its task_complete sequence — without it the
    state machine never completes the in-flight task, and the resulting CFG
    contains a fall-through cycle that hangs `strip_unused_operations`.
    Extending this to async functions is tracked in TODO.md.
    """
    if not fn.sync:
        return fn
    ops = list(fn.ops)
    if len(ops) < 2:
        return fn

    new_ops: list[Op] = []
    i = 0
    n = len(ops)
    while i < n:
        op = ops[i]
        nxt = ops[i + 1] if i + 1 < n else None

        # Pattern 1 — non-void tail call: Call(register=R) ; Return(R)
        # where R's type matches fn.result.
        if (isinstance(op, Call)
                and not op.musttail
                and op.register is not None
                and isinstance(nxt, Return)
                and isinstance(nxt.value, StackVar)
                and nxt.value.name == op.register.name
                and op.register.get_type() == fn.result):
            result_type = op.register.get_type()
            new_ops.append(dataclasses.replace(
                op, musttail=True, register=None, result_type=result_type))
            i += 2
            continue

        # Pattern 2 — void tail call: Call(register=None, result_type=Void) ; ReturnVoid
        if (isinstance(op, Call)
                and not op.musttail
                and op.register is None
                and (op.result_type is None or isinstance(op.result_type, Void))
                and isinstance(nxt, ReturnVoid)
                and isinstance(fn.result, Void)):
            new_ops.append(dataclasses.replace(op, musttail=True))
            i += 2
            continue

        new_ops.append(op)
        i += 1

    return dataclasses.replace(fn, ops=tuple(new_ops))


# ─────────────────────────────────────────────────────────────────────────────
# Liveness analysis (unchanged)
# ─────────────────────────────────────────────────────────────────────────────

def __calculate_saved_vars(fn: Function) -> Function:
    labels = {op.name: index for index, op in enumerate(fn.ops) if isinstance(op, Label)}

    def do_a_pass(ops: tuple[Op, ...]) -> tuple[Op, ...]:
        def saved_set_at(index: int) -> frozenset[StackVar]:
            op = ops[index]
            next_live, _ = op.get_live_vars()
            return next_live | op.saved_vars

        def calc(index: int) -> Op:
            op = ops[index]
            if index >= len(ops) - 1:
                ss1 = frozenset()
            elif isinstance(op, Jump):
                ss1 = saved_set_at(labels[op.name]) if op.name in labels else frozenset()
            else:
                ss1 = saved_set_at(index + 1)
            ss2 = frozenset() if not isinstance(op, JumpIf) else saved_set_at(labels[op.label])
            this_live, this_dead = op.get_live_vars()
            saved_vars = (ss1 | ss2) - this_dead
            return dataclasses.replace(op, saved_vars=saved_vars)

        return tuple(calc(index) for index in range(len(ops)))

    def iterate(ops: tuple[Op, ...]) -> tuple[Op, ...]:
        new_ops = do_a_pass(ops)
        return new_ops if ops == new_ops else iterate(new_ops)

    return dataclasses.replace(fn, ops=iterate(fn.ops))


# ─────────────────────────────────────────────────────────────────────────────
# Basic-block splitting (unchanged logic, same output shape)
# ─────────────────────────────────────────────────────────────────────────────

def __vars_to_state_fields(vars: Iterable[StackVar], state_name: str) -> dict[StackVar, LParam]:
    return {var: ObjectField(var.get_type(), __state_param_var, state_name, var.name, None)
            for var in vars}


def __convert_var_to_field_refs(ops: Iterable[Op],
                                 vars_to_fields: dict[str, LParam]) -> tuple[Op, ...]:
    # Each StackVar name within a function is unique to one declaration
    # site (match arms get per-arm mangled names — see match._arm_unique_name),
    # so name-keyed substitution maps each occurrence to the right state field.
    def replacer(p: RParam) -> RParam:
        if isinstance(p, StackVar) and p.name in vars_to_fields:
            return vars_to_fields[p.name]
        return p
    return tuple(op.replace_params(replacer) for op in ops)


def __create_basic_blocks(fn: Function, state_name: str) -> list[BasicBlock]:
    liveness_fn = __calculate_saved_vars(fn)
    partitions = langtools.partition(liveness_fn.ops,
                                     lambda op: (isinstance(op, Call) and not op.musttail)
                                                 or isinstance(op, ParallelCall))

    def make_block(index: int, ops: list[Op]) -> BasicBlock:
        name = f"cont${index}"
        last_op = ops[-1]
        result = last_op.register if isinstance(last_op, (Call, ParallelCall)) else None
        augmented = ops
        live_vars = {var: ObjectField(var.get_type(), __state_param_var, state_name, var.name, None)
                     for var in last_op.saved_vars}
        return BasicBlock(name, augmented, live_vars, result)

    return [make_block(i, ops) for i, ops in enumerate(partitions)]


# ─────────────────────────────────────────────────────────────────────────────
# Return-type helpers
# ─────────────────────────────────────────────────────────────────────────────

def __wrap_return_type(t: Type) -> Type:
    """Adjust a function's return type to carry the task-pending signal."""
    if isinstance(t, (Void, DataPointer, Str, FuncPointer)):
        return t        # pointer types use PTR_TAG_TASK bit; Void stays Void
    if isinstance(t, Int) and t.precision == 0:
        return t        # bigint is object_t* — pointer tagging works
    if isinstance(t, Struct) and first_pointer_field(t) is not None:
        return t        # struct with a pointer field: tag via that field
    return TaskWrapper(t)   # pure primitive: wrap in {value, task*} struct


def __task_subtype_name(result_type: Type) -> str | None:
    """Name of the compiler-generated task subtype, or None for Void (base task_t).

    Types that store the same C value in the result field share one subtype.
    Distinct struct layouts always get a unique name (collision probability of
    abs(hash) is negligible within a single compilation).
    """
    if isinstance(result_type, Void):
        return None
    # Pointer-compatible: DataPointer, Str, bigint (Int(0)) — all stored as object_t*.
    # This maps to yafllib's pre-declared task_obj_t (yafl.h) and its vtable
    # obj_task_obj, so we use the concrete yafllib name rather than synthesising one.
    if (isinstance(result_type, (DataPointer, Str))
            or (isinstance(result_type, Int) and result_type.precision == 0)):
        return "task_obj"
    # FuncPointer: stored as fun_t
    if isinstance(result_type, FuncPointer):
        return "task$FuncPointer"
    # Fixed-width integer: stored as intN_t
    if isinstance(result_type, Int):
        return f"task$Int{result_type.precision}"
    # TaskWrapper: the task stores the unwrapped inner type
    if isinstance(result_type, TaskWrapper):
        return __task_subtype_name(result_type.inner)
    # Struct (or any other type): unique subtype per distinct layout
    return f"task$T{abs(hash(result_type))}"


def __is_task_param(result_var: RParam, wrapped_type: Type) -> RParam:
    """RParam that is truthy (Int(32)) when result_var carries a task signal.

    `wrapped_type` must be the *already-wrapped* return type (i.e. the value
    returned by __wrap_return_type), not the original callee return type.
    """
    if isinstance(wrapped_type, (DataPointer, Str)):
        return Invoke("PTR_IS_TASK", NewStruct((("p", result_var),)), Int(32))
    if isinstance(wrapped_type, FuncPointer):
        return Invoke("PTR_IS_TASK",
                      NewStruct((("p", StructField(result_var, "o")),)), Int(32))
    if isinstance(wrapped_type, Int) and wrapped_type.precision == 0:
        return Invoke("PTR_IS_TASK", NewStruct((("p", result_var),)), Int(32))
    if isinstance(wrapped_type, Struct):
        fname = first_pointer_field(wrapped_type)
        if fname:
            return Invoke("PTR_IS_TASK",
                          NewStruct((("p", StructField(result_var, fname)),)), Int(32))
    if isinstance(wrapped_type, TaskWrapper):
        return StructField(result_var, "task")  # truthy when non-NULL
    raise ValueError(f"Cannot generate IS_TASK check for type {wrapped_type}")


def __task_ptr_from(result_var: RParam, wrapped_type: Type) -> RParam:
    """Return the pointer-to-task (suitable for TASK_UNTAG) from a task-carrying result."""
    if isinstance(wrapped_type, TaskWrapper):
        return StructField(result_var, "task")   # plain task ptr in .task; TASK_UNTAG is no-op
    if isinstance(wrapped_type, (DataPointer, Str)):
        return result_var                         # result IS the tagged pointer
    if isinstance(wrapped_type, Int) and wrapped_type.precision == 0:
        return result_var                         # bigint = object_t*
    if isinstance(wrapped_type, FuncPointer):
        return StructField(result_var, "o")       # .o holds the tagged task pointer
    if isinstance(wrapped_type, Struct):
        fname = first_pointer_field(wrapped_type)
        if fname:
            return StructField(result_var, fname)
    raise ValueError(f"Cannot extract task ptr from wrapped type {wrapped_type}")


def __extract_from_task(completed_task: RParam, callee_result_type: Type,
                        task_subtype_name: str | None) -> RParam:
    """Read the result from a completed task object."""
    if task_subtype_name is None or isinstance(callee_result_type, Void):
        return NullPointer()
    return ObjectField(callee_result_type, completed_task, task_subtype_name, "result", None)


def __zero_val(t: Type) -> RParam:
    """Explicit zero/null initialiser for a field (never rely on object_create zero-fill)."""
    if isinstance(t, (DataPointer, Str)) or (isinstance(t, Int) and t.precision == 0):
        return NullPointer()
    if isinstance(t, Int):
        return Integer(0, t.precision)
    return ZeroOf(t)


# ─────────────────────────────────────────────────────────────────────────────
# State object generation
# ─────────────────────────────────────────────────────────────────────────────

def __create_state_object(fn: Function, state_name: str,
                           basic_blocks: list[BasicBlock]) -> Object:
    """Object that stores all state needed across async suspensions."""
    # Collect every live var and every call-result register
    fields: dict[str, Type] = {}
    for bb in basic_blocks[:-1]:
        for var in bb.live:
            fields[var.name] = var.get_type()
        if bb.result is not None and isinstance(bb.result, StackVar):
            fields[bb.result.name] = bb.result.get_type()

    heap_fields: tuple[tuple[str, Type], ...] = (
        ("type",    DataPointer()),   # vtable (required first field)
        ("my_task", DataPointer()),   # our task (what we're fulfilling)
        ("idx",     Int(32)),         # which call site we're suspended at
    )
    heap_fields += tuple((name, typ) for name, typ in fields.items())
    return Object(state_name, (), (), ImmediateStruct(heap_fields), comment=fn.comment)


# ─────────────────────────────────────────────────────────────────────────────
# Hot-path function
# ─────────────────────────────────────────────────────────────────────────────

def __create_hot_path_func(fn: Function, state_name: str,
                            task_subtype_name: str | None,
                            basic_blocks: list[BasicBlock]) -> Function:
    """
    Original function signature (return type possibly wrapped for primitives).
    After each non-tail call, emits an UNLIKELY(IS_TASK) guard.

    When the guard fires the cold block writes only two locals ($sv_call_id and
    $sv_async_task) then jumps to the shared $asynccommon label.  All state
    allocation, live-var saves, task creation, and callback registration happen
    once in that shared tail, eliminating per-call-site duplication.

    GC safety: every var that will ever be saved in $asynccommon is
    null/zero-initialised in the function prologue so that earlier cold blocks
    never write garbage pointer values into the state object.
    """
    wrapped_result = __wrap_return_type(fn.result)
    wrap_fields: list[tuple[str, Type]] = []

    # ── Collect all vars that end up as state-object fields ──────────────────
    # Used both for the prologue null-inits and for the common save block.
    # Preserve insertion order so the generated C is deterministic.
    seen_state_var_names: set[str] = set()
    all_state_vars: list[StackVar] = []
    for bb in basic_blocks[:-1]:
        for var in bb.live:
            if var.name not in seen_state_var_names:
                all_state_vars.append(var)
                seen_state_var_names.add(var.name)
        if bb.result is not None and isinstance(bb.result, StackVar):
            rv = bb.result
            if rv.name not in seen_state_var_names:
                all_state_vars.append(rv)
                seen_state_var_names.add(rv.name)

    # ── Prologue: null/zero-init LOCAL state-tracked vars ────────────────────
    # A cold block at call site N may fire before vars that are only live at
    # call sites >N have been assigned.  Initialising them here ensures that
    # the common save block always writes a valid GC-traceable value.
    # Parameters are always initialised by the caller and must NOT be touched.
    param_names = {name for name, _ in fn.params.fields}
    hot_ops: list[Op] = [
        Move(var, __zero_val(var.get_type()))
        for var in all_state_vars
        if var.name not in param_names
    ]

    # ── Per-call-site hot path ────────────────────────────────────────────────

    for i, bb in enumerate(basic_blocks[:-1]):
        call_op = bb.ops[-1]

        if isinstance(call_op, ParallelCall):
            par_task_name = f"task$par${i}${fn.name}"
            closures = tuple(
                call_ref.object if isinstance(call_ref, GlobalFunction) and call_ref.object is not None
                else NullPointer()
                for call_ref in call_op.calls)

            hot_ops.extend(bb.ops[:-1])
            hot_ops.extend(_emit_par_task_setup(__sv_par_task, par_task_name, closures))
            for k in range(len(call_op.calls)):
                hot_ops.extend(_emit_post_launcher(__sv_launcher, __sv_par_task, fn.name, i, k))

            # Hand off to $asynccommon
            hot_ops.append(Move(__sv_async_task, __sv_par_task))
            hot_ops.append(Move(__sv_call_id, Integer(i + 1, 32)))
            hot_ops.append(Jump("$asynccommon"))
            continue

        assert isinstance(call_op, Call) and not call_op.musttail
        result_var = call_op.register

        if result_var is None:
            discarded_type = call_op.result_type
            if discarded_type is None:
                # Truly void-returning — cannot be a task; emit unchanged
                hot_ops.extend(bb.ops)
                continue
            # Non-void async call with discarded result: still need the task check
            # so the C cast uses the correct wrapped return type (avoids sret ABI mismatch).
            discarded_wrapped = __wrap_return_type(discarded_type)
            sv_discard_wrap = StackVar(discarded_wrapped, f"$wrap${i}")
            wrap_fields.append((f"$wrap${i}", discarded_wrapped))
            hot_ops.extend(bb.ops[:-1])
            hot_ops.append(dataclasses.replace(call_op, register=sv_discard_wrap))
            task_ptr = __task_ptr_from(sv_discard_wrap, discarded_wrapped)
            hot_ops.append(IfTask(
                condition=__is_task_param(sv_discard_wrap, discarded_wrapped),
                task_source=task_ptr,
                task_lhs=__sv_async_task,
                call_id_lhs=__sv_call_id,
                call_id=i + 1,
                target="$asynccommon"))
            # Value is discarded — no Move needed
            continue

        result_type  = result_var.get_type()
        wrapped_type = __wrap_return_type(result_type)
        needs_temp   = (wrapped_type is not result_type)

        if needs_temp:
            # Pure-primitive callee: receive result in a temp wrapped-type var,
            # then unwrap on the sync path.
            sv_wrapped = StackVar(wrapped_type, f"$wrap${i}")
            wrap_fields.append((f"$wrap${i}", wrapped_type))
            hot_ops.extend(bb.ops[:-1])
            hot_ops.append(dataclasses.replace(call_op, register=sv_wrapped))
            sv_for_check = sv_wrapped
        else:
            hot_ops.extend(bb.ops)
            sv_for_check = result_var

        task_ptr = __task_ptr_from(sv_for_check, wrapped_type)
        hot_ops.append(IfTask(
            condition=__is_task_param(sv_for_check, wrapped_type),
            task_source=task_ptr,
            task_lhs=__sv_async_task,
            call_id_lhs=__sv_call_id,
            call_id=i + 1,     # 1-based: idx==0 must never reach dispatch
                               # (zero-init heap means uninitialised state)
            target="$asynccommon"))

        # Sync path: unwrap primitive if needed
        if needs_temp:
            hot_ops.append(Move(result_var, StructField(sv_wrapped, "value")))

    # Terminal block
    terminal_ops: list[Op] = list(basic_blocks[-1].ops)
    if isinstance(wrapped_result, TaskWrapper):
        new_terminal: list[Op] = []
        for op in terminal_ops:
            if isinstance(op, Return):
                new_terminal.append(Return(SyncWrap(op.value, wrapped_result)))
            elif isinstance(op, Call) and op.musttail:
                # Musttail tail-call to a callee that also returns TaskWrapper:
                # update result_type so the C cast uses the wrapped typedef.
                new_terminal.append(dataclasses.replace(op, result_type=wrapped_result))
            else:
                new_terminal.append(op)
        terminal_ops = new_terminal
    hot_ops.extend(terminal_ops)

    # ── Shared $asynccommon block ─────────────────────────────────────────────
    # All Call sites jump here when IS_TASK fires. The label is the same in
    # every function — what it does depends on whether this function can
    # legally suspend:
    #   * sync  → emit Abort (a "sync" function has been proven not to
    #             suspend, so reaching here means a downstream call broke
    #             that contract; better to crash than corrupt state).
    #   * async → allocate state, save live vars, create task, register
    #             continuation callback, return tagged task pointer.
    common_ops: list[Op] = [Label("$asynccommon")]

    has_par = any(isinstance(bb.ops[-1], ParallelCall) for bb in basic_blocks[:-1])

    if fn.sync:
        common_ops.append(Abort(reason="sync function reached $asynccommon"))
        par_fields = (("$sv_par_task", DataPointer()), ("$sv_launcher", DataPointer()), ("$sv_discard", DataPointer())) if has_par else ()
        extra_stack = Struct((
            ("$sv_call_id",    Int(32)),
            ("$sv_async_task", DataPointer()),
        ) + par_fields + tuple(wrap_fields))
        all_ops = tuple(hot_ops) + tuple(common_ops)
        return dataclasses.replace(fn,
                                   result=wrapped_result,
                                   ops=all_ops,
                                   stack_vars=fn.stack_vars + extra_stack)

    # Allocate state object
    common_ops.append(NewObject(state_name, __sv_state))

    # Save all state-tracked vars (the union across all call sites).
    # Vars not yet assigned at this call site carry their prologue zero/null,
    # which is GC-safe and will be overwritten by the state machine on resume.
    for var in all_state_vars:
        common_ops.append(Move(
            ObjectField(var.get_type(), __sv_state, state_name, var.name, None),
            var))

    # Set my_task = NULL before task allocation so the GC sees a valid field
    # if it traces the state object during NewObject(task).
    common_ops.append(Move(
        ObjectField(DataPointer(), __sv_state, state_name, "my_task", None),
        NullPointer()))

    # Record which call site caused the suspension
    common_ops.append(Move(
        ObjectField(Int(32), __sv_state, state_name, "idx", None),
        __sv_call_id))

    # Create the task subtype (or base task_t for Void-returning functions).
    # The helper ensures task_init() has been called regardless of which path
    # is taken — never rely on zero-fill alone for state/thread_id/next.
    common_ops.extend(_emit_task_alloc(__sv_task, task_subtype_name))

    # Link state → task (GC will trace my_task from here on)
    common_ops.append(Move(
        ObjectField(DataPointer(), __sv_state, state_name, "my_task", None),
        __sv_task))

    # Register the state machine as the callback on the in-flight task
    callback = GlobalFunction(f"{fn.name}$async", __sv_state)
    common_ops.append(Move(
        __sv_discard,
        Invoke("task_on_complete",
               NewStruct((("task", __sv_async_task), ("cb", callback))),
               DataPointer()),
        keep=True))
    common_ops.append(Return(TagTask(__sv_task, wrapped_result)))

    par_fields = (("$sv_par_task", DataPointer()), ("$sv_launcher", DataPointer())) if has_par else ()
    extra_stack = Struct((
        ("$sv_state",      DataPointer()),
        ("$sv_task",       DataPointer()),
        ("$sv_discard",    DataPointer()),
        ("$sv_call_id",    Int(32)),
        ("$sv_async_task", DataPointer()),
    ) + par_fields + tuple(wrap_fields))
    all_ops = tuple(hot_ops) + tuple(common_ops)
    return dataclasses.replace(fn,
                               result=wrapped_result,
                               ops=all_ops,
                               stack_vars=fn.stack_vars + extra_stack)


# ─────────────────────────────────────────────────────────────────────────────
# State-machine function
# ─────────────────────────────────────────────────────────────────────────────

def __create_state_machine_func(fn: Function, state_name: str,
                                 task_subtype_name: str | None,
                                 basic_blocks: list[BasicBlock]) -> Function:
    """
    void foo$async(object_t* $state, object_t* $completed_task)

    Dispatches on $state->idx, extracts the result from $completed_task, then
    runs the remainder of the function as a state machine.  All live-variable
    and result-variable references in the body are substituted to state fields.
    """
    non_terminal = basic_blocks[:-1]   # blocks that end with a non-tail call
    n = len(non_terminal)

    # Build substitution map: variable name → ObjectField into $state.
    # Keyed by name (not full StackVar) because the same physical variable
    # can appear with different IR types in different contexts — most
    # commonly a match-arm rebinding reinterpreting a union pointer. The
    # state struct is also one field per unique name, and both types map
    # to the same C variable, so the substitution needs to match by name
    # to stay consistent.
    vars_to_fields: dict[str, LParam] = {}
    for bb in non_terminal:
        for var, field in bb.live.items():
            vars_to_fields.setdefault(var.name, field)
        if bb.result is not None and isinstance(bb.result, StackVar):
            vars_to_fields.setdefault(bb.result.name, ObjectField(
                bb.result.get_type(), __state_param_var, state_name,
                bb.result.name, None))

    idx_field = ObjectField(Int(32), __state_param_var, state_name, "idx", None)
    my_task_field = ObjectField(DataPointer(), __state_param_var, state_name, "my_task", None)

    def to_state_field(p: RParam) -> RParam:
        if isinstance(p, StackVar) and p.name in vars_to_fields:
            return vars_to_fields[p.name]
        return p

    sm_ops: list[Op] = []
    cold_ops: list[Op] = []
    sm_wrap_fields: list[tuple[str, Type]] = []

    # ── Dispatch: switch on idx (1-based); every valid resume has a case
    #    mapped to a label in dispatch_ops; idx==0 (uninitialised state) and
    #    any out-of-range value hit the default abort. ──────────────────────
    sm_ops.append(SwitchJump(idx_field, tuple((i + 1, f"$case${i + 1}") for i in range(n))))

    sm_ops.append(Label(f"$resume$0"))  # resume point for first-call completion

    # ── Body: bb[1]..bb[N-1] ops, with StackVar → state field substitution ──
    for i in range(1, n):
        bb = non_terminal[i]
        body_ops_before_call = bb.ops[:-1]
        call_op_orig         = bb.ops[-1]

        substituted_before = __convert_var_to_field_refs(body_ops_before_call, vars_to_fields)
        sm_ops.extend(substituted_before)

        if isinstance(call_op_orig, ParallelCall):
            par_task_name = f"task$par${i}${fn.name}"

            pc_subst_calls = tuple(c.replace_params(to_state_field) for c in call_op_orig.calls)

            sv_par_sm      = StackVar(DataPointer(), f"$sv_par_sm${i}")
            sv_launcher_sm = StackVar(DataPointer(), f"$sv_launcher_sm${i}")
            sm_wrap_fields.append((sv_par_sm.name, DataPointer()))
            sm_wrap_fields.append((sv_launcher_sm.name, DataPointer()))

            closures = tuple(
                c.object if isinstance(c, GlobalFunction) and c.object is not None else NullPointer()
                for c in pc_subst_calls)
            sm_ops.extend(_emit_par_task_setup(sv_par_sm, par_task_name, closures))
            for k in range(len(pc_subst_calls)):
                sm_ops.extend(_emit_post_launcher(sv_launcher_sm, sv_par_sm, fn.name, i, k))

            # Register fn$async on par_task and suspend; dispatch case$i+1 will
            # land at $resume$i after the par_task completes.
            sm_ops.extend(_emit_suspend_to_async(idx_field, i + 1, sv_par_sm, fn.name))
            sm_ops.append(Label(f"$resume${i}"))
            # No cold_ops entry needed — always takes the launcher path
            continue

        result_type     = call_op_orig.register.get_type() if call_op_orig.register else None
        discarded_type  = None if result_type is not None else call_op_orig.result_type
        wrapped_type    = __wrap_return_type(result_type)  if result_type else None
        needs_temp      = result_type is not None and (wrapped_type is not result_type)

        call_subst = call_op_orig.replace_params(to_state_field)

        # The `$resume${i}` label marks the point both the sync fall-through
        # *after* the IS_TASK check+unpack and the dispatch path (from
        # `$case${i+1}`) converge.  The check+unpack reads the local wrap
        # slot written by the Call op just above; the dispatch path reaches
        # `$resume${i}` without having run that Call, so the check+unpack
        # must sit *before* the label — on the sync edge only — and never be
        # re-entered on resume.  Dispatch writes the extracted result into
        # the state field and lands at the label with the check already
        # satisfied.

        # Decide which var receives the call's result for the IS_TASK check, and
        # whether we need to unwrap a primitive into the destination state field
        # on the sync edge.
        if discarded_type is not None:
            # Non-void call whose result was stripped by dead-store elimination.
            # Still need to check for async and use the correct C cast (sret ABI).
            check_type = __wrap_return_type(discarded_type)
            sv_check = StackVar(check_type, f"$sm_wrap${i}")
            sm_wrap_fields.append((sv_check.name, check_type))
            sm_ops.append(dataclasses.replace(call_subst, register=sv_check))
            unwrap_op = None
        elif needs_temp:
            check_type = wrapped_type
            sv_check = StackVar(wrapped_type, f"$sm_wrap${i}")
            sm_wrap_fields.append((sv_check.name, wrapped_type))
            sm_ops.append(dataclasses.replace(call_subst, register=sv_check))
            unwrap_op = Move(call_subst.register, StructField(sv_check, "value"))
        else:
            check_type = wrapped_type
            sv_check   = call_subst.register   # may be None for void calls
            sm_ops.append(call_subst)
            unwrap_op = None

        if sv_check is None:
            # Void call: nothing to test; resume falls through directly.
            sm_ops.append(Label(f"$resume${i}"))
        else:
            check = Invoke("UNLIKELY",
                           NewStruct((("x", __is_task_param(sv_check, check_type)),)),
                           Int(32))
            async_sm_label = f"$async_sm${i}"
            sm_ops.append(JumpIf(async_sm_label, check))
            if unwrap_op is not None:
                sm_ops.append(unwrap_op)
            sm_ops.append(Label(f"$resume${i}"))

            untagged = Invoke("TASK_UNTAG",
                              NewStruct((("p", __task_ptr_from(sv_check, check_type)),)),
                              DataPointer())
            cold_ops.append(Label(async_sm_label))
            cold_ops.extend(_emit_suspend_to_async(idx_field, i + 1, untagged, fn.name))

    # ── Terminal block ────────────────────────────────────────────────────────
    terminal_bb = basic_blocks[-1]
    terminal_ops = __convert_var_to_field_refs(terminal_bb.ops, vars_to_fields)

    # Replace the terminal Return with task-completion logic
    final_ops: list[Op] = []
    for op in terminal_ops:
        if isinstance(op, Return):
            # Write result into task, then complete
            if task_subtype_name is not None and not isinstance(fn.result, Void):
                final_ops.append(Move(
                    ObjectField(fn.result, my_task_field, task_subtype_name, "result", None),
                    op.value))
            final_ops.append(Move(
                __sv_discard,
                Invoke("task_complete", NewStruct((("self", my_task_field),)), DataPointer()),
                keep=True))
            final_ops.append(ReturnVoid())
        else:
            final_ops.append(op)
    sm_ops.extend(final_ops)

    # ── Dispatch targets for idx 1..N (at tail, after cold blocks). Case
    #    (i+1) handles completion of non_terminal[i]'s call: extract that
    #    call's result from the completed task, then jump to $resume$i.
    dispatch_ops: list[Op] = []
    for i in range(n):
        bb = non_terminal[i]
        dispatch_ops.append(Label(f"$case${i + 1}"))
        call_op = bb.ops[-1]
        if isinstance(call_op, ParallelCall):
            # Completed task is the par_task; assemble tuple from its result_k fields.
            pc = call_op
            par_task_name  = f"task$par${i}${fn.name}"
            par_result_types = [r.get_type() for r in pc.results]
            if pc.register is not None and pc.register.name in vars_to_fields:
                dispatch_ops.append(Move(
                    vars_to_fields[pc.register.name],
                    NewStruct(tuple(
                        (f"_{k}", ObjectField(par_result_types[k], __completed_param_var,
                                              par_task_name, f"result_{k}", None))
                        for k in range(len(par_result_types))))))
        elif bb.result is not None and isinstance(bb.result, StackVar):
            callee_task_name = __task_subtype_name(bb.result.get_type())
            extract = __extract_from_task(__completed_param_var, bb.result.get_type(),
                                           callee_task_name)
            dispatch_ops.append(Move(vars_to_fields[bb.result.name], extract))
        dispatch_ops.append(Jump(f"$resume${i}"))

    all_ops = tuple(sm_ops) + tuple(cold_ops) + tuple(dispatch_ops)

    extra_stack = Struct((("$sv_discard", DataPointer()),) + tuple(sm_wrap_fields))

    return Function(
        name=f"{fn.name}$async",
        params=Struct((("$state", DataPointer()), ("$completed_task", DataPointer()))),
        result=Void(),
        stack_vars=fn.stack_vars + extra_stack,
        ops=all_ops,
        comment=fn.comment,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Per-function conversion
# ─────────────────────────────────────────────────────────────────────────────

def __convert_function_to_task_convention(
        fn: Function) -> tuple[dict[str, Function], dict[str, Object]]:
    """
    If the function has no non-tail calls: just wrap its return type.
    Otherwise: produce the hot-path function (with the cold $asynccommon
    block) and, for non-sync functions, the state-machine function plus a
    state Object. Sync functions reuse the same hot path; their cold block
    aborts instead of creating a task.
    """
    # Skip __entrypoint__ – it bridges thread_start (old CPS) to the new world
    if fn.name == "__entrypoint__":
        return {fn.name: fn}, {}

    after_tail = __discover_tail_calls(fn)
    state_name = f"{fn.name}$state"
    basic_blocks = __create_basic_blocks(after_tail, state_name)

    # Functions with at most one block (no non-tail calls) need only
    # their return type adjusted (or kept as-is if it stays pointer-typed).
    if len(basic_blocks) < 2:
        wrapped = __wrap_return_type(fn.result)
        if isinstance(wrapped, TaskWrapper):
            # Promote Return(v) → Return(SyncWrap(v, wrapped)) and update any
            # musttail Call result_type so the C cast uses the wrapped typedef.
            new_ops = []
            for op in after_tail.ops:
                if isinstance(op, Return):
                    new_ops.append(Return(SyncWrap(op.value, wrapped)))
                elif isinstance(op, Call) and op.musttail:
                    new_ops.append(dataclasses.replace(op, result_type=wrapped))
                else:
                    new_ops.append(op)
            simple = dataclasses.replace(after_tail, result=wrapped, ops=tuple(new_ops))
        else:
            simple = dataclasses.replace(after_tail, result=wrapped)
        return {simple.name: simple}, {}

    task_subtype_name = __task_subtype_name(fn.result)

    hot_fn = __create_hot_path_func(after_tail, state_name,
                                     task_subtype_name, basic_blocks)

    # Scan for ParallelCall blocks; generate par_task structs, slot callbacks, and launcher callbacks.
    par_objects: dict[str, Object] = {}
    par_functions: dict[str, Function] = {}
    for i, bb in enumerate(basic_blocks[:-1]):
        call_op = bb.ops[-1]
        if isinstance(call_op, ParallelCall):
            pc = call_op
            par_task_nm = f"task$par${i}${fn.name}"
            res_types   = [r.get_type() for r in pc.results]
            par_objects[par_task_nm] = _par_task_object(par_task_nm, res_types)
            for k, rt in enumerate(res_types):
                # Slot callback (for when the lambda itself is async)
                cb = _slot_callback_function(fn.name, i, k, par_task_nm, rt)
                par_functions[cb.name] = cb
                # Launcher callback (runs on worker thread, calls the lambda)
                call_ref = pc.calls[k]
                lambda_name = call_ref.name if isinstance(call_ref, GlobalFunction) else f"__unknown_{k}__"
                launcher = _launcher_callback_function(fn.name, i, k, par_task_nm, lambda_name, rt)
                par_functions[launcher.name] = launcher

    if fn.sync:
        # Sync function: $asynccommon aborts; no state machine, no state object.
        return {hot_fn.name: hot_fn} | par_functions, par_objects

    state_obj  = __create_state_object(after_tail, state_name, basic_blocks)
    machine_fn = __create_state_machine_func(after_tail, state_name,
                                              task_subtype_name, basic_blocks)
    functions = {hot_fn.name: hot_fn, machine_fn.name: machine_fn} | par_functions
    objects   = {state_obj.name: state_obj} | par_objects
    return functions, objects


# ─────────────────────────────────────────────────────────────────────────────
# Task-subtype Object generation (collected across all functions)
# ─────────────────────────────────────────────────────────────────────────────

# Mirror of task_t in yafllib/yafl.h.  Subtypes inherit these fields the
# normal YAFL way (flat-layout), so ((task_t*)subtype) hits each prefix
# field at the same offset by construction — no per-callsite cast machinery
# needed. Order MUST match the C declaration of task_t exactly.
_TASK_FIELDS: tuple[tuple[str, Type], ...] = (
    ("type",       DataPointer()),   # object_t.vtable (vtable_t*)
    ("state",      Int(32)),         # _Atomic(int_fast32_t)
    ("thread_id",  Int(32)),         # originating worker thread index
    ("callback",   FuncPointer()),   # fun_t
    ("next",       DataPointer()),   # _Atomic(task_t*) — intrusive queue link
)


def _task_object() -> Object:
    """Foreign 'task' Object — its typedef lives in yafl.h; we publish the
    field list so subtypes can extend it via normal YAFL inheritance and
    ObjectField accesses to inherited fields resolve at the correct offsets.
    """
    return Object(
        name="task",
        extends=(),
        functions=(),
        fields=ImmediateStruct(_TASK_FIELDS),
        comment="foreign task_t — declared in yafllib/yafl.h",
        is_foreign=True,
    )


def _task_subtype_object(subtype_name: str, result_type: Type) -> Object:
    # "task_obj" is pre-declared in yafllib (yafl.h + task.c: TASK_OBJ_VTABLE
    # aliased as obj_task_obj). Mark it foreign so codegen doesn't emit a
    # duplicate typedef/vtable; NewObject/ObjectField still reference the
    # yafllib symbols by name.  Compiler-synthesised subtypes get a flat
    # struct emitted by codegen with the task_t prefix followed by `result`.
    is_foreign = subtype_name == "task_obj"
    fields = _TASK_FIELDS + (("result", result_type),)
    return Object(
        name=subtype_name,
        extends=("task",),
        functions=(),
        fields=ImmediateStruct(fields),
        comment=f"task subtype for result type {result_type}",
        is_foreign=is_foreign,
    )


def _par_task_object(par_task_name: str, result_types: list[Type]) -> Object:
    """Generate the par_task struct for a parallel call site.

    Inherits task_t's prefix fields (so `(task_t*)par_task` and
    `(task_par_base_t*)par_task` both work), then appends per-instance
    fields: `remaining`, per-slot closure pointers, and per-slot results."""
    N = len(result_types)
    fields = _TASK_FIELDS + (
        ("remaining", Int(32)),
    ) + tuple((f"closure_{k}", DataPointer()) for k in range(N)) \
      + tuple((f"result_{k}", rt) for k, rt in enumerate(result_types))
    return Object(
        name=par_task_name,
        extends=("task",),
        functions=(),
        fields=ImmediateStruct(fields),
        comment=f"parallel join task with {N} slots",
        is_foreign=False,
    )


def _slot_callback_function(fn_name: str, call_site: int, slot: int,
                              par_task_name: str, result_type: Type) -> Function:
    """Generate the callback invoked when slot K's sub-task completes.

    Writes the sub-task result into par_task->result_K then calls
    task_par_decrement(par_task) which fires task_complete when all slots done.
    """
    sv_par      = StackVar(DataPointer(), "$par_task")
    sv_sub      = StackVar(DataPointer(), "$completed_sub_task")
    sv_discard_ = StackVar(DataPointer(), "$sv_discard_cb")

    sub_task_name = __task_subtype_name(result_type)
    ops_cb: list[Op] = []

    if not isinstance(result_type, Void) and sub_task_name is not None:
        ops_cb.append(Move(
            ObjectField(result_type, sv_par, par_task_name, f"result_{slot}", None),
            __extract_from_task(sv_sub, result_type, sub_task_name)))

    ops_cb.append(Move(
        sv_discard_,
        Invoke("task_par_decrement", NewStruct((("par_task", sv_par),)), DataPointer()),
        keep=True))
    ops_cb.append(Return(NullPointer()))

    return Function(
        name=f"{fn_name}$par${call_site}$slot${slot}",
        params=Struct((("$par_task", DataPointer()), ("$completed_sub_task", DataPointer()))),
        result=DataPointer(),
        stack_vars=Struct((("$sv_discard_cb", DataPointer()),)),
        ops=tuple(ops_cb),
    )


def _launcher_callback_function(fn_name: str, call_site: int, slot: int,
                                 par_task_name: str, lambda_name: str,
                                 result_type: Type) -> Function:
    """Callback posted to a worker thread to invoke slot K's lambda.

    Reads par_task->closure_K, calls lambda_name(closure), then:
      - sync result: writes to result_K, calls task_par_decrement
      - async result: registers slot_K callback on the returned task
    """
    sv_par       = StackVar(DataPointer(), "$par_task")
    sv_closure   = StackVar(DataPointer(), "$launcher_closure")
    wrapped_type = __wrap_return_type(result_type)
    needs_temp   = wrapped_type is not result_type
    sv_result_w  = StackVar(wrapped_type, "$result_w")
    sv_discard_  = StackVar(DataPointer(), "$sv_discard_cb")

    closure_field = ObjectField(DataPointer(), sv_par, par_task_name, f"closure_{slot}", None)

    ops: list[Op] = []
    # Read closure from par_task
    ops.append(Move(sv_closure, closure_field))
    # Call the lambda
    ops.append(Call(GlobalFunction(lambda_name, sv_closure), NewStruct(()), sv_result_w))
    # IS_TASK check
    cond = Invoke("UNLIKELY",
                  NewStruct((("x", __is_task_param(sv_result_w, wrapped_type)),)),
                  Int(32))
    ops.append(JumpIf("$launcher_async", cond))
    # Sync path: write result, decrement
    unwrapped = StructField(sv_result_w, "value") if needs_temp else sv_result_w
    ops.append(Move(
        ObjectField(result_type, sv_par, par_task_name, f"result_{slot}", None),
        unwrapped))
    ops.append(Move(sv_discard_,
                    Invoke("task_par_decrement",
                           NewStruct((("par_task", sv_par),)), DataPointer()),
                    keep=True))
    ops.append(Jump("$launcher_done"))
    # Async path: register slot callback
    ops.append(Label("$launcher_async"))
    task_ptr_k = __task_ptr_from(sv_result_w, wrapped_type)
    untag_k    = Invoke("TASK_UNTAG", NewStruct((("p", task_ptr_k),)), DataPointer())
    slot_cb    = GlobalFunction(f"{fn_name}$par${call_site}$slot${slot}", sv_par)
    ops.append(Move(sv_discard_,
                    Invoke("task_on_complete",
                           NewStruct((("task", untag_k), ("cb", slot_cb))),
                           DataPointer()),
                    keep=True))
    ops.append(Label("$launcher_done"))
    ops.append(Return(NullPointer()))

    stack_vars_fields = [("$launcher_closure", DataPointer()), ("$result_w", wrapped_type), ("$sv_discard_cb", DataPointer())]
    return Function(
        name=f"{fn_name}$par${call_site}$launcher${slot}",
        params=Struct((("$par_task", DataPointer()), ("$launched_task", DataPointer()))),
        result=DataPointer(),
        stack_vars=Struct(tuple(stack_vars_fields)),
        ops=tuple(ops),
    )


def collect_task_subtypes(app: Application) -> dict[str, Object]:
    """
    Scan all functions and collect the unique task-subtype objects that need
    to be generated (one per distinct non-Void codegen-level return type).

    Registers the foreign 'task' Object so that the trim pass and codegen can
    resolve the extends=("task",) reference on every generated subtype.
    """
    seen: dict[str, Type] = {}
    for fn in app.functions.values():
        if isinstance(fn.result, Void):
            continue
        name = __task_subtype_name(fn.result)
        if name and name not in seen:
            # Use the actual inner type for TaskWrapper; the raw type otherwise
            inner = fn.result.inner if isinstance(fn.result, TaskWrapper) else fn.result
            seen[name] = inner

    objs: dict[str, Object] = {name: _task_subtype_object(name, t)
                               for name, t in seen.items()}
    objs["task"] = _task_object()
    return objs


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def lower_async(app: Application) -> Application:
    results = [__convert_function_to_task_convention(fn)
               for fn in app.functions.values()]

    new_functions = reduce(lambda acc, v: acc | v[0], results, {})
    new_objects   = reduce(lambda acc, v: acc | v[1], results, {}) | app.objects

    # Add task-subtype objects (after conversion so return types are finalised)
    tmp_app = dataclasses.replace(app, functions=new_functions, objects=new_objects)
    task_subtypes = collect_task_subtypes(tmp_app)

    return dataclasses.replace(tmp_app,
                               objects=task_subtypes | tmp_app.objects)
