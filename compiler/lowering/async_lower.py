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
from lowering.task_abi import (
    TASK_FIELDS, wrap_return_type, is_task_param, task_ptr_from,
    task_subtype_name, make_task_foreign_object, make_task_subtype_object,
)
from codegen.gen import Application
from codegen.ops import Op, Call, Return, ReturnVoid, Move, Label, JumpIf, IfTask, Jump, NewObject, SwitchJump, Abort, ParallelCall, Phi
from codegen.things import Function, Object
from codegen.typedecl import (
    FuncPointer, Void, Struct, ImmediateStruct, DataPointer, Int, Type, Array,
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
# Return conversion helpers
#
# A Return / ReturnVoid op semantically means "the function exits here with
# this value." It can appear at the end of the function (the natural place)
# OR anywhere else in the op stream — early exits introduced by branch
# threading, by future optimisations, or by source-level early-return syntax
# once that exists. Both the hot-path and state-machine emitters must handle
# Returns uniformly wherever they appear, otherwise a mid-function Return
# leaks through as a `return value;` inside a function that's been declared
# void (state machine) or whose return type has been wrapped (hot path).
# ─────────────────────────────────────────────────────────────────────────────


def __convert_returns_for_state_machine(
        ops: Iterable[Op],
        my_task_field: RParam,
        fn_result: Type,
        task_subtype_name: str | None) -> list[Op]:
    """Convert each Return / ReturnVoid in `ops` to `task_complete` + ReturnVoid.

    For non-void Returns: also store the value into the task's result field.
    Non-Return ops pass through unchanged.
    """
    out: list[Op] = []
    for op in ops:
        if isinstance(op, Return):
            if task_subtype_name is not None and not isinstance(fn_result, Void):
                out.append(Move(
                    ObjectField(fn_result, my_task_field, task_subtype_name, "result", None),
                    op.value))
            out.append(Move(
                __sv_discard,
                Invoke("task_complete", NewStruct((("self", my_task_field),)), DataPointer()),
                keep=True))
            out.append(ReturnVoid())
        elif isinstance(op, ReturnVoid):
            out.append(Move(
                __sv_discard,
                Invoke("task_complete", NewStruct((("self", my_task_field),)), DataPointer()),
                keep=True))
            out.append(ReturnVoid())
        else:
            out.append(op)
    return out


def __convert_returns_for_hot_path(
        ops: Iterable[Op],
        wrapped_result: Type) -> list[Op]:
    """Wrap each Return's value in SyncWrap if the function's return type
    was wrapped in a TaskWrapper (pure-primitive returns), and bring each
    musttail Call's result_type into line with the function's wrapped result
    so the emitted C cast `((wrapped_t(*)(…))callee)(…)` agrees with the
    surrounding `return` statement's type.

    Both adjustments are no-ops when the return type isn't TaskWrapper-
    wrapped (pointer-typed returns pass through unchanged).
    """
    if not isinstance(wrapped_result, TaskWrapper):
        return list(ops)
    out: list[Op] = []
    for op in ops:
        if isinstance(op, Return):
            # Skip if the Return value is already shaped like the wrapped
            # type (e.g. a TagTask constructing the async-pending form).
            # Lets passes that hand-build wrapped-shape returns interoperate
            # with the hot-path SyncWrap convention.
            if op.value.get_type() == wrapped_result:
                out.append(op)
            else:
                out.append(Return(SyncWrap(op.value, wrapped_result)))
        elif isinstance(op, Call) and op.musttail:
            out.append(dataclasses.replace(op, result_type=wrapped_result))
        else:
            out.append(op)
    return out


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
# Tail-call detection (unchanged from the old Task pass)
# ─────────────────────────────────────────────────────────────────────────────

def __discover_tail_calls(fn: Function) -> Function:
    """Mark Calls in literal tail position as `musttail`.

    A Call qualifies when it is immediately followed by a Return whose value
    is the Call's result register, AND the Call's result type matches
    fn.result. The match is on the *unwrapped* type (this pass runs before
    wrap_return_type is applied) — once both sides go through the same
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

    Applies to both sync and async functions. Sync functions don't generate
    a state machine, so the removed Return + musttail Call is safe everywhere
    downstream. Async functions get the musttail preserved on the hot path
    (clang TCOs `return foo(...)`); the state machine separately re-expands
    musttail back to Call+Return via `__unroll_musttail_for_state_machine`
    so its terminal-Return → task_complete sequence still fires.
    """
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
    ops0 = fn.ops
    n = len(ops0)
    labels = {op.name: index for index, op in enumerate(ops0) if isinstance(op, Label)}

    # Enclosing block label for each op (nearest preceding Label), so a Phi
    # source can be attributed to the specific predecessor edge it arrives on.
    block_label: list[str | None] = [None] * n
    cur: str | None = None
    for i, op in enumerate(ops0):
        if isinstance(op, Label):
            cur = op.name
        block_label[i] = cur

    def reads_writes(op: Op) -> tuple[frozenset[StackVar], frozenset[StackVar]]:
        # A Phi reads nothing *unconditionally* — each source is consumed only
        # on the edge from its labelled predecessor (added per-edge in
        # `edge_in`). Treating Phi sources as plain reads would make a loop
        # head's entry-edge value (e.g. an incoming param) appear live on the
        # back-edge too, forcing it to be saved across a suspension where it no
        # longer exists. The Phi writes its target.
        if isinstance(op, Phi):
            w = frozenset({op.target}) if isinstance(op.target, StackVar) else frozenset()
            return frozenset(), w
        return op.get_live_vars()

    def do_a_pass(ops: tuple[Op, ...]) -> tuple[Op, ...]:
        def saved_set_at(index: int) -> frozenset[StackVar]:
            reads, _ = reads_writes(ops[index])
            return reads | ops[index].saved_vars

        def phi_sources_into(target_index: int, pred: str | None) -> frozenset[StackVar]:
            srcs: frozenset[StackVar] = frozenset()
            j = target_index + 1
            while j < n and isinstance(ops[j], Phi):
                for lbl, v in ops[j].sources:
                    if lbl == pred:
                        srcs = srcs | v.get_live_vars()
                j += 1
            return srcs

        def edge_in(from_index: int, target_index: int) -> frozenset[StackVar]:
            return saved_set_at(target_index) | phi_sources_into(target_index, block_label[from_index])

        def calc(index: int) -> Op:
            op = ops[index]
            if index >= n - 1:
                ss1 = frozenset()
            elif isinstance(op, Jump):
                ss1 = edge_in(index, labels[op.name]) if op.name in labels else frozenset()
            else:
                ss1 = edge_in(index, index + 1)
            ss2 = (edge_in(index, labels[op.label])
                   if isinstance(op, JumpIf) and op.label in labels else frozenset())
            _, this_writes = reads_writes(op)
            saved_vars = (ss1 | ss2) - this_writes
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


# ── Heap-frame layout ─────────────────────────────────────────────────────────
# A heap state frame keeps every local that is *strictly* an object pointer
# (`object_t*`, i.e. a bare DataPointer root variable) in a trailing `object_t*`
# array, scanned by the GC via the array machinery — so the count is unbounded.
# Every other frame local (primitives, and compound types like `fun_t` or
# unboxed unions/tuples whose pointers are *members*) becomes an inline field.
#
# To keep the inline pointer count — and so the 64-bit `object_pointer_locations`
# mask — small, inline locals SHARE storage: two locals of the same type whose
# live ranges never overlap occupy one slot (a plain shared field; identical type
# means no C union is needed). A standard interference graph (built from the
# liveness already computed for the state machine, plus the hot-path save sets)
# drives a greedy colouring; each colour is one slot. The save step writes only
# the locals live at each suspension (see __create_hot_path_func), so a shared
# slot only ever receives its one live occupant.

@dataclass(frozen=True)
class FrameLayout:
    ptr_slots:    dict[str, int]                  # strict object_t* local → array index
    inline_slots: dict[str, str]                  # other frame local → shared field name
    slot_fields:  tuple[tuple[str, Type], ...]    # the distinct inline slot fields
    n_array:      int                             # trailing array length


def __frame_field_types(basic_blocks: list[BasicBlock]) -> dict[str, Type]:
    """Collect every frame-resident local (saved live vars + call-result
    registers), name → type, in first-seen order (type is last-seen, matching
    the historical state-object collection)."""
    fields: dict[str, Type] = {}
    for bb in basic_blocks[:-1]:
        # bb.live is a frozenset; iterate it in a fixed order (SSA names are
        # unique, so name order is total) or the field-collection order — and
        # everything downstream that numbers slots and anonymous structs from
        # it — becomes hash-seed dependent, making codegen non-reproducible.
        for var in sorted(bb.live, key=lambda v: v.name):
            fields[var.name] = var.get_type()
        if bb.result is not None and isinstance(bb.result, StackVar):
            fields[bb.result.name] = bb.result.get_type()
    return fields


def __op_writes(op: Op) -> frozenset[StackVar]:
    # Mirror __calculate_saved_vars' Phi handling: a Phi defines its target only.
    if isinstance(op, Phi):
        return frozenset({op.target}) if isinstance(op.target, StackVar) else frozenset()
    return op.get_live_vars()[1]


def __op_reads(op: Op) -> frozenset[StackVar]:
    # Mirror __calculate_saved_vars' Phi handling: a Phi reads nothing
    # unconditionally (each source is consumed only on its predecessor edge).
    if isinstance(op, Phi):
        return frozenset()
    return op.get_live_vars()[0]


def __build_interference(op_sequences: list[tuple[Op, ...]],
                         frame_names: frozenset[str]) -> dict[str, set[str]]:
    """Two frame locals interfere if they are ever simultaneously live, computed
    over EVERY given op sequence (both the state-machine view and the hot-path
    view — a value can live differently in each, and the shared slot layout must
    be safe for both).

    Each op carries its `saved_vars` (live-out) from __calculate_saved_vars. A
    pair is simultaneously live when:
      * both are in the same live-out set; or
      * one is defined while the other is live-out (def vs live-out); or
      * both are live *into* the same op — its operands (reads) plus any survivor
        not (re)defined there. This catches operands that both die at the op —
        e.g. the two arguments of `concat(left, right)` — which never share a
        live-out set yet are simultaneously live.
    A value read at an op does NOT interfere with the value the op defines: the
    reads are consumed before the result is written (`slot = f(slot)` is safe),
    which is exactly what makes `x = f(x)` coalescing sound.
    """
    graph: dict[str, set[str]] = {n: set() for n in frame_names}

    def link(a: str, b: str) -> None:
        if a != b and a in graph and b in graph:
            graph[a].add(b)
            graph[b].add(a)

    def link_all_pairs(names: list[str]) -> None:
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                link(names[i], names[j])

    for ops in op_sequences:
        for op in ops:
            live_out = [v.name for v in op.saved_vars if v.name in graph]
            writes = {w.name for w in __op_writes(op)}
            link_all_pairs(live_out)
            for w in writes:
                if w in graph:
                    for n in live_out:
                        link(w, n)
            live_in = [v.name for v in __op_reads(op) if v.name in graph]
            live_in += [n for n in live_out if n not in writes]
            link_all_pairs(live_in)
    return graph


def __colour(names: list[str], graph: dict[str, set[str]]) -> dict[str, int]:
    """Greedy interference colouring: non-overlapping same-typed frame locals
    share a slot, shrinking the heap state frame (and its GC-scanned pointer
    array)."""
    colour: dict[str, int] = {}
    for name in names:
        used = {colour[n] for n in graph.get(name, ()) if n in colour}
        c = 0
        while c in used:
            c += 1
        colour[name] = c
    return colour


def __compute_frame_layout(sm_basic_blocks: list[BasicBlock],
                           hot_basic_blocks: list[BasicBlock],
                           liveness_ops: tuple[Op, ...]) -> FrameLayout:
    field_types = __frame_field_types(sm_basic_blocks)
    frame_names = frozenset(field_types)

    # Build interference over BOTH the state-machine view (authoritative layout)
    # and the hot-path view (the ops actually executed when no suspension occurs):
    # a coalesced slot must be safe under both. The hot blocks' ops carry their
    # own `saved_vars`, so per-op live-in/out interference covers the hot path
    # too — including operands that both die at one op (e.g. `concat(left,right)`)
    # which a per-suspension save set alone would miss.
    hot_ops = tuple(op for bb in hot_basic_blocks for op in bb.ops)
    graph = __build_interference([liveness_ops, hot_ops], frame_names)

    # Coalesce FIRST, over every frame local: group by exact type and greedily
    # colour each type-class against the interference graph, so non-overlapping
    # same-typed locals share one slot. THEN route slots by type — a slot whose
    # type is strictly object_t* goes to the GC-scanned trailing array (so even
    # the pointer roots are coalesced, shrinking the array to the peak live
    # count); every other slot is an inline field.
    by_type: dict[Type, list[str]] = {}
    for name, typ in field_types.items():
        by_type.setdefault(typ, []).append(name)

    ptr_slots: dict[str, int] = {}
    inline_slots: dict[str, str] = {}
    slot_fields: list[tuple[str, Type]] = []
    n_array = 0
    for type_index, (typ, names) in enumerate(by_type.items()):
        colour = __colour(names, graph)
        if isinstance(typ, DataPointer):
            base = n_array
            for name in names:
                ptr_slots[name] = base + colour[name]
            n_array += len(set(colour.values()))
        else:
            for c in sorted(set(colour.values())):
                slot_fields.append((f"$slot${type_index}${c}", typ))
            for name in names:
                inline_slots[name] = f"$slot${type_index}${colour[name]}"

    return FrameLayout(ptr_slots, inline_slots, tuple(slot_fields), n_array)


def __state_field(name: str, typ: Type, state_param: RParam,
                  state_name: str, layout: FrameLayout) -> ObjectField:
    """Reference to a frame local: a slot in the trailing pointer array when the
    local is strictly `object_t*`, its shared inline slot when it is a coalesced
    inline local, otherwise a plain named field."""
    if name in layout.ptr_slots:
        return ObjectField(DataPointer(), state_param, state_name, "array",
                           Integer(layout.ptr_slots[name], 32))
    if name in layout.inline_slots:
        return ObjectField(typ, state_param, state_name, layout.inline_slots[name], None)
    return ObjectField(typ, state_param, state_name, name, None)


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


def __unroll_musttail_for_state_machine(fn: Function) -> Function:
    """Re-expand `Call(musttail=True)` back into `Call(register=tmp) + Return(tmp)`
    (or `Call + ReturnVoid` for void calls) so the state-machine code generation
    can drive task_complete via its existing terminal-Return handling.

    The hot path keeps the original musttail Call so its C codegen emits
    `return foo(...)` and clang TCOs it. Only the state-machine path needs
    the re-expansion: after a suspension+resume, control re-enters via the
    dispatch — there is no tail position from C's perspective — so the call
    must be a regular non-tail call whose result feeds task_complete.

    The fresh temp becomes a basic-block result and ends up as a state-object
    field via the existing `__create_state_object` machinery.
    """
    new_ops: list[Op] = []
    counter = 0
    for op in fn.ops:
        if isinstance(op, Call) and op.musttail:
            counter += 1
            if op.result_type is None or isinstance(op.result_type, Void):
                new_ops.append(dataclasses.replace(op, musttail=False))
                new_ops.append(ReturnVoid())
            else:
                tmp = StackVar(op.result_type, f"$musttail$ret${counter}")
                new_ops.append(dataclasses.replace(op, musttail=False, register=tmp))
                new_ops.append(Return(tmp))
        else:
            new_ops.append(op)
    return dataclasses.replace(fn, ops=tuple(new_ops))


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

# `task_subtype_name` moved to `task_abi` so other passes (notably
# `lazy_thunks`) can share the canonical naming and avoid casting one
# task subtype to a different one with merely-matching layout.
__task_subtype_name = task_subtype_name


def __extract_from_task(completed_task: RParam, callee_result_type: Type,
                        task_subtype_name: str | None) -> RParam:
    """Read the result from a completed task object."""
    if task_subtype_name is None or isinstance(callee_result_type, Void):
        return NullPointer()
    return ObjectField(callee_result_type, completed_task, task_subtype_name, "result", None)


def __zero_val(t: Type) -> RParam:
    """Explicit zero/null initialiser for a field (never rely on object_create zero-fill)."""
    if isinstance(t, DataPointer):
        return NullPointer()
    if isinstance(t, Int):
        return Integer(0, t.precision)
    return ZeroOf(t)


# ─────────────────────────────────────────────────────────────────────────────
# State object generation
# ─────────────────────────────────────────────────────────────────────────────

def __create_state_object(fn: Function, state_name: str,
                           layout: FrameLayout) -> Object:
    """Object that stores all state needed across async suspensions.

    Layout:
        type, my_task                 — header pointers (low slots)
        <inline pointer-bearing slots: fun_t, pointer-carrying structs, …>
        idx, $ptr_count, <pure non-pointer slots>   — moved to the end
        array[N] : object_t*          — every strictly-`object_t*` local
    Each inline slot is a coalesced field shared by same-typed, non-overlapping
    locals (see __compute_frame_layout). Pointer-bearing slots are kept ahead of
    the non-pointer remainder so their offsets — and hence their
    `object_pointer_locations` bits — stay low, independent of how many primitive
    slots follow. The strict-pointer bulk lives in the trailing array and is
    GC-scanned by length, not by mask bit.
    """
    inline_ptr = tuple((n, t) for n, t in layout.slot_fields if t.has_pointers)
    non_ptr    = tuple((n, t) for n, t in layout.slot_fields if not t.has_pointers)

    heap_fields: tuple[tuple[str, Type], ...] = (
        ("type",    DataPointer()),   # vtable (required first field)
        ("my_task", DataPointer()),   # our task (what we're fulfilling)
    ) + inline_ptr + (
        ("idx",        Int(32)),      # which call site we're suspended at
        ("$ptr_count", Int(32)),      # array length, for the GC scan
    ) + non_ptr + (
        ("array", Array(DataPointer(), 0)),   # strict object_t* locals
    )
    return Object(state_name, (), (), ImmediateStruct(heap_fields),
                  length_field="$ptr_count", comment=fn.comment,
                  is_mutable=True)   # idx + live vars rewritten at every suspension


# ─────────────────────────────────────────────────────────────────────────────
# Hot-path function
# ─────────────────────────────────────────────────────────────────────────────

def __create_hot_path_func(fn: Function, state_name: str,
                            task_subtype_name: str | None,
                            basic_blocks: list[BasicBlock],
                            layout: FrameLayout) -> Function:
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
    wrapped_result = wrap_return_type(fn.result)
    wrap_fields: list[tuple[str, Type]] = []

    # ── Collect all vars that end up as state-object fields ──────────────────
    # Used both for the prologue null-inits and for the common save block.
    # bb.live is a frozenset; iterate by SSA name (unique → total order) so the
    # collection order — and the generated C built from it — is deterministic.
    seen_state_var_names: set[str] = set()
    all_state_vars: list[StackVar] = []
    for bb in basic_blocks[:-1]:
        for var in sorted(bb.live, key=lambda v: v.name):
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

            hot_ops.extend(__convert_returns_for_hot_path(bb.ops[:-1], wrapped_result))
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
                # (only the Returns inside the body need conversion)
                hot_ops.extend(__convert_returns_for_hot_path(bb.ops, wrapped_result))
                continue
            # Non-void async call with discarded result: still need the task check
            # so the C cast uses the correct wrapped return type (avoids sret ABI mismatch).
            discarded_wrapped = wrap_return_type(discarded_type)
            sv_discard_wrap = StackVar(discarded_wrapped, f"$wrap${i}")
            wrap_fields.append((f"$wrap${i}", discarded_wrapped))
            hot_ops.extend(__convert_returns_for_hot_path(bb.ops[:-1], wrapped_result))
            hot_ops.append(dataclasses.replace(call_op, register=sv_discard_wrap))
            task_ptr = task_ptr_from(sv_discard_wrap, discarded_wrapped)
            hot_ops.append(IfTask(
                condition=is_task_param(sv_discard_wrap, discarded_wrapped),
                task_source=task_ptr,
                task_lhs=__sv_async_task,
                call_id_lhs=__sv_call_id,
                call_id=i + 1,
                target="$asynccommon"))
            # Value is discarded — no Move needed
            continue

        result_type  = result_var.get_type()
        wrapped_type = wrap_return_type(result_type)
        needs_temp   = (wrapped_type is not result_type)

        if needs_temp:
            # Pure-primitive callee: receive result in a temp wrapped-type var,
            # then unwrap on the sync path.
            sv_wrapped = StackVar(wrapped_type, f"$wrap${i}")
            wrap_fields.append((f"$wrap${i}", wrapped_type))
            hot_ops.extend(__convert_returns_for_hot_path(bb.ops[:-1], wrapped_result))
            hot_ops.append(dataclasses.replace(call_op, register=sv_wrapped))
            sv_for_check = sv_wrapped
        else:
            hot_ops.extend(__convert_returns_for_hot_path(bb.ops, wrapped_result))
            sv_for_check = result_var

        task_ptr = task_ptr_from(sv_for_check, wrapped_type)
        hot_ops.append(IfTask(
            condition=is_task_param(sv_for_check, wrapped_type),
            task_source=task_ptr,
            task_lhs=__sv_async_task,
            call_id_lhs=__sv_call_id,
            call_id=i + 1,     # 1-based: idx==0 must never reach dispatch
                               # (zero-init heap means uninitialised state)
            target="$asynccommon"))

        # Sync path: unwrap primitive if needed
        if needs_temp:
            hot_ops.append(Move(result_var, StructField(sv_wrapped, "value")))

    # Terminal block: same Return + musttail conversion as the per-call-site
    # bodies above. The terminal block is just the block whose last op isn't
    # a non-tail Call; structurally it has no special status.
    hot_ops.extend(__convert_returns_for_hot_path(basic_blocks[-1].ops, wrapped_result))

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

    # Allocate state object. It carries a trailing object_t* array (one slot per
    # strictly-pointer local), so it is allocated with an element count via
    # array_create — hence the size argument. array_create zero-fills, so any
    # inline slot a given call site does not write stays a GC-safe NULL.
    common_ops.append(NewObject(state_name, __sv_state, Integer(layout.n_array, 32)))

    # Save only the locals live at the suspending call site. Because inline slots
    # are shared between locals with disjoint live ranges, writing the whole union
    # would let a dead local clobber a live one in a shared slot — so we dispatch
    # on the recorded call id and save just that site's live set.
    non_terminal = basic_blocks[:-1]
    common_ops.append(SwitchJump(__sv_call_id,
        tuple((i + 1, f"$save${i}") for i in range(len(non_terminal)))))
    common_ops.append(Jump("$save$done"))   # default: unreachable (every suspend sets a known id)
    for i, bb in enumerate(non_terminal):
        common_ops.append(Label(f"$save${i}"))
        # Deterministic store order (bb.live is a frozenset); each save is
        # independent, so SSA-name order is as valid as any and reproducible.
        for var in sorted(bb.live, key=lambda v: v.name):
            common_ops.append(Move(
                __state_field(var.name, var.get_type(), __sv_state, state_name, layout),
                var))
        common_ops.append(Jump("$save$done"))
    common_ops.append(Label("$save$done"))

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
                                 basic_blocks: list[BasicBlock],
                                 layout: FrameLayout) -> Function:
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
        # Name-keyed lookup map; iterate the frozenset deterministically for
        # consistency with the other bb.live walks (first-wins by unique name,
        # so the result is order-independent regardless).
        for var in sorted(bb.live, key=lambda v: v.name):
            vars_to_fields.setdefault(var.name, __state_field(
                var.name, var.get_type(), __state_param_var, state_name, layout))
        if bb.result is not None and isinstance(bb.result, StackVar):
            vars_to_fields.setdefault(bb.result.name, __state_field(
                bb.result.name, bb.result.get_type(), __state_param_var, state_name, layout))

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

    # ── Body: bb[0]..bb[N-1] ops, with StackVar → state field substitution.
    #    bb[0] (the pre-first-suspend entry block) is included even though the
    #    dispatch never falls into it (the switch's default aborts): a [tail]
    #    loop whose body suspends has its loop head in bb[0], and the back-edge
    #    `recur` jumps to it, re-running the head→suspend region each iteration.
    #    For non-loop functions bb[0] is unreachable here and is pruned. Its
    #    `$resume$0` label is emitted by the i==0 iteration below.
    for i in range(0, n):
        bb = non_terminal[i]
        body_ops_before_call = bb.ops[:-1]
        call_op_orig         = bb.ops[-1]

        substituted_before = __convert_var_to_field_refs(body_ops_before_call, vars_to_fields)
        # An early Return inside a non-terminal block's body must also drive
        # task_complete — same conversion as the terminal block applies here.
        substituted_before = __convert_returns_for_state_machine(
            substituted_before, my_task_field, fn.result, task_subtype_name)
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
        wrapped_type    = wrap_return_type(result_type)  if result_type else None
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
            check_type = wrap_return_type(discarded_type)
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
                           NewStruct((("x", is_task_param(sv_check, check_type)),)),
                           Int(32))
            async_sm_label = f"$async_sm${i}"
            sm_ops.append(JumpIf(async_sm_label, check))
            if unwrap_op is not None:
                sm_ops.append(unwrap_op)
            sm_ops.append(Label(f"$resume${i}"))

            untagged = Invoke("TASK_UNTAG",
                              NewStruct((("p", task_ptr_from(sv_check, check_type)),)),
                              DataPointer())
            cold_ops.append(Label(async_sm_label))
            cold_ops.extend(_emit_suspend_to_async(idx_field, i + 1, untagged, fn.name))

    # ── Terminal block ────────────────────────────────────────────────────────
    # Same Return-conversion logic as the per-call-site bodies above. The
    # terminal block is just the block whose last op happens to not be a
    # non-tail Call; structurally it has no special status.
    terminal_bb = basic_blocks[-1]
    terminal_ops = __convert_var_to_field_refs(terminal_bb.ops, vars_to_fields)
    sm_ops.extend(__convert_returns_for_state_machine(
        terminal_ops, my_task_field, fn.result, task_subtype_name))

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

    all_ops = _prune_unreachable_phi_sources(tuple(sm_ops) + tuple(cold_ops) + tuple(dispatch_ops))

    extra_stack = Struct((("$sv_discard", DataPointer()),) + tuple(sm_wrap_fields))

    return Function(
        name=f"{fn.name}$async",
        params=Struct((("$state", DataPointer()), ("$completed_task", DataPointer()))),
        result=Void(),
        stack_vars=fn.stack_vars + extra_stack,
        ops=all_ops,
        comment=fn.comment,
    )


