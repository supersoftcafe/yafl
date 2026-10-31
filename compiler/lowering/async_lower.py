from __future__ import annotations

# Async lowering: convert each function that has may-suspend calls into two C
# functions. A call through a function value proven sync (FuncPointer.sync,
# lowering/sync_inference.py) is a plain call and no suspension point.
#   1. Hot path  – original name, runs fully inline if all calls are sync.
#      After each may-suspend call, emits an UNLIKELY(IS_TASK) check; if true,
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
    wrap_return_type, wrap_value, unwrap_value, is_unit,
    is_task_param, task_ptr_from, pending_task_of,
    task_subtype_name, make_task_foreign_object, make_task_subtype_object,
    RUNTIME_TASK_SUBTYPES,
)
from codegen.gen import Application
from codegen.ops import Op, Call, Return, ReturnVoid, Move, Label, JumpIf, IfTask, AssertNotTask, Jump, NewObject, SwitchJump, Abort, Phi, Await
from codegen.ir import Function, Object
from codegen.typedecl import (
    FuncPointer, Void, Struct, ImmediateStruct, DataPointer, Int, Type, Array,
    TaskWrapper, first_pointer_field, is_task_check,
)
from codegen.param import (
    ObjectField, StackVar, LParam, GlobalVar, NewStruct, GlobalFunction, Integer,
    RParam, StructField, NullPointer, RuntimeInvoke, TagTask, IntEqConst, ZeroOf,
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
# so a single set of locals is enough.
__sv_state      = StackVar(DataPointer(), "$sv_state")
__sv_task       = StackVar(DataPointer(), "$sv_task")
__sv_discard    = StackVar(DataPointer(), "$sv_discard")
__sv_call_id    = StackVar(Int(32),       "$sv_call_id")    # call-site index for asynccommon
__sv_async_task = StackVar(DataPointer(), "$sv_async_task") # TASK_UNTAG'd task ptr for asynccommon


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
                RuntimeInvoke("task_complete", NewStruct((("self", my_task_field),)), DataPointer()),
                keep=True))
            out.append(ReturnVoid())
        elif isinstance(op, ReturnVoid):
            out.append(Move(
                __sv_discard,
                RuntimeInvoke("task_complete", NewStruct((("self", my_task_field),)), DataPointer()),
                keep=True))
            out.append(ReturnVoid())
        else:
            out.append(op)
    return out


def __convert_returns_for_hot_path(
        ops: Iterable[Op],
        fn_result: Type) -> list[Op]:
    """Bring each Return's value into the function's task-carrying return
    shape (`wrap_value`), and each musttail Call's result_type into line
    with it so the emitted C cast `((wrapped_t(*)(…))callee)(…)` agrees with
    the surrounding `return` statement's type.

    A no-op when the return type carries the task signal in-band.
    """
    wrapped_result = wrap_return_type(fn_result)
    if wrapped_result == fn_result:
        return list(ops)
    out: list[Op] = []
    for op in ops:
        if isinstance(op, Return):
            out.append(Return(wrap_value(op.value, wrapped_result)))
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

def _emit_task_alloc(sv_task: StackVar, task_subtype_name: str | None) -> tuple[Op, ...]:
    """Allocate the task object that this function will fulfil.

    Three paths, all leaving sv_task pointing at a fully task_init'd task:
      - None        : Void-returning function uses the base task_t.
      - RUNTIME_TASK_SUBTYPES : pre-declared yafllib subtypes (task_obj,
                                task_str), each initialised by `<name>_create`.
      - other       : compiler-synthesised subtype, allocate via NewObject + task_init.
    """
    if task_subtype_name is None:
        return (Move(sv_task,
            RuntimeInvoke("task_create", NewStruct((("self", NullPointer()),)), DataPointer())),)
    if task_subtype_name in RUNTIME_TASK_SUBTYPES:
        return (Move(sv_task,
            RuntimeInvoke(f"{task_subtype_name}_create", NewStruct((("self", NullPointer()),)),
                          DataPointer())),)
    return (
        NewObject(task_subtype_name, sv_task),
        Move(__sv_discard,
             RuntimeInvoke("task_init", NewStruct((("task", sv_task),)), DataPointer()),
             keep=True),
    )


