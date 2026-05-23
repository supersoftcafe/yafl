"""Validate that every StackVar read is preceded by a write on every
reachable path.  Runs after all lowering as a codegen-correctness check.

The analysis is standard definite-assignment: a forward data-flow over the
function's control-flow graph where the lattice element at each program
point is the set of StackVars that are *definitely* initialised on every
path reaching that point.  The meet operator at join points (Labels
reached from multiple predecessors) is intersection.  An op that reads a
StackVar not in its entry set is a bug — either in the lowering that
produced the IR, or in this pass's CFG model.
"""

from __future__ import annotations

from codegen.ops import (
    Op, Label, Move, Jump, JumpIf, SwitchJump, IfTask, NewObject,
    Call, Return, ReturnVoid, Abort, Phi,
)
from codegen.param import StackVar
from codegen.things import Function
from codegen.gen import Application


class UninitialisedReadError(Exception):
    """Raised when a StackVar is read before every path writes it.
    Always indicates a codegen bug."""


def _build_label_index(ops: tuple[Op, ...]) -> dict[str, int]:
    return {op.name: i for i, op in enumerate(ops) if isinstance(op, Label)}


def _successors(ops: tuple[Op, ...], labels: dict[str, int], i: int) -> list[int]:
    op = ops[i]
    n = len(ops)
    if isinstance(op, (Return, ReturnVoid, Abort)):
        return []
    if isinstance(op, Call) and op.musttail:
        return []
    if isinstance(op, Jump):
        return [labels[op.name]] if op.name in labels else []
    if isinstance(op, JumpIf):
        succs: list[int] = []
        if op.label in labels:
            succs.append(labels[op.label])
        if i + 1 < n:
            succs.append(i + 1)
        return succs
    if isinstance(op, IfTask):
        succs = []
        if op.target in labels:
            succs.append(labels[op.target])
        if i + 1 < n:
            succs.append(i + 1)
        return succs
    if isinstance(op, SwitchJump):
        # Codegen emits `default: abort()` so unlisted values never fall
        # through.  Successors are exactly the labelled cases.
        return [labels[lbl] for _, lbl in op.cases if lbl in labels]
    # All other ops fall through to the next index.
    return [i + 1] if i + 1 < n else []


def _reads_writes(op: Op) -> tuple[frozenset[StackVar], frozenset[StackVar]]:
    """Return (reads, writes) for a single op."""
    if isinstance(op, Phi):
        # Phi sources are conditional reads on their predecessor edges, not
        # unconditional reads at the Phi's location. The per-edge verification
        # in `_check_phi_sources` catches a genuinely uninitialised source.
        # The target is written when the block is entered.
        writes = frozenset({op.target}) if isinstance(op.target, StackVar) else frozenset()
        return frozenset(), writes

    reads, writes = op.get_live_vars()

    # Op.get_live_vars() does not report IfTask's task_lhs / call_id_lhs
    # writes because IfTask is a conditional jump and the writes only land
    # on the jumped-to branch.  We conservatively treat them as writes on
    # that branch by noting them here; the caller handles the branch split.
    if isinstance(op, IfTask):
        taken: set[StackVar] = set()
        if isinstance(op.task_lhs, StackVar):
            taken.add(op.task_lhs)
        if isinstance(op.call_id_lhs, StackVar):
            taken.add(op.call_id_lhs)
        writes = writes | frozenset(taken)

    return reads, writes


def _iftask_taken_writes(op: IfTask) -> frozenset[StackVar]:
    """Subset of writes that only happen on the branch taken."""
    s: set[StackVar] = set()
    if isinstance(op.task_lhs, StackVar):
        s.add(op.task_lhs)
    if isinstance(op.call_id_lhs, StackVar):
        s.add(op.call_id_lhs)
    return frozenset(s)