def _prune_unreachable_phi_sources(ops: tuple[Op, ...]) -> tuple[Op, ...]:
    """Block splitting across the hot path / state-machine boundary leaves
    Phi nodes whose source labels refer to predecessors now living in a
    different function. Drop those sources here so each remaining Phi has
    one source per actual predecessor in this function's CFG."""
    # Collect actual predecessor labels for every Phi block.
    block_predecessors: dict[str, set[str]] = {}
    current_block: str | None = None
    for i, op in enumerate(ops):
        if isinstance(op, Label):
            # Fall-through edge from the previous op's block (if any).
            if i > 0 and current_block is not None:
                prev = ops[i - 1]
                if not isinstance(prev, (Jump, Return, ReturnVoid, Abort)):
                    if not (isinstance(prev, Call) and prev.musttail):
                        block_predecessors.setdefault(op.name, set()).add(current_block)
            current_block = op.name
        elif isinstance(op, Jump):
            if current_block is not None:
                block_predecessors.setdefault(op.name, set()).add(current_block)
        elif isinstance(op, JumpIf):
            if current_block is not None:
                block_predecessors.setdefault(op.label, set()).add(current_block)
        elif isinstance(op, IfTask):
            if current_block is not None:
                block_predecessors.setdefault(op.target, set()).add(current_block)
        elif isinstance(op, SwitchJump):
            if current_block is not None:
                for _, lbl in op.cases:
                    block_predecessors.setdefault(lbl, set()).add(current_block)

    out: list[Op] = []
    current_block = None
    for op in ops:
        if isinstance(op, Label):
            current_block = op.name
            out.append(op)
            continue
        if isinstance(op, Phi) and current_block is not None:
            preds = block_predecessors.get(current_block, set())
            kept = tuple((lbl, v) for lbl, v in op.sources if lbl in preds)
            if kept == op.sources:
                out.append(op)
            elif kept:
                out.append(dataclasses.replace(op, sources=kept))
            # else: every source pruned → drop the Phi entirely (the target
            # is written elsewhere — e.g. in the hot-path function for an
            # arm that doesn't suspend).
            continue
        out.append(op)
    return tuple(out)


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
    # Skip __entrypoint__ – it bridges thread_start (legacy) to the new world
    if fn.name == "__entrypoint__":
        return {fn.name: fn}, {}

    # Functions explicitly marked bypass_async (hand-crafted trampoline
    # helpers, etc.) pass through unchanged — their ops are already in
    # final form and need no IS_TASK insertion, state machine, or wrap.
    if fn.bypass_async:
        return {fn.name: fn}, {}

    after_tail = __discover_tail_calls(fn)
    state_name = f"{fn.name}$state"
    basic_blocks = __create_basic_blocks(after_tail, state_name)

    # Functions with at most one block (no non-tail calls) need only
    # their return type adjusted (or kept as-is if it stays pointer-typed).
    if len(basic_blocks) < 2:
        wrapped = wrap_return_type(fn.result)
        if isinstance(wrapped, TaskWrapper):
            # Promote Return(v) → Return(SyncWrap(v, wrapped)) and update any
            # musttail Call result_type so the C cast uses the wrapped typedef.
            new_ops = []
            for op in after_tail.ops:
                if isinstance(op, Return):
                    # Skip the wrap when the Return value already has the
                    # wrapped shape (passes that hand-build async-pending
                    # returns supply pre-wrapped values).
                    if op.value.get_type() == wrapped:
                        new_ops.append(op)
                    else:
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

    # The state-machine view (musttail calls unrolled to Call+Return) defines the
    # authoritative frame layout — it may carry extra result temps the hot path
    # never materialises. Compute the frame layout (array slots + coalesced inline
    # slots) from it once and share it across the hot path, state object, and
    # state machine so every local lands in the same slot everywhere.
    if any(isinstance(op, Call) and op.musttail for op in after_tail.ops):
        sm_fn = __unroll_musttail_for_state_machine(after_tail)
        sm_basic_blocks = __create_basic_blocks(sm_fn, state_name)
    else:
        sm_fn = after_tail
        sm_basic_blocks = basic_blocks
    layout = __compute_frame_layout(sm_basic_blocks, basic_blocks,
                                    __calculate_saved_vars(sm_fn).ops)

    hot_fn = __create_hot_path_func(after_tail, state_name,
                                     task_subtype_name, basic_blocks, layout)

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

    # sm_fn / sm_basic_blocks (and the shared frame layout) were computed above so
    # the hot path and state machine agree on the frame layout. The state-machine
    # view re-expands musttail Calls to Call+Return so the existing terminal-Return
    # → task_complete logic fires; the hot path keeps the musttail.
    state_obj  = __create_state_object(sm_fn, state_name, layout)
    machine_fn = __create_state_machine_func(sm_fn, state_name,
                                              task_subtype_name, sm_basic_blocks, layout)
    functions = {hot_fn.name: hot_fn, machine_fn.name: machine_fn} | par_functions
    objects   = {state_obj.name: state_obj} | par_objects
    return functions, objects