def _emit_suspend_to_async(idx_field: LParam, idx: int, untagged_task: RParam,
                            fn_name: str) -> tuple[Op, ...]:
    """SM cold-block tail: write idx, register fn$async on the in-flight task, return.

    `untagged_task` must already be a clean task_t pointer (no PTR_TAG_TASK bit
    set): call-site cold blocks wrap their tagged result in TASK_UNTAG first.
    """
    callback = GlobalFunction(f"{fn_name}$async", __state_param_var)
    return (
        Move(idx_field, Integer(idx, 32)),
        Move(__sv_discard,
             RuntimeInvoke("task_on_complete",
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

    # reads/writes depend only on op STRUCTURE, which never changes across
    # passes (only saved_vars does) — computed once, not per generation.
    rw_cache = [reads_writes(op) for op in ops0]

    def do_a_pass(ops: tuple[Op, ...]) -> tuple[Op, ...]:
        # Liveness is a BACKWARD analysis, so the sweep runs backward and reads
        # successors out of the generation being built (`cur`). A forward sweep
        # read them from the PREVIOUS generation, which moves information
        # backward exactly one op per pass — P grew linearly with function
        # length and the fixpoint cost O(ops^2) op-visits (measured: an 82-op
        # function took 46 passes). Reading the freshest available value is
        # ordinary chaotic iteration: same monotone transfer functions, so the
        # same least fixed point, reached in a couple of passes.
        cur = list(ops)

        def saved_set_at(index: int) -> frozenset[StackVar]:
            return rw_cache[index][0] | cur[index].saved_vars

        def phi_sources_into(target_index: int, pred: str | None) -> frozenset[StackVar]:
            srcs: frozenset[StackVar] = frozenset()
            j = target_index + 1
            while j < n and isinstance(cur[j], Phi):
                for lbl, v in cur[j].sources:
                    if lbl == pred:
                        srcs = srcs | v.get_live_vars()
                j += 1
            return srcs

        def edge_in(from_index: int, target_index: int) -> frozenset[StackVar]:
            return saved_set_at(target_index) | phi_sources_into(target_index, block_label[from_index])

        def calc(index: int) -> Op:
            op = cur[index]
            # A Jump's successor is its label WHEREVER the op sits — testing
            # last-op first severed the back edge of a loop whose back-edge
            # Jump was the function's final op (the array-ctor fill inlined
            # into a tail position), so nothing loop-carried was saved
            # across a park inside that loop.
            if isinstance(op, Jump):
                ss1 = edge_in(index, labels[op.name]) if op.name in labels else frozenset()
            elif index >= n - 1:
                ss1 = frozenset()
            else:
                ss1 = edge_in(index, index + 1)
            ss2 = (edge_in(index, labels[op.label])
                   if isinstance(op, JumpIf) and op.label in labels else frozenset())
            saved_vars = (ss1 | ss2) - rw_cache[index][1]
            return dataclasses.replace(op, saved_vars=saved_vars)

        for index in range(len(ops) - 1, -1, -1):
            cur[index] = calc(index)
        return tuple(cur)

    def iterate(ops: tuple[Op, ...]) -> tuple[Op, ...]:
        # A LOOP, not recursion: the recursive form pinned every generation
        # of the full op tuple (fresh Op + frozenset per instruction, per
        # pass) on the Python stack until convergence — O(ops x passes) live
        # memory, an 11GB+ MemoryError on -O3's inlined functions. The loop
        # frees each generation as the next lands; results are identical.
        while True:
            new_ops = do_a_pass(ops)
            if ops == new_ops:
                return ops
            ops = new_ops

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
    # Structs whose every leaf is a strict pointer live DECOMPOSED in the
    # trailing array (base index; one element per leaf): the array is length-
    # scanned by the GC, so these need no object_pointer_locations bits —
    # the mask is a single word and a big fused frame's inline slots can
    # exceed it. Only mixed structs (raw ints alongside pointers) stay inline.
    decomposed:   dict[str, int] = dataclasses.field(default_factory=dict)


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

    def link_all_pairs(names: list[str], prev: set[str]) -> None:
        """Every pair in `names`, given that every pair in `prev` is already
        linked: a pair of two names both in `prev` is, so only the names new
        since `prev` need linking — against the whole set. Neighbouring ops'
        live sets are nearly equal, so this is O(new·L), not O(L²), per op,
        and the edge set is exactly the all-pairs one."""
        for a in names:
            if a not in prev:
                for b in names:
                    link(a, b)

    for ops in op_sequences:
        prev_out: set[str] = set()
        prev_in: set[str] = set()
        for op in ops:
            live_out = [v.name for v in op.saved_vars if v.name in graph]
            writes = {w.name for w in __op_writes(op)}
            link_all_pairs(live_out, prev_out)
            for w in writes:
                if w in graph:
                    for n in live_out:
                        link(w, n)
            live_in = [v.name for v in __op_reads(op) if v.name in graph]
            live_in += [n for n in live_out if n not in writes]
            link_all_pairs(live_in, prev_in)
            prev_out, prev_in = set(live_out), set(live_in)
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
    decomposed: dict[str, int] = {}
    n_array = 0
    for type_index, (typ, names) in enumerate(by_type.items()):
        colour = __colour(names, graph)
        leaves = __ptr_leaves(typ)
        if isinstance(typ, DataPointer):
            base = n_array
            for name in names:
                ptr_slots[name] = base + colour[name]
            n_array += len(set(colour.values()))
        elif leaves is not None:
            # All-pointer struct: decomposed into the maskless trailing array
            # (see FrameLayout.decomposed), coalesced like any other slot.
            width = len(leaves)
            colour_base = {c: n_array + i * width
                           for i, c in enumerate(sorted(set(colour.values())))}
            for name in names:
                decomposed[name] = colour_base[colour[name]]
            n_array += width * len(colour_base)
        else:
            for c in sorted(set(colour.values())):
                slot_fields.append((f"$slot${type_index}${c}", typ))
            for name in names:
                inline_slots[name] = f"$slot${type_index}${colour[name]}"

    return FrameLayout(ptr_slots, inline_slots, tuple(slot_fields), n_array,
                       decomposed)


def __ptr_leaves(typ: Type) -> list[tuple[str, ...]] | None:
    """Leaf field paths when every leaf of `typ` is a strict pointer; None
    otherwise (or when it isn't a struct at all)."""
    if not isinstance(typ, Struct):
        return None
    out: list[tuple[str, ...]] = []
    for fname, ftype in typ.fields:
        if isinstance(ftype, DataPointer):
            out.append((fname,))
        elif isinstance(ftype, Struct):
            inner = __ptr_leaves(ftype)
            if inner is None:
                return None
            out.extend((fname,) + path for path in inner)
        else:
            return None
    return out if out else None


def __array_elem(state_param: RParam, state_name: str, index: int) -> ObjectField:
    return ObjectField(DataPointer(), state_param, state_name, "array",
                       Integer(index, 32))


def __store_var(var: StackVar, state_param: RParam, state_name: str,
                layout: FrameLayout) -> list[Op]:
    """local → state; a decomposed struct stores one leaf per array element."""
    if var.name in layout.decomposed:
        base = layout.decomposed[var.name]
        paths = __ptr_leaves(var.get_type())
        ops: list[Op] = []
        for i, path in enumerate(paths):
            src: RParam = var
            for f in path:
                src = StructField(src, f)
            ops.append(Move(__array_elem(state_param, state_name, base + i), src))
        return ops
    return [Move(__state_field(var.name, var.get_type(), state_param,
                               state_name, layout), var)]


def __load_var(var: StackVar, state_param: RParam, state_name: str,
               layout: FrameLayout) -> list[Op]:
    """state → local; a decomposed struct is rebuilt from its array elements."""
    if var.name in layout.decomposed:
        base = layout.decomposed[var.name]
        typ = var.get_type()

        def build(t: Struct, idx: list[int]) -> RParam:
            values = []
            for fname, ftype in t.fields:
                if isinstance(ftype, Struct):
                    values.append((fname, build(ftype, idx)))
                else:
                    values.append((fname, __array_elem(state_param, state_name,
                                                       base + idx[0])))
                    idx[0] += 1
            return NewStruct(tuple(values))

        return [Move(var, build(typ, [0]))]
    return [Move(var, __state_field(var.name, var.get_type(), state_param,
                                    state_name, layout))]


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


def __expand_sync_call(op: Call, wrap_name: str) -> tuple[list[Op], list[tuple[str, Type]]]:
    """A call proven sync is a plain call: no block split, no IfTask. It
    keeps the uniform task-carrying return ABI — its callee may also be
    reached from a may-suspend site — so a primitive result is received in
    its wrapped shape (`wrap_name`) and unwrapped, and every result passes
    a debug-build AssertNotTask. Returns the ops and any locals they add."""
    if op.register is not None:
        result_type = op.register.get_type()
    elif op.result_type is not None and not isinstance(op.result_type, Void):
        result_type = op.result_type
    else:
        return [op], []     # void: nothing comes back to check
    wrapped = wrap_return_type(result_type)
    if op.register is not None and wrapped is result_type:
        return [op, AssertNotTask(is_task_param(op.register, wrapped))], []
    received = StackVar(wrapped, wrap_name)
    ops: list[Op] = [dataclasses.replace(op, register=received),
                     AssertNotTask(is_task_param(received, wrapped))]
    if op.register is not None:
        ops.append(Move(op.register, unwrap_value(received, result_type)))
    return ops, [(wrap_name, wrapped)]


def __expand_sync_calls(fn: Function) -> Function:
    """Expand every non-tail sync Call (`__expand_sync_call`). Runs after
    tail discovery, so a sync call in tail position stays a musttail that
    passes its callee's result straight through."""
    new_ops: list[Op] = []
    new_vars: list[tuple[str, Type]] = []
    for index, op in enumerate(fn.ops):
        if isinstance(op, Call) and not op.musttail and op.is_sync:
            wrap_name = f"$syncwrap${op.register.name}" if isinstance(op.register, StackVar) \
                else f"$syncwrap${index}"
            ops, added = __expand_sync_call(op, wrap_name)
            new_ops.extend(ops)
            new_vars.extend(added)
        else:
            new_ops.append(op)
    if len(new_ops) == len(fn.ops):
        return fn
    return dataclasses.replace(fn, ops=tuple(new_ops),
                               stack_vars=fn.stack_vars + Struct(tuple(new_vars)))


# ─────────────────────────────────────────────────────────────────────────────
# Deferred awaits (lowering/defer_awaits.py places them)
#
# An `Await` realises a deferred call's result where it is used: it parks only
# on a task still running; a completed one is read in place, so every later
# use is a test. A `returned` Await is for a Return of the whole value: the hot
# path hands the pending value to the caller as it stands.
# ─────────────────────────────────────────────────────────────────────────────

def __await_task(op: Await) -> RParam:
    """The task an Await's pending value holds, untagged, or NULL."""
    return pending_task_of(op.source, op.source.get_type())


def __task_running(op: Await) -> RParam:
    return RuntimeInvoke("TASK_RUNNING", NewStruct((("task", __await_task(op)),)), Int(32))


def __await_value(op: Await, label: str) -> list[Op]:
    """An Await that did not park: the value from the completed task when
    there was one, else as the call returned it."""
    result_type = op.register.get_type()
    return [JumpIf(f"{label}$done", __await_task(op)),
            Move(op.register, unwrap_value(op.source, result_type)),
            Jump(f"{label}$end"),
            Label(f"{label}$done"),
            Move(op.register, __extract_from_task(__await_task(op), result_type,
                                                  __task_subtype_name(result_type))),
            Label(f"{label}$end")]


def __return_unparked(fn: Function) -> Function:
    """When a function's only suspension points are `returned` Awaits it never
    parks: each such Await, with the projection and Return that follow it,
    becomes the Return of the pending value itself, and the function needs
    no state machine."""
    if not any(isinstance(op, Await) and op.returned for op in fn.ops):
        return fn
    if any((isinstance(op, Call) and op.may_suspend) or (isinstance(op, Await) and not op.returned)
           for op in fn.ops):
        return fn
    new_ops: list[Op] = []
    skipping = False
    for op in fn.ops:
        if skipping:
            skipping = not isinstance(op, Return)
        elif isinstance(op, Await):
            new_ops.append(Return(op.source))
            skipping = True
        else:
            new_ops.append(op)
    return dataclasses.replace(fn, ops=tuple(new_ops))


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
    field via the existing `__create_state_object` machinery — unless the
    call is sync, when it is expanded in place (`__expand_sync_call`) and
    never splits a block.
    """
    new_ops: list[Op] = []
    new_vars: list[tuple[str, Type]] = []
    counter = 0
    for op in fn.ops:
        if isinstance(op, Call) and op.musttail:
            counter += 1
            if op.result_type is None or isinstance(op.result_type, Void):
                new_ops.append(dataclasses.replace(op, musttail=False))
                new_ops.append(ReturnVoid())
            else:
                tmp = StackVar(op.result_type, f"$musttail$ret${counter}")
                call = dataclasses.replace(op, musttail=False, register=tmp)
                if call.is_sync:
                    # Not a block boundary, so no block result declares
                    # `tmp` — declare it (and any wrap local) here.
                    ops, added = __expand_sync_call(call, f"$syncwrap${tmp.name}")
                    new_ops.extend(ops)
                    new_vars.extend([(tmp.name, tmp.type)] + added)
                else:
                    new_ops.append(call)
                new_ops.append(Return(tmp))
        else:
            new_ops.append(op)
    return dataclasses.replace(fn, ops=tuple(new_ops),
                               stack_vars=fn.stack_vars + Struct(tuple(new_vars)))


def __create_basic_blocks(fn: Function, state_name: str) -> list[BasicBlock]:
    liveness_fn = __calculate_saved_vars(fn)
    partitions = langtools.partition(liveness_fn.ops,
                                     lambda op: (isinstance(op, Call) and op.may_suspend)
                                                 or isinstance(op, Await))

    def make_block(index: int, ops: list[Op]) -> BasicBlock:
        name = f"cont${index}"
        last_op = ops[-1]
        result = last_op.register if isinstance(last_op, (Call, Await)) else None
        augmented = ops
        return BasicBlock(name, augmented, last_op.saved_vars, result)

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
    if is_unit(callee_result_type):
        return ZeroOf(callee_result_type)
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

        if isinstance(call_op, Await) and call_op.returned:
            # Returned whole: the caller takes the pending value as it stands.
            hot_ops.extend(__convert_returns_for_hot_path(bb.ops[:-1], fn.result))
            hot_ops.append(Return(call_op.source))
            continue

        if isinstance(call_op, Await):
            # The deferred call ran earlier; park on its task if it is still
            # running, else take the value: from the task, or as returned.
            hot_ops.extend(__convert_returns_for_hot_path(bb.ops[:-1], fn.result))
            hot_ops.append(IfTask(
                condition=__task_running(call_op),
                task_source=__await_task(call_op),
                task_lhs=__sv_async_task,
                call_id_lhs=__sv_call_id,
                call_id=i + 1,
                target="$asynccommon"))
            hot_ops.extend(__await_value(call_op, f"$await${i}"))
            continue

        assert isinstance(call_op, Call) and call_op.may_suspend
        result_var = call_op.register

        if result_var is None:
            discarded_type = call_op.result_type
            if discarded_type is None:
                # Truly void-returning — cannot be a task; emit unchanged
                # (only the Returns inside the body need conversion)
                hot_ops.extend(__convert_returns_for_hot_path(bb.ops, fn.result))
                continue
            # Non-void async call with discarded result: still need the task check
            # so the C cast uses the correct wrapped return type (avoids sret ABI mismatch).
            discarded_wrapped = wrap_return_type(discarded_type)
            sv_discard_wrap = StackVar(discarded_wrapped, f"$wrap${i}")
            wrap_fields.append((f"$wrap${i}", discarded_wrapped))
            hot_ops.extend(__convert_returns_for_hot_path(bb.ops[:-1], fn.result))
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
            hot_ops.extend(__convert_returns_for_hot_path(bb.ops[:-1], fn.result))
            hot_ops.append(dataclasses.replace(call_op, register=sv_wrapped))
            sv_for_check = sv_wrapped
        else:
            hot_ops.extend(__convert_returns_for_hot_path(bb.ops, fn.result))
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
            hot_ops.append(Move(result_var, unwrap_value(sv_wrapped, result_type)))

    # Terminal block: same Return + musttail conversion as the per-call-site
    # bodies above. The terminal block is just the block whose last op isn't
    # a non-tail Call; structurally it has no special status.
    hot_ops.extend(__convert_returns_for_hot_path(basic_blocks[-1].ops, fn.result))

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

    if fn.sync:
        common_ops.append(Abort(reason="sync function reached $asynccommon"))
        extra_stack = Struct((
            ("$sv_call_id",    Int(32)),
            ("$sv_async_task", DataPointer()),
        ) + tuple(wrap_fields))
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
            common_ops.extend(__store_var(var, __sv_state, state_name, layout))
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
        RuntimeInvoke("task_on_complete",
               NewStruct((("task", __sv_async_task), ("cb", callback))),
               DataPointer()),
        keep=True))
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


# A function this large doesn't get the full duplicated linear launch body:
# the hot path and the state machine are near-identical twins, and past this
# size the twin costs more (binary size, clang's register allocator working
# the same giant body twice) than the sync fast path is worth. Instead a
# small STUB allocates the heap frame immediately, stores the parameters,
# and transfers control to the state machine via its entry case — which now
# runs on locals at hot-path speed anyway (see __create_state_machine_func).
_STUB_THRESHOLD_OPS = 256

# DISABLED pending a sync-entry bug: a stubbed function driven to completion
# on the caller's stack (Json::prettyString via collect — no IO anywhere)
# aborts at runtime; the IO-driven path works. Suspect the entry-case /
# completion interaction when the machine never actually parks. Flip once
# diagnosed — tests/test_json_string.py pins the failing case at -O3.
_STUB_ENABLED = True


def __augment_layout_with_params(layout: FrameLayout, params) -> FrameLayout:
    """Stub mode: every parameter needs a state field (the stub stores them,
    the entry case reloads them), not just those live across a suspension."""
    ptr_slots = dict(layout.ptr_slots)
    inline_slots = dict(layout.inline_slots)
    slot_fields = list(layout.slot_fields)
    n_array = layout.n_array
    decomposed = dict(layout.decomposed)
    placed = (set(ptr_slots) | set(inline_slots) | set(decomposed)
              | {n for n, _ in slot_fields})
    for name, typ in params.fields:
        if name in placed:
            continue
        leaves = __ptr_leaves(typ)
        if isinstance(typ, DataPointer):
            ptr_slots[name] = n_array
            n_array += 1
        elif leaves is not None:
            decomposed[name] = n_array
            n_array += len(leaves)
        else:
            inline_slots[name] = name
            slot_fields.append((name, typ))
    return FrameLayout(ptr_slots, inline_slots, tuple(slot_fields), n_array,
                       decomposed)


def __create_stub_launch_func(fn: Function, state_name: str,
                               task_subtype_name: str | None,
                               layout: FrameLayout, entry_idx: int) -> Function:
    """The linear-launch replacement for oversized functions: allocate the
    state object, park the parameters, allocate the task, and run the state
    machine's entry case on this C stack. Sync completion still works — the
    caller receives a task that is already complete, and task_on_complete
    fires immediately on registration."""
    wrapped_result = wrap_return_type(fn.result)
    ops: list[Op] = [NewObject(state_name, __sv_state, Integer(layout.n_array, 32))]
    for name, typ in fn.params.fields:
        ops.extend(__store_var(StackVar(typ, name), __sv_state, state_name, layout))
    ops.append(Move(
        ObjectField(DataPointer(), __sv_state, state_name, "my_task", None),
        NullPointer()))
    ops.append(Move(
        ObjectField(Int(32), __sv_state, state_name, "idx", None),
        Integer(entry_idx, 32)))
    ops.extend(_emit_task_alloc(__sv_task, task_subtype_name))
    ops.append(Move(
        ObjectField(DataPointer(), __sv_state, state_name, "my_task", None),
        __sv_task))
    # The machine's C signature is ($state, $completed_task); a Call's first
    # argument slot is the callee object, so the state rides there.
    ops.append(Call(
        function=GlobalFunction(f"{fn.name}$async", __sv_state),
        parameters=NewStruct((("$completed_task", NullPointer()),)),
        register=None))
    ops.append(Return(TagTask(__sv_task, wrapped_result)))
    # `_emit_task_alloc`'s synthesised-subtype path discards the `task_init`
    # result through `$sv_discard` (a `keep=True` write kept only for its side
    # effect). Declare that local exactly when the ops actually write it — so
    # clang neither hits an undeclared identifier (when the write is present)
    # nor warns on an unused local (the base task_t / `task_obj` paths omit it).
    sv_fields = [("$sv_state", DataPointer()), ("$sv_task", DataPointer())]
    if any(isinstance(op, Move) and isinstance(op.target, StackVar)
           and op.target.name == __sv_discard.name for op in ops):
        sv_fields.append(("$sv_discard", DataPointer()))
    return dataclasses.replace(
        fn, result=wrapped_result, ops=tuple(ops),
        stack_vars=Struct(tuple(sv_fields)))


# ─────────────────────────────────────────────────────────────────────────────
# State-machine function
# ─────────────────────────────────────────────────────────────────────────────

def __create_state_machine_func(fn: Function, state_name: str,
                                 task_subtype_name: str | None,
                                 basic_blocks: list[BasicBlock],
                                 layout: FrameLayout,
                                 with_entry_case: bool = False) -> Function:
    """
    void foo$async(object_t* $state, object_t* $completed_task)

    Dispatches on $state->idx, extracts the result from $completed_task, then
    runs the remainder of the function as a state machine.

    The body runs on ORDINARY C LOCALS, exactly like the hot path: state
    fields are touched only at the two suspension boundaries. Each dispatch
    case loads its site's live set (field → local) and jumps to the resume
    point; each suspend edge stores it back (local → field) before parking.
    The sync fall-through — a call that completed without suspending — pays
    nothing. This keeps the machine's heap traffic (and every GC write
    barrier it implies) proportional to suspensions taken, not to ops
    executed; the fused-drain regression this replaced was per-op field
    addressing making the whole hot loop barrier-bound once the first
    suspension parked the loop in this function.

    The resume label therefore joins two edges that deliver the same
    variables by NAME (sync defs vs dispatch loads) without a Phi — this
    function is deliberately phi-lowered at those joins, and ssa_validate
    exempts `$async` functions from the single-definition check for exactly
    this reason.
    """
    non_terminal = basic_blocks[:-1]   # blocks that end with a non-tail call
    n = len(non_terminal)

    def field_for(var: StackVar) -> LParam:
        return __state_field(var.name, var.get_type(), __state_param_var,
                             state_name, layout)

    # Park stores skip values the machine can only ever have LOADED: a var
    # with no definition anywhere in the body (a loop-invariant — stream
    # handle, config) reached this park holding exactly the value its field
    # already holds, because the only way into the machine is a dispatch
    # load. (Slot coalescing cannot have clobbered the field in between:
    # slots are shared only between non-overlapping live ranges, and this
    # var was live throughout.) Loads must stay unfiltered — the field is
    # always current, the local only exists after a load.
    body_defs: set[str] = set()
    for bb_scan in basic_blocks:
        for op_scan in bb_scan.ops:
            for sv in op_scan.get_live_vars()[1]:
                body_defs.add(sv.name)

    idx_field = ObjectField(Int(32), __state_param_var, state_name, "idx", None)
    my_task_field = ObjectField(DataPointer(), __state_param_var, state_name, "my_task", None)

    sm_ops: list[Op] = []
    cold_ops: list[Op] = []
    sm_wrap_fields: list[tuple[str, Type]] = []

    # ── Dispatch: switch on idx (1-based); every valid resume has a case
    #    mapped to a label in dispatch_ops; idx==0 (uninitialised state) and
    #    any out-of-range value hit the default abort. ──────────────────────
    cases = tuple((i + 1, f"$case${i + 1}") for i in range(n))
    if with_entry_case:
        # Stub mode (oversized function, no linear launch body): the stub
        # parks the parameters and sets idx to the entry case, which reloads
        # them and starts the body from the top on this C stack.
        cases += ((n + 1, "$case$entry"),)
    sm_ops.append(SwitchJump(idx_field, cases))
    if with_entry_case:
        sm_ops.append(Label("$sm$body"))

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

        # Body ops run on their original locals — only the boundaries below
        # touch the state object. Early Returns still drive task_complete.
        sm_ops.extend(__convert_returns_for_state_machine(
            body_ops_before_call, my_task_field, fn.result, task_subtype_name))

        # local → field, in the hot path's deterministic $save$i order;
        # never-defined (loaded-only) values are already current in the state.
        save_stores = tuple(op for var in sorted(bb.live, key=lambda v: v.name)
                            if var.name in body_defs
                            for op in __store_var(var, __state_param_var, state_name, layout))

        if isinstance(call_op_orig, Await):
            # The deferred call ran earlier: park on its task if still
            # running; on the sync edge, take the value.
            async_sm_label = f"$async_sm${i}"
            sm_ops.append(JumpIf(async_sm_label, RuntimeInvoke(
                "UNLIKELY", NewStruct((("x", __task_running(call_op_orig)),)), Int(32))))
            sm_ops.extend(__await_value(call_op_orig, f"$await_sm${i}"))
            sm_ops.append(Label(f"$resume${i}"))
            cold_ops.append(Label(async_sm_label))
            cold_ops.extend(save_stores)
            cold_ops.extend(_emit_suspend_to_async(idx_field, i + 1, __await_task(call_op_orig), fn.name))
            continue

        result_type     = call_op_orig.register.get_type() if call_op_orig.register else None
        discarded_type  = None if result_type is not None else call_op_orig.result_type
        wrapped_type    = wrap_return_type(result_type)  if result_type else None
        needs_temp      = result_type is not None and (wrapped_type is not result_type)

        call_subst = call_op_orig

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
            unwrap_op = Move(call_subst.register, unwrap_value(sv_check, result_type))
        else:
            check_type = wrapped_type
            sv_check   = call_subst.register   # may be None for void calls
            sm_ops.append(call_subst)
            unwrap_op = None

        if sv_check is None:
            # Void call: nothing to test; resume falls through directly.
            sm_ops.append(Label(f"$resume${i}"))
        else:
            check = RuntimeInvoke("UNLIKELY",
                           NewStruct((("x", is_task_param(sv_check, check_type)),)),
                           Int(32))
            async_sm_label = f"$async_sm${i}"
            sm_ops.append(JumpIf(async_sm_label, check))
            if unwrap_op is not None:
                sm_ops.append(unwrap_op)
            sm_ops.append(Label(f"$resume${i}"))

            untagged = RuntimeInvoke("TASK_UNTAG",
                              NewStruct((("p", task_ptr_from(sv_check, check_type)),)),
                              DataPointer())
            # The park path: this is the ONLY place block i's locals reach
            # the state object — the sync fall-through above never does.
            cold_ops.append(Label(async_sm_label))
            cold_ops.extend(save_stores)
            cold_ops.extend(_emit_suspend_to_async(idx_field, i + 1, untagged, fn.name))

    # ── Terminal block ────────────────────────────────────────────────────────
    # Same Return-conversion logic as the per-call-site bodies above. The
    # terminal block is just the block whose last op happens to not be a
    # non-tail Call; structurally it has no special status.
    terminal_bb = basic_blocks[-1]
    sm_ops.extend(__convert_returns_for_state_machine(
        terminal_bb.ops, my_task_field, fn.result, task_subtype_name))

    # ── Dispatch targets for idx 1..N (at tail, after cold blocks). Case
    #    (i+1) handles completion of non_terminal[i]'s call: reload the site's
    #    live set (field → local), extract that call's result from the
    #    completed task into its local register, then jump to $resume$i.
    dispatch_ops: list[Op] = []
    for i in range(n):
        bb = non_terminal[i]
        dispatch_ops.append(Label(f"$case${i + 1}"))
        for var in sorted(bb.live, key=lambda v: v.name):
            dispatch_ops.extend(__load_var(var, __state_param_var, state_name, layout))
        if bb.result is not None and isinstance(bb.result, StackVar):
            callee_task_name = __task_subtype_name(bb.result.get_type())
            extract = __extract_from_task(__completed_param_var, bb.result.get_type(),
                                           callee_task_name)
            dispatch_ops.append(Move(bb.result, extract))
        dispatch_ops.append(Jump(f"$resume${i}"))
    if with_entry_case:
        # The entry case defines the parameters (parked by the stub) AND every
        # park-stored local from its zero-filled field: a first-iteration park
        # may store a local whose definition lives on a later-iteration path,
        # and the zero it reloads here is exactly what the field-addressed
        # machine used to read. Runs once per activation.
        dispatch_ops.append(Label("$case$entry"))
        entry_defined: set[str] = set()
        for name, typ in fn.params.fields:
            entry_defined.add(name)
            dispatch_ops.extend(__load_var(StackVar(typ, name),
                                           __state_param_var, state_name, layout))
        for bb in non_terminal:
            for var in sorted(bb.live, key=lambda v: v.name):
                if var.name not in entry_defined:
                    entry_defined.add(var.name)
                    dispatch_ops.extend(__load_var(var, __state_param_var, state_name, layout))
        dispatch_ops.append(Jump("$sm$body"))

    all_ops = _prune_unreachable_phi_sources(tuple(sm_ops) + tuple(cold_ops) + tuple(dispatch_ops))

    # The original function's PARAMETERS become plain locals here (the SM's
    # own signature is just $state/$completed_task): a param live across a
    # suspension is reloaded by the dispatch like any other local, so it
    # needs a local slot to land in. Likewise block RESULT registers that
    # exist nowhere else — the musttail-unroll's `$musttail$ret$N` temps are
    # minted during this pass and were previously "declared" by the very
    # field substitution this design removed.
    declared = {n for n, _ in fn.stack_vars.fields}
    extra_locals: list[tuple[str, Type]] = []
    for name, typ in fn.params.fields:
        if name not in declared:
            declared.add(name)
            extra_locals.append((name, typ))
    for bb in basic_blocks:
        if isinstance(bb.result, StackVar) and bb.result.name not in declared:
            declared.add(bb.result.name)
            extra_locals.append((bb.result.name, bb.result.get_type()))
    param_locals = Struct(tuple(extra_locals))
    extra_stack = Struct((("$sv_discard", DataPointer()),) + tuple(sm_wrap_fields))

    return Function(
        name=f"{fn.name}$async",
        params=Struct((("$state", DataPointer()), ("$completed_task", DataPointer()))),
        result=Void(),
        stack_vars=fn.stack_vars + param_locals + extra_stack,
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
            if i > 0 and current_block is not None and ops[i - 1].falls_through():
                block_predecessors.setdefault(op.name, set()).add(current_block)
            current_block = op.name
        elif current_block is not None:
            for target in op.branch_targets():
                block_predecessors.setdefault(target, set()).add(current_block)

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
    Sync calls are plain calls (`__expand_sync_calls`); only a may-suspend
    call is a suspension point. If the function has none: just wrap its
    return type. Otherwise: produce the hot-path function (with the cold $asynccommon
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

    after_tail = __return_unparked(__expand_sync_calls(__discover_tail_calls(fn)))
    state_name = f"{fn.name}$state"
    basic_blocks = __create_basic_blocks(after_tail, state_name)

    # Functions with at most one block (no non-tail calls) need only
    # their return type adjusted (or kept as-is if it stays pointer-typed).
    if len(basic_blocks) < 2:
        simple = dataclasses.replace(
            after_tail, result=wrap_return_type(fn.result),
            ops=tuple(__convert_returns_for_hot_path(after_tail.ops, fn.result)))
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

    # Stub only when a PARK SITE lies inside a loop as well as the body being
    # large: a straight-line body runs once and the linear launch completes it
    # synchronously with no state/task allocation at all — the stub would pay
    # that on every call. A body that parks INSIDE a loop lives in the machine
    # anyway, so the duplicated launch body is pure size. A back edge alone is
    # NOT enough: a compute-only loop (hash6's MD5 rounds after -O3 inlining)
    # never parks at runtime, and stubbing it turns a zero-allocation call
    # into a heap state allocation per call — measured on the bootstrap
    # self-compile as 2.9x page allocations and 2.3x wall.
    def has_parking_loop(ops) -> bool:
        # park ops = exactly what __create_basic_blocks splits on
        park_prefix = [0]
        for op in ops:
            is_park = ((isinstance(op, Call) and op.may_suspend)
                       or isinstance(op, Await))
            park_prefix.append(park_prefix[-1] + (1 if is_park else 0))
        label_at: dict[str, int] = {}
        for i, op in enumerate(ops):
            if isinstance(op, Label):
                label_at[op.name] = i
                continue
            for tname in op.branch_targets():
                j = label_at.get(tname)
                # Back edge (target already seen) whose span contains a park.
                if j is not None and park_prefix[i + 1] - park_prefix[j] > 0:
                    return True
        return False

    # A stub defers ALL work to the state machine + state object, so it only
    # applies to functions that HAVE them: never a sync function (no
    # suspensions → no machine → nothing to duplicate, so the code-size
    # rationale doesn't even arise). Large + park-in-loop + genuinely-async.
    use_stub = (_STUB_ENABLED and not fn.sync
                and len(sm_fn.ops) > _STUB_THRESHOLD_OPS
                and has_parking_loop(sm_fn.ops))
    if use_stub:
        layout = __augment_layout_with_params(layout, fn.params)
        hot_fn = __create_stub_launch_func(after_tail, state_name,
                                            task_subtype_name, layout,
                                            entry_idx=len(sm_basic_blocks))
    else:
        hot_fn = __create_hot_path_func(after_tail, state_name,
                                         task_subtype_name, basic_blocks, layout)

    if fn.sync:
        # Sync function: $asynccommon aborts; no state machine, no state object.
        return {hot_fn.name: hot_fn}, {}

    # sm_fn / sm_basic_blocks (and the shared frame layout) were computed above so
    # the hot path and state machine agree on the frame layout. The state-machine
    # view re-expands musttail Calls to Call+Return so the existing terminal-Return
    # → task_complete logic fires; the hot path keeps the musttail.
    state_obj  = __create_state_object(sm_fn, state_name, layout)
    machine_fn = __create_state_machine_func(sm_fn, state_name,
                                              task_subtype_name, sm_basic_blocks, layout,
                                              with_entry_case=use_stub)
    return {hot_fn.name: hot_fn, machine_fn.name: machine_fn}, {state_obj.name: state_obj}


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


def __zero_init_unwritten_saves(fn: Function) -> Function:
    """Aggressive IR inlining (-O3) can place a suspension inside a loop
    whose body defines a live range crossing the back-edge: the state-save
    at the suspension then reads the variable BEFORE any write on the
    first-iteration path (it holds a real value only from iteration two).
    The value saved on that first pass is never consumed — but saving
    indeterminate memory is still wrong, and uninit_check rightly rejects
    it. Zero-init exactly those variables at entry so every save stores a
    DEFINED value. Only STATE-SAVE Moves are repaired — a general repair
    would mask the real read-before-write bugs the checker exists for."""
    from lowering.uninit_check import compute_entry_sets
    entry = compute_entry_sets(fn)
    offenders: dict[str, Type] = {}
    for i, op in enumerate(fn.ops):
        e = entry[i]
        if e is None or not isinstance(op, Move):
            continue
        tgt, src = op.target, op.source
        if (isinstance(tgt, ObjectField) and isinstance(tgt.pointer, StackVar)
                and tgt.pointer.name == "$state" and isinstance(src, StackVar)
                and src.name not in e):
            offenders[src.name] = src.get_type()
    if not offenders:
        return fn
    inits = tuple(Move(StackVar(t, name), __zero_val(t))
                  for name, t in sorted(offenders.items()))
    return dataclasses.replace(fn, ops=inits + tuple(fn.ops))


def __without_saved_vars(fn: Function) -> Function:
    """`saved_vars` is this pass's liveness, a live-out on EVERY op, not a save.
    Once lowered, what a suspension saves is an explicit store into the state
    object, so the sets mean nothing further — and read as saves they made a
    construction's first store publish its own object (lowering/fast_stores.py)."""
    if not any(op.saved_vars for op in fn.ops):
        return fn
    return dataclasses.replace(fn, ops=tuple(
        dataclasses.replace(op, saved_vars=frozenset()) if op.saved_vars else op
        for op in fn.ops))


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def lower_async(app: Application) -> Application:
    results = [__convert_function_to_task_convention(fn)
               for fn in app.functions.values()]

    new_functions = reduce(lambda acc, v: acc | v[0], results, {})
    new_functions = {n: __without_saved_vars(__zero_init_unwritten_saves(f))
                     for n, f in new_functions.items()}
    new_objects   = reduce(lambda acc, v: acc | v[1], results, {}) | app.objects

    # Add task-subtype objects (after conversion so return types are finalised).
    # The dict union `task_subtypes | tmp_app.objects` lets `tmp_app.objects`
    # win on key collisions.
    tmp_app = dataclasses.replace(app, functions=new_functions, objects=new_objects)
    task_subtypes = collect_task_subtypes(tmp_app)

    return dataclasses.replace(tmp_app,
                               objects=task_subtypes | tmp_app.objects)
