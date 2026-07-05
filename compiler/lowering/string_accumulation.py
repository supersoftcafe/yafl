"""Deforest string accumulation loops into in-place builder writes.

The naive way to build a string in a loop — `go(acc + x, …)` through a
`[tail]` call — is O(n²): every iteration copies the whole accumulator into a
fresh string. The stdlib's StringBuilder exists to avoid that, but users
shouldn't need to know it for the common case. This stage rewrites the
pattern automatically.

At the IR level (post tail_loop) the pattern is a loop-carried Phi:

    A   = Phi[(entry, init), (backedge, B)]
    ...
    B   = string_append(A, x)          # or a concat_n rooted at A

The rewrite replaces the String accumulator with two loop-carried variables —
a heap buffer and a byte offset — appended in place:

    buf = Phi[(entry, init),        (backedge, buf')]
    off = Phi[(entry, length(init)), (backedge, off')]
    ...
    buf' = string_copy_to_dangerously(
               string_builder_reserve(buf, off, length(x)), off, x)
    off' = integer_add(off, length(x))

`string_builder_reserve` (yafllib/string.c) hides the growth branch and
heapifies a packed init, so the rewrite adds no control flow. Every OTHER
read of `A` — loop exits, mid-loop uses, saved values — becomes
`string_resize(buf, off)`: an exact-size snapshot copy, which is a correct
immutable string at ANY point of the accumulation (the buffer is exclusively
owned by the introduced variables, and a snapshot never aliases it). One
snapshot at the exit is exactly the stdlib toString; this is why reads never
block the rewrite — only the shape of the push chain can.

Bail-out rules (all conservative, all per-Phi):
  - at least one step edge (a source whose value chases to an append/concat_n
    whose LEFT-spine root is A) and at least one init edge;
  - within a step chain, A is read exactly once (the root) — `acc + acc`
    self-append disqualifies;
  - pushed operands and init values are DUPLICABLE (they are evaluated in
    both the buf and off computations);
  - chain intermediates and the step result B are read only by the chain and
    the Phi (`saved_vars` count as reads via ssa_defs.read_counts, so a value
    the async state machine will save is never absorbed);
  - `A` itself may appear in `saved_vars`: those entries are remapped to
    {buf, off}.

Runs in the pre-async fixpoint at -O1+ AFTER string_concat, which flattens
multi-append steps into a single concat_n so one recogniser shape covers
`acc + a + b + c`. Idempotent: rewritten loops contain no appends rooted at a
Phi'd string.
"""
from __future__ import annotations

import dataclasses

from codegen.gen import Application
from codegen.ops import Op, Move, Phi, Label, Jump, JumpIf
from codegen.param import RParam, StackVar, NewStruct, RuntimeInvoke
from codegen.typedecl import DataPointer, Struct
from lowering.ssa_defs import DUPLICABLE, single_defs, read_counts

_APPEND = "string_append"
_CONCAT_N = "string_concat_n"


def _invoke(function: str, *args: RParam) -> RuntimeInvoke:
    fields = tuple((f"a{i}", v) for i, v in enumerate(args))
    return RuntimeInvoke(function, NewStruct(fields), DataPointer())


def _length_of(value: RParam) -> RParam:
    return _invoke("string_length_int", value)


@dataclasses.dataclass
class _Step:
    """One back-edge's recognised push chain."""
    edge_label: str
    result_name: str            # B: the Phi-source var the chain defines
    pushes: list[RParam]        # operands appended to A, in order
    chain_moves: set[str]       # Move targets the chain runs through (drop)


def _operands_of(invoke: RuntimeInvoke) -> list[RParam] | None:
    """The ordered operand list of an append/concat_n invoke, else None."""
    if not isinstance(invoke.parameters, NewStruct):
        return None
    values = [v for fname, v in invoke.parameters.values if fname != "count"]
    if invoke.function == _APPEND and len(values) == 2:
        return values
    if invoke.function == _CONCAT_N:
        return values
    return None