def check_function(fn: Function) -> None:
    """Raise UninitialisedReadError if any StackVar read could happen on a
    path where the variable has not been written.

    Parameters are treated as initialised on entry.  Unreachable ops are
    skipped.

    Phi ops are special: each source is consumed only on the edge from its
    labelled predecessor, not at the Phi's location.  The standard data-
    flow models the Phi as zero unconditional reads + a single write of
    the target; a separate per-edge pass below checks each source against
    its predecessor's exit set so a genuine "source uninitialised on its
    edge" bug is still caught.
    """
    ops = fn.ops
    n = len(ops)
    if n == 0:
        return

    labels = _build_label_index(ops)
    params: frozenset[StackVar] = frozenset(StackVar(typ, name) for name, typ in fn.params.fields)

    # entry[i] = set of StackVars definitely initialised on entry to ops[i];
    # None means "not reached yet" during fixpoint iteration.
    entry: list[frozenset[StackVar] | None] = [None] * n
    entry[0] = params

    worklist: list[int] = [0]
    while worklist:
        i = worklist.pop()
        e = entry[i]
        if e is None:
            continue
        op = ops[i]
        reads, writes = _reads_writes(op)

        # IfTask writes task_lhs/call_id_lhs *only* on the jumped-to branch;
        # fall-through does not see them as initialised.
        if isinstance(op, IfTask):
            branch_only = _iftask_taken_writes(op)
            fallthrough_writes = writes - branch_only
            branch_writes = writes
        else:
            branch_only = frozenset()
            fallthrough_writes = writes
            branch_writes = writes

        exit_fallthrough = e | fallthrough_writes
        exit_branch = e | branch_writes

        for succ in _successors(ops, labels, i):
            # JumpIf/IfTask: first successor listed is the taken label;
            # then fall-through.  SwitchJump: every listed case is a
            # "branch", fall-through is the trailing unmatched case.
            is_branch_target = False
            if isinstance(op, (JumpIf, IfTask)):
                target_label = op.label if isinstance(op, JumpIf) else op.target
                is_branch_target = (target_label in labels
                                    and labels[target_label] == succ)
            elif isinstance(op, SwitchJump):
                is_branch_target = any(labels.get(lbl) == succ for _, lbl in op.cases)

            incoming = exit_branch if is_branch_target else exit_fallthrough

            old = entry[succ]
            new = incoming if old is None else (old & incoming)
            if new != old:
                entry[succ] = new
                worklist.append(succ)

    # Verification pass — independent of fixpoint iteration so errors are
    # reported once the analysis has stabilised.
    for i, op in enumerate(ops):
        e = entry[i]
        if e is None:
            continue  # unreachable
        reads, _ = _reads_writes(op)
        missing = reads - e
        if missing:
            raise UninitialisedReadError(
                f"uninitialised StackVar read in function {fn.name!r} at op #{i}:\n"
                f"  op       : {op!r}\n"
                f"  needs    : {sorted(reads, key=lambda v: v.name)}\n"
                f"  init set : {sorted(e, key=lambda v: v.name)}\n"
                f"  missing  : {sorted(missing, key=lambda v: v.name)}\n"
                f"This is a codegen bug — either the lowering produced a read-"
                f"before-write, or the variable should have been promoted to "
                f"the task-heap state object.")

    # Per-edge Phi verification. Each Phi source is consumed on the edge
    # from its labelled predecessor; the source's reads must be in that
    # predecessor's exit set at the point control leaves for the Phi
    # block.
    _check_phi_sources(fn, ops, labels, entry)


def _check_phi_sources(
    fn: Function,
    ops: tuple[Op, ...],
    labels: dict[str, int],
    entry: list[frozenset[StackVar] | None],
) -> None:
    """For each Phi source (P_label, source), verify `source`'s reads are
    defined in the exit set of every edge from block P_label into the
    Phi's block."""
    # Index Phi ops by their enclosing block label (most recent Label).
    phi_ops_by_block: dict[str, list[Phi]] = {}
    current_block: str | None = None
    for op in ops:
        if isinstance(op, Label):
            current_block = op.name
        elif isinstance(op, Phi) and current_block is not None:
            phi_ops_by_block.setdefault(current_block, []).append(op)
    if not phi_ops_by_block:
        return

    # Collect every edge from a labelled block into a Phi block:
    # list of (predecessor_label, phi_block_label, exit-set-at-transfer).
    edges: list[tuple[str, str, frozenset[StackVar]]] = []
    current_block = None
    for i, op in enumerate(ops):
        e = entry[i]
        if isinstance(op, Label):
            # Fall-through edge to a new block. The previous op (if any)
            # transferred control here if it wasn't a terminator. The
            # exit set at that transfer is entry[i-1] | writes(prev).
            if op.name in phi_ops_by_block and current_block is not None and i > 0:
                prev = ops[i - 1]
                if not isinstance(prev, (Jump, Return, ReturnVoid, Abort)):
                    if not (isinstance(prev, Call) and prev.musttail):
                        prev_e = entry[i - 1]
                        if prev_e is not None:
                            _, prev_writes = _reads_writes(prev)
                            edges.append((current_block, op.name, prev_e | prev_writes))
            current_block = op.name
            continue
        if e is None or current_block is None:
            continue
        _, writes = _reads_writes(op)
        exit_here = e | writes
        if isinstance(op, Jump) and op.name in phi_ops_by_block:
            edges.append((current_block, op.name, exit_here))
        elif isinstance(op, JumpIf) and op.label in phi_ops_by_block:
            edges.append((current_block, op.label, exit_here))
        elif isinstance(op, IfTask) and op.target in phi_ops_by_block:
            edges.append((current_block, op.target, exit_here))
        elif isinstance(op, SwitchJump):
            for _, lbl in op.cases:
                if lbl in phi_ops_by_block:
                    edges.append((current_block, lbl, exit_here))

    # For every edge into a Phi block, check the Phi source whose label
    # matches this predecessor is fully defined.
    for pred_label, phi_block, pred_exit in edges:
        for phi in phi_ops_by_block[phi_block]:
            for source_label, source in phi.sources:
                if source_label != pred_label:
                    continue
                needed = source.get_live_vars()
                missing = needed - pred_exit
                if missing:
                    raise UninitialisedReadError(
                        f"uninitialised StackVar read in function {fn.name!r}: "
                        f"Phi at block {phi_block!r}, source from predecessor "
                        f"{pred_label!r}:\n"
                        f"  phi      : {phi!r}\n"
                        f"  source   : {source!r}\n"
                        f"  needs    : {sorted(needed, key=lambda v: v.name)}\n"
                        f"  exit set : {sorted(pred_exit, key=lambda v: v.name)}\n"
                        f"  missing  : {sorted(missing, key=lambda v: v.name)}\n"
                        f"This is a codegen bug — the Phi source is read on "
                        f"the edge from this predecessor but isn't defined "
                        f"there.")


def check_application(app: Application) -> None:
    """Validate every compiled function in the application."""
    for fn in app.functions.values():
        if getattr(fn, "foreign_symbol", None):
            continue  # extern declarations have no ops to check
        check_function(fn)
