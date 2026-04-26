from __future__ import annotations

# Convert each function that has non-tail calls into two C functions:
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
from codegen.ops import Op, Call, Return, ReturnVoid, Move, Label, JumpIf, IfTask, Jump, NewObject, SwitchJump
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

# Internal scratch variables used in hot-path cold blocks / common block
__sv_state      = StackVar(DataPointer(), "$sv_state")
__sv_task       = StackVar(DataPointer(), "$sv_task")
__sv_discard    = StackVar(DataPointer(), "$sv_discard")
__sv_call_id    = StackVar(Int(32),       "$sv_call_id")    # call-site index for asynccommon
__sv_async_task = StackVar(DataPointer(), "$sv_async_task") # TASK_UNTAG'd task ptr for asynccommon


# ─────────────────────────────────────────────────────────────────────────────
# Tail-call detection (unchanged from old CPS pass)
# ─────────────────────────────────────────────────────────────────────────────

def __discover_tail_calls(fn: Function) -> Function:
    # In the direct-return calling convention every call site needs an
    # IS_TASK check regardless of position, so tail-call collapsing is not
    # used.  The C compiler handles tail-call optimisation where possible.
    return fn


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
    # Match by name: match-arm rebinding can produce StackVars that share a
    # name but differ in IR type (e.g., _IO|Int pointer-union reinterpreted
    # as Int(0) bigint). They map to the same C variable and the same state
    # field, so substitution must key on name only.
    def replacer(p: RParam) -> RParam:
        if isinstance(p, StackVar) and p.name in vars_to_fields:
            return vars_to_fields[p.name]
        return p
    return tuple(op.replace_params(replacer) for op in ops)