def _recognise_step(edge_label: str, source: RParam, acc: str,
                    defs, reads) -> _Step | None:
    """Chase a Phi source to an append/concat_n chain left-rooted at `acc`."""
    chain_moves: set[str] = set()

    # The Phi source itself must be a single-read var defined by the chain's
    # final invoke (Phi counts as its one read).
    if not (isinstance(source, StackVar) and reads.get(source.name) == 1):
        return None
    result_name = source.name

    def flatten(param: RParam) -> list[RParam] | None:
        """Operand spine of the append tree at `param`; None = not a chain."""
        if isinstance(param, RuntimeInvoke):
            ops = _operands_of(param)
            if ops is not None:
                left = flatten(ops[0])
                if left is None:
                    return None
                return left + ops[1:]
        if isinstance(param, StackVar):
            if param.name == acc:
                return [param]
            if reads.get(param.name) == 1:
                inner = defs.get(param.name)
                if inner is not None:
                    deeper = flatten(inner)
                    if deeper is not None:
                        chain_moves.add(param.name)
                        return deeper
        return None

    root_def = defs.get(result_name)
    if root_def is None:
        return None
    spine = flatten(root_def)
    if spine is None or len(spine) < 2:
        return None
    root, pushes = spine[0], spine[1:]
    if not (isinstance(root, StackVar) and root.name == acc):
        return None
    # A must be read exactly once (the root); an operand that is or contains
    # A would alias the buffer mid-mutation.
    if any(p.test(lambda q: isinstance(q, StackVar) and q.name == acc) for p in pushes):
        return None
    if not all(isinstance(p, DUPLICABLE) for p in pushes):
        return None
    chain_moves.add(result_name)
    return _Step(edge_label, result_name, pushes, chain_moves)