# ─────────────────────────────────────────────────────────────────────────────
# Task-subtype Object generation (collected across all functions)
#
# `TASK_FIELDS` is defined in `lowering.task_abi` and shared with passes
# that synthesise task-aware code (e.g. tail_trampoline). Subtypes inherit
# those fields the normal YAFL way so `((task_t*)subtype)` hits each prefix
# field at the same offset by construction.
# ─────────────────────────────────────────────────────────────────────────────

# `_task_object` and `_task_subtype_object` were moved to task_abi.py
# (as `make_task_foreign_object` and `make_task_subtype_object`) so
# other passes (notably `lazy_thunks`) can pre-register subtypes under
# the canonical names without import-cycling through async_lower.
_task_object = make_task_foreign_object
_task_subtype_object = make_task_subtype_object


def _par_task_object(par_task_name: str, result_types: list[Type]) -> Object:
    """Generate the par_task struct for a parallel call site.

    Inherits task_t's prefix fields (so `(task_t*)par_task` and
    `(task_par_base_t*)par_task` both work), then appends per-instance
    fields: `remaining`, per-slot closure pointers, and per-slot results."""
    N = len(result_types)
    fields = TASK_FIELDS + (
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
        is_mutable=True,   # remaining counter + per-slot results written after construction
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
    wrapped_type = wrap_return_type(result_type)
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
                  NewStruct((("x", is_task_param(sv_result_w, wrapped_type)),)),
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
    task_ptr_k = task_ptr_from(sv_result_w, wrapped_type)
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
# Backpressure: outline each __parallel__ site behind a runtime fork/chain choice
# ─────────────────────────────────────────────────────────────────────────────

def __outline_parallel_sites(fn: Function) -> tuple[Function, dict[str, Function]]:
    """Replace each ParallelCall with a call to a synthesised dispatch helper.

    The helper asks the runtime's advisory backpressure signal and takes one
    of two arms:

        if (thread_work_accepting())     // queues hungry: spread the work
            <the original ParallelCall>  // par_task + launchers, suspend on join
        else                             // backlog full: stop fanning out
            r0 = slot0(closure0)         // ordinary chained calls — each may
            r1 = slot1(closure1)         //   suspend via the standard machinery,
            ...                          //   but no tasks are created or posted
            return (r0, r1, ...)

    Both arms produce the same tuple; in a pure language the choice is
    unobservable. The sequential arm allocates NO task machinery, so under
    load a recursive divide-and-conquer site degrades from breadth-first
    task explosion to depth-first chains — bounding queue length and the
    heap pinned by it. The helper is converted by the same async lowering
    as any other function, so both arms reuse the existing suspension and
    state-machine machinery unchanged.
    """
    if not any(isinstance(op, ParallelCall) for op in fn.ops):
        return fn, {}

    helpers: dict[str, Function] = {}
    new_ops: list[Op] = []
    for op_index, op in enumerate(fn.ops):
        # Only outline the well-formed shape (named slot functions, a result
        # tuple). Anything else keeps today's always-parallel lowering.
        if (not isinstance(op, ParallelCall)
                or op.register is None
                or not all(isinstance(c, GlobalFunction) for c in op.calls)):
            new_ops.append(op)
            continue

        helper_name = f"{fn.name}$par_site${op_index}"
        n_slots     = len(op.calls)

        # Helper params: the unused receiver slot, then one closure per slot.
        closure_params = tuple(StackVar(DataPointer(), f"$c{k}") for k in range(n_slots))
        helper_calls   = tuple(dataclasses.replace(c, object=closure_params[k])
                               for k, c in enumerate(op.calls))

        sv_accepting = StackVar(Int(32), "$accepting")
        seq_calls: list[Op] = [
            Call(helper_calls[k], NewStruct(()), op.results[k])
            for k in range(n_slots)
        ]
        helper_ops: tuple[Op, ...] = (
            Move(sv_accepting,
                 Invoke("thread_work_accepting", NewStruct(()), Int(32))),
            JumpIf("$fork", sv_accepting),
            # Sequential arm — falls through when the task system is busy.
            *seq_calls,
            Move(op.register,
                 NewStruct(tuple((f"_{k}", op.results[k]) for k in range(n_slots)))),
            Return(op.register),
            # Parallel arm.
            Label("$fork"),
            ParallelCall(calls=helper_calls, results=op.results, register=op.register),
            Return(op.register),
        )
        helpers[helper_name] = Function(
            name=helper_name,
            params=Struct((("$unused_self", DataPointer()),)
                          + tuple((p.name, DataPointer()) for p in closure_params)),
            result=op.register.get_type(),
            stack_vars=Struct(tuple((v.name, v.get_type())
                                    for v in (*op.results, op.register, sv_accepting))),
            ops=helper_ops,
            comment=f"__parallel__ backpressure dispatch for {fn.name} site {op_index}",
        )

        # The original site becomes an ordinary (suspendable) call.
        new_ops.append(Call(
            GlobalFunction(helper_name),
            NewStruct(tuple(
                (f"$c{k}", c.object if c.object is not None else NullPointer())
                for k, c in enumerate(op.calls))),
            op.register))

    return dataclasses.replace(fn, ops=tuple(new_ops)), helpers


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def lower_async(app: Application) -> Application:
    # Outline every __parallel__ site behind the backpressure choice first, so
    # the synthesised helpers are converted by the very same pass below.
    outlined: dict[str, Function] = {}
    for name, fn in app.functions.items():
        if fn.bypass_async or name == "__entrypoint__":
            outlined[name] = fn
            continue
        new_fn, helpers = __outline_parallel_sites(fn)
        outlined[name] = new_fn
        outlined |= helpers

    results = [__convert_function_to_task_convention(fn)
               for fn in outlined.values()]

    new_functions = reduce(lambda acc, v: acc | v[0], results, {})
    new_objects   = reduce(lambda acc, v: acc | v[1], results, {}) | app.objects

    # Add task-subtype objects (after conversion so return types are finalised).
    # The dict union `task_subtypes | tmp_app.objects` lets `tmp_app.objects`
    # win on key collisions — important because `lazy_thunks.ensure_lazy_machinery`
    # pre-registers task subtypes under the same canonical names, and we must
    # not clobber them.  Don't switch this to `.update()` or reversed-union
    # without also updating lazy_thunks.
    tmp_app = dataclasses.replace(app, functions=new_functions, objects=new_objects)
    task_subtypes = collect_task_subtypes(tmp_app)

    return dataclasses.replace(tmp_app,
                               objects=task_subtypes | tmp_app.objects)