def __create_basic_blocks(fn: Function, state_name: str) -> list[BasicBlock]:
    liveness_fn = __calculate_saved_vars(fn)
    partitions = langtools.partition(liveness_fn.ops,
                                     lambda op: isinstance(op, Call) and not op.musttail and not op.sync)

    def make_block(index: int, ops: list[Op]) -> BasicBlock:
        name = f"cont${index}"
        last_op = ops[-1]
        result = last_op.register if isinstance(last_op, Call) else None
        # Append a resume label right after the call (same as old CPS model)
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
        call_op = bb.ops[-1]   # Call is last
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
        terminal_ops = [
            Return(SyncWrap(op.value, wrapped_result)) if isinstance(op, Return) else op
            for op in terminal_ops
        ]
    hot_ops.extend(terminal_ops)

    # ── Shared $asynccommon block ─────────────────────────────────────────────
    # Allocates state, saves all live vars, creates the task, registers the
    # callback, and returns the tagged task pointer.
    common_ops: list[Op] = [Label("$asynccommon")]

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

    # Create the task subtype (or base task_t for Void-returning functions)
    if task_subtype_name is None:
        common_ops.append(Move(
            __sv_task,
            Invoke("task_create", NewStruct((("self", NullPointer()),)), DataPointer())))
    else:
        common_ops.append(NewObject(task_subtype_name, __sv_task))
        # TODO: atomic_store(&task->state, TASK_PENDING) once yafllib
        # provides task_init().  Zero-fill from allocator is correct for now.
        if not isinstance(fn.result, Void):
            common_ops.append(Move(
                ObjectField(fn.result, __sv_task, task_subtype_name, "result", None),
                __zero_val(fn.result)))

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
               DataPointer())))
    common_ops.append(Return(TagTask(__sv_task, wrapped_result)))

    extra_stack = Struct((
        ("$sv_state",      DataPointer()),
        ("$sv_task",       DataPointer()),
        ("$sv_discard",    DataPointer()),
        ("$sv_call_id",    Int(32)),
        ("$sv_async_task", DataPointer()),
    ) + tuple(wrap_fields))
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

        result_type     = call_op_orig.register.get_type() if call_op_orig.register else None
        discarded_type  = None if result_type is not None else call_op_orig.result_type
        wrapped_type    = __wrap_return_type(result_type)  if result_type else None
        needs_temp      = result_type is not None and (wrapped_type is not result_type)

        substituted_before = __convert_var_to_field_refs(body_ops_before_call, vars_to_fields)
        sm_ops.extend(substituted_before)

        call_subst = call_op_orig.replace_params(
            lambda p: vars_to_fields[p.name] if isinstance(p, StackVar) and p.name in vars_to_fields else p)

        # The `$resume${i}` label marks the point both the sync fall-through
        # *after* the IS_TASK check+unpack and the dispatch path (from
        # `$case${i+1}`) converge.  The check+unpack reads the local wrap
        # slot written by the Call op just above; the dispatch path reaches
        # `$resume${i}` without having run that Call, so the check+unpack
        # must sit *before* the label — on the sync edge only — and never be
        # re-entered on resume.  Dispatch writes the extracted result into
        # the state field and lands at the label with the check already
        # satisfied.

        if discarded_type is not None:
            # Non-void call whose result was stripped by dead-store elimination.
            # Still need to check for async and use the correct C cast (sret ABI).
            discarded_wrapped = __wrap_return_type(discarded_type)
            sv_discard_wrap = StackVar(discarded_wrapped, f"$sm_wrap${i}")
            sm_wrap_fields.append((f"$sm_wrap${i}", discarded_wrapped))
            sm_ops.append(dataclasses.replace(call_subst, register=sv_discard_wrap))
            task_ptr = __task_ptr_from(sv_discard_wrap, discarded_wrapped)
            check = Invoke("UNLIKELY",
                           NewStruct((("x", __is_task_param(sv_discard_wrap, discarded_wrapped)),)),
                           Int(32))
            async_sm_label = f"$async_sm${i}"
            sm_ops.append(JumpIf(async_sm_label, check))
            sm_ops.append(Label(f"$resume${i}"))
            cold_ops.append(Label(async_sm_label))
            cold_ops.append(Move(idx_field, Integer(i + 1, 32)))
            untag    = Invoke("TASK_UNTAG", NewStruct((("p", task_ptr),)), DataPointer())
            callback = GlobalFunction(f"{fn.name}$async", __state_param_var)
            cold_ops.append(Move(
                __sv_discard,
                Invoke("task_on_complete",
                       NewStruct((("task", untag), ("cb", callback))),
                       DataPointer())))
            cold_ops.append(ReturnVoid())
        elif needs_temp:
            sv_wrapped = StackVar(wrapped_type, f"$sm_wrap${i}")
            sm_wrap_fields.append((f"$sm_wrap${i}", wrapped_type))
            call_with_wrap = dataclasses.replace(call_subst, register=sv_wrapped)
            sm_ops.append(call_with_wrap)
            sv_for_check    = sv_wrapped
            orig_state_field = call_subst.register

            check = Invoke("UNLIKELY",
                           NewStruct((("x", __is_task_param(sv_for_check, wrapped_type)),)),
                           Int(32))
            async_sm_label = f"$async_sm${i}"
            sm_ops.append(JumpIf(async_sm_label, check))

            sm_ops.append(Move(orig_state_field, StructField(sv_wrapped, "value")))
            sm_ops.append(Label(f"$resume${i}"))

            cold_ops.append(Label(async_sm_label))
            cold_ops.append(Move(idx_field, Integer(i + 1, 32)))   # 1-based
            task_ptr = __task_ptr_from(sv_for_check, wrapped_type)
            untag    = Invoke("TASK_UNTAG", NewStruct((("p", task_ptr),)), DataPointer())
            callback = GlobalFunction(f"{fn.name}$async", __state_param_var)
            cold_ops.append(Move(
                __sv_discard,
                Invoke("task_on_complete",
                       NewStruct((("task", untag), ("cb", callback))),
                       DataPointer())))
            cold_ops.append(ReturnVoid())
        else:
            sm_ops.append(call_subst)
            sv_for_check     = call_subst.register
            orig_state_field = None

            if sv_for_check is not None:
                check = Invoke("UNLIKELY",
                               NewStruct((("x", __is_task_param(sv_for_check, wrapped_type)),)),
                               Int(32))
                async_sm_label = f"$async_sm${i}"
                sm_ops.append(JumpIf(async_sm_label, check))

                cold_ops.append(Label(async_sm_label))
                cold_ops.append(Move(idx_field, Integer(i + 1, 32)))   # 1-based
                task_ptr = __task_ptr_from(sv_for_check, wrapped_type)
                untag    = Invoke("TASK_UNTAG", NewStruct((("p", task_ptr),)), DataPointer())
                callback = GlobalFunction(f"{fn.name}$async", __state_param_var)
                cold_ops.append(Move(
                    __sv_discard,
                    Invoke("task_on_complete",
                           NewStruct((("task", untag), ("cb", callback))),
                           DataPointer())))
                cold_ops.append(ReturnVoid())

            sm_ops.append(Label(f"$resume${i}"))

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
                Invoke("task_complete", NewStruct((("self", my_task_field),)), DataPointer())))
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
        if bb.result is not None and isinstance(bb.result, StackVar):
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
    Otherwise: produce the hot-path function + the state-machine function,
    plus a state Object.
    """
    # Skip __entrypoint__ – it bridges thread_start (old CPS) to the new world
    if fn.name == "__entrypoint__":
        return {fn.name: fn}, {}

    # Sync functions never suspend, so they need no state machine — but they
    # can still be invoked through a fun_t that expects the wrapped return
    # convention (e.g. a lambda passed to a generic `?>`). Wrap the return
    # type so the calling convention matches, and skip body CPS conversion.
    if fn.sync:
        wrapped = __wrap_return_type(fn.result)
        if isinstance(wrapped, TaskWrapper):
            new_ops = tuple(
                Return(SyncWrap(op.value, wrapped)) if isinstance(op, Return) else op
                for op in fn.ops
            )
            simple = dataclasses.replace(fn, result=wrapped, ops=new_ops)
            return {simple.name: simple}, {}
        return {fn.name: fn}, {}

    after_tail = __discover_tail_calls(fn)
    state_name = f"{fn.name}$state"
    basic_blocks = __create_basic_blocks(after_tail, state_name)

    # Functions with at most one block (no non-tail calls) need only
    # their return type adjusted (or kept as-is if it stays pointer-typed).
    if len(basic_blocks) < 2:
        wrapped = __wrap_return_type(fn.result)
        if isinstance(wrapped, TaskWrapper):
            # Promote Return(v) → Return(SyncWrap(v, wrapped)) so the function
            # emits the correct TaskWrapper struct with .task=NULL.
            new_ops = tuple(
                Return(SyncWrap(op.value, wrapped)) if isinstance(op, Return) else op
                for op in after_tail.ops
            )
            simple = dataclasses.replace(after_tail, result=wrapped, ops=new_ops)
        else:
            simple = dataclasses.replace(after_tail, result=wrapped)
        return {simple.name: simple}, {}

    task_subtype_name = __task_subtype_name(fn.result)

    state_obj   = __create_state_object(after_tail, state_name, basic_blocks)
    hot_fn      = __create_hot_path_func(after_tail, state_name,
                                          task_subtype_name, basic_blocks)
    machine_fn  = __create_state_machine_func(after_tail, state_name,
                                               task_subtype_name, basic_blocks)

    functions = {hot_fn.name: hot_fn, machine_fn.name: machine_fn}
    objects   = {state_obj.name: state_obj}
    return functions, objects


# ─────────────────────────────────────────────────────────────────────────────
# Task-subtype Object generation (collected across all functions)
# ─────────────────────────────────────────────────────────────────────────────

# Fields common to all task subtypes (mirror task_t layout so casting works):
#   type     – vtable pointer (= object_t.type)
#   state    – _Atomic(int_fast32_t)  [treated as Int(32) in the IR]
#   callback – fun_t
#   result   – T  (the actual return value)
#
# The compiler-generated typedef embeds task_t directly as its first field
# so casts between task_t* and task_T_t* are valid C.

def _task_subtype_object(subtype_name: str, result_type: Type) -> Object:
    fields: tuple[tuple[str, Type], ...] = (
        ("type",     DataPointer()),   # vtable
        ("state",    Int(32)),         # _Atomic int – treated as Int(32) here
        ("callback", FuncPointer()),   # fun_t
        ("result",   result_type),
    )
    # "task_obj" is pre-declared in yafllib (yafl.h + task.c: TASK_OBJ_VTABLE
    # aliased as obj_task_obj). Mark it foreign so codegen doesn't emit a
    # duplicate typedef/vtable; NewObject/ObjectField still reference the
    # yafllib symbols by name.
    is_foreign = subtype_name == "task_obj"
    return Object(
        name=subtype_name,
        extends=(),        # task_complete/task_on_complete cast directly; no vtable dispatch needed
        functions=(),
        fields=ImmediateStruct(fields),
        comment=f"task subtype for result type {result_type}",
        is_foreign=is_foreign,
    )


def collect_task_subtypes(app: Application) -> dict[str, Object]:
    """
    Scan all functions and collect the unique task-subtype objects that need
    to be generated (one per distinct non-Void codegen-level return type).

    Also registers a foreign 'task' Object so that the trim pass can resolve
    the extends=("task",) reference on every generated subtype.
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

    return {name: _task_subtype_object(name, t) for name, t in seen.items()}


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point (same name, same signature – compiler.py import unchanged)
# ─────────────────────────────────────────────────────────────────────────────

def convert_application_to_cps(app: Application) -> Application:
    results = [__convert_function_to_task_convention(fn)
               for fn in app.functions.values()]

    new_functions = reduce(lambda acc, v: acc | v[0], results, {})
    new_objects   = reduce(lambda acc, v: acc | v[1], results, {}) | app.objects

    # Add task-subtype objects (after conversion so return types are finalised)
    tmp_app = dataclasses.replace(app, functions=new_functions, objects=new_objects)
    task_subtypes = collect_task_subtypes(tmp_app)

    return dataclasses.replace(tmp_app,
                               objects=task_subtypes | tmp_app.objects)