def deforest_string_accumulation(app: Application) -> Application:
    new_functions = {}
    for fn_name, fn in app.functions.items():
        defs = single_defs(fn)
        reads = read_counts(fn)

        # ── recognise: one accumulator Phi at a time (fixpoint reruns us) ──
        plan = None
        for op in fn.ops:
            if not (isinstance(op, Phi) and isinstance(op.target, StackVar)):
                continue
            acc = op.target.name
            steps: list[_Step] = []
            inits: list[tuple[str, RParam]] = []
            for label, value in op.sources:
                step = _recognise_step(label, value, acc, defs, reads)
                if step is not None:
                    steps.append(step)
                else:
                    inits.append((label, value))
            if steps and inits and all(isinstance(v, DUPLICABLE) for _, v in inits):
                plan = (op, acc, steps, inits)
                break
        if plan is None:
            new_functions[fn_name] = fn
            continue

        phi_op, acc, steps, inits = plan
        buf_name, off_name = f"{acc}$sb_buf", f"{acc}$sb_off"
        buf_var = StackVar(DataPointer(), buf_name)
        off_var = StackVar(DataPointer(), off_name)
        chain_moves = set().union(*(s.chain_moves for s in steps))
        step_by_result = {s.result_name: s for s in steps}

        def snapshot() -> RParam:
            return _invoke("string_resize", buf_var, off_var)

        # A residual read of the accumulator cannot be edited in place —
        # StackVar substitution is LParam-guarded — so each reading op gets a
        # materialised snapshot Move + rename. Phi sources are the exception
        # (their value is consumed on the predecessor edge, where an inserted
        # Move would not execute): a DIRECT acc source takes the snapshot
        # expression itself; an acc buried deeper inside a Phi source has no
        # safe rewrite point, so that pattern bails the whole plan.
        def phi_source_buries_acc(op: Op) -> bool:
            return (isinstance(op, Phi) and op is not phi_op
                    and any(not (isinstance(v, StackVar) and v.name == acc)
                            and v.test(lambda q: isinstance(q, StackVar) and q.name == acc)
                            for _, v in op.sources))

        if any(phi_source_buries_acc(op) for op in fn.ops):
            new_functions[fn_name] = fn
            continue

        # The rewrite wins only when residual reads are OUTSIDE the loop: an
        # in-loop read pays a full snapshot copy every iteration ON TOP of
        # the push — strictly worse than the append it replaced. Loop body ≈
        # the op span from the accumulator's Phi to the last jump back to its
        # label; any acc read in that span (outside the recognised chains)
        # bails the plan. (Found the hard way: the JSON lexer's carry buffer
        # is consumed each iteration — deforesting it doubled the work.)
        ops_list = list(fn.ops)
        phi_idx = ops_list.index(phi_op)
        loop_label = next((op.name for op in reversed(ops_list[:phi_idx])
                           if isinstance(op, Label)), None)
        def jump_target(op: Op) -> str | None:
            if isinstance(op, JumpIf):
                return op.label
            if isinstance(op, Jump):
                return op.name
            return None
        span_end = max((i for i, op in enumerate(ops_list)
                        if jump_target(op) == loop_label),
                       default=phi_idx)
        chain_all = set().union(*(step.chain_moves for step in steps))
        def reads_acc_outside_chain(op: Op) -> bool:
            if isinstance(op, Move) and isinstance(op.target, StackVar) \
                    and op.target.name in chain_all:
                return False
            return any(sv.name == acc for sv in op.get_live_vars()[0])
        if any(reads_acc_outside_chain(ops_list[i])
               for i in range(phi_idx + 1, span_end + 1)):
            new_functions[fn_name] = fn
            continue

        snap_vars: list[StackVar] = []
        new_ops: list[Op] = []
        for op in fn.ops:
            if op is phi_op:
                # The accumulator Phi becomes the (buf, off) Phi pair.
                buf_sources = tuple((lbl, v) for lbl, v in inits) + tuple(
                    (s.edge_label, StackVar(DataPointer(), f"{s.result_name}$sb_buf"))
                    for s in steps)
                off_sources = tuple((lbl, _length_of(v)) for lbl, v in inits) + tuple(
                    (s.edge_label, StackVar(DataPointer(), f"{s.result_name}$sb_off"))
                    for s in steps)
                new_ops.append(Phi(target=buf_var, sources=buf_sources))
                new_ops.append(Phi(target=off_var, sources=off_sources))
                continue
            if isinstance(op, Move) and isinstance(op.target, StackVar):
                if op.target.name in step_by_result:
                    # The chain's final Move becomes the in-place push
                    # sequence: reserve → dangerous copy, then advance the
                    # offset, once per operand.
                    step = step_by_result[op.target.name]
                    cur_buf: RParam = buf_var
                    cur_off: RParam = off_var
                    for i, x in enumerate(step.pushes):
                        last = i == len(step.pushes) - 1
                        nbuf = StackVar(DataPointer(),
                                        f"{step.result_name}$sb_buf" if last
                                        else f"{step.result_name}$sb_buf@{i}")
                        noff = StackVar(DataPointer(),
                                        f"{step.result_name}$sb_off" if last
                                        else f"{step.result_name}$sb_off@{i}")
                        grown = _invoke("string_builder_reserve",
                                        cur_buf, cur_off, _length_of(x))
                        new_ops.append(Move(nbuf, _invoke(
                            "string_copy_to_dangerously", grown, cur_off, x)))
                        new_ops.append(Move(noff, _invoke(
                            "integer_add", cur_off, _length_of(x))))
                        cur_buf, cur_off = nbuf, noff
                    continue
                if op.target.name in chain_moves:
                    continue    # absorbed intermediate
            # Everything else: reads of the accumulator become snapshots, and
            # a saved accumulator becomes a saved (buf, off) pair.
            if isinstance(op, Phi):
                op = dataclasses.replace(op, sources=tuple(
                    (lbl, snapshot() if isinstance(v, StackVar) and v.name == acc else v)
                    for lbl, v in op.sources))
            elif any(sv.name == acc for sv in op.get_live_vars()[0]):
                snap = StackVar(DataPointer(), f"{acc}$snap@{len(snap_vars)}")
                snap_vars.append(snap)
                new_ops.append(Move(snap, snapshot()))
                op = op.rename_vars({acc: snap.name})
            if any(sv.name == acc for sv in op.saved_vars):
                op = dataclasses.replace(op, saved_vars=frozenset(
                    sv for sv in op.saved_vars if sv.name != acc) | {buf_var, off_var})
            new_ops.append(op)

        # Declare the introduced locals; retire the replaced ones (the
        # accumulator, the step results and the absorbed intermediates).
        retired = {acc} | chain_moves
        introduced = [(buf_name, DataPointer()), (off_name, DataPointer())]
        introduced += [(sv.name, DataPointer()) for sv in snap_vars]
        for step in steps:
            for i in range(len(step.pushes)):
                last = i == len(step.pushes) - 1
                suffix = "" if last else f"@{i}"
                introduced.append((f"{step.result_name}$sb_buf{suffix}", DataPointer()))
                introduced.append((f"{step.result_name}$sb_off{suffix}", DataPointer()))
        kept = tuple((n, ty) for n, ty in fn.stack_vars.fields if n not in retired)
        new_stack_vars = Struct(kept + tuple(introduced))
        new_functions[fn_name] = dataclasses.replace(
            fn, ops=tuple(new_ops), stack_vars=new_stack_vars)
    return dataclasses.replace(app, functions=new_functions)
