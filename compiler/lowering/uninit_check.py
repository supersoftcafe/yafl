"""Validate that every StackVar read is preceded by a write on every
reachable path.  Runs after all lowering as a codegen-correctness check.

The analysis is standard definite-assignment: a forward data-flow over the
function's control-flow graph where the lattice element at each program
point is the set of StackVar names that are *definitely* initialised on
every path reaching that point.  The meet operator at join points (Labels
reached from multiple predecessors) is intersection.  An op that reads a
StackVar not in its entry set is a bug — either in the lowering that
produced the IR, or in this pass's CFG model.

Keyed by variable name (not StackVar identity) because the lowering can
produce multiple StackVars with the same name but different IR types —
they compile to the same C storage, so "initialised" tracks the C
variable.
"""

from __future__ import annotations

from codegen.ops import (
    Op, Label, Move, Jump, JumpIf, SwitchJump, IfTask, NewObject,
    Call, Return, ReturnVoid, Abort,
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


def _reads_writes(op: Op) -> tuple[frozenset[str], frozenset[str]]:
    """Return (read_names, written_names) for a single op."""
    reads, writes = op.get_live_vars()

    # Op.get_live_vars() does not report IfTask's task_lhs / call_id_lhs
    # writes because IfTask is a conditional jump and the writes only land
    # on the jumped-to branch.  We conservatively treat them as writes on
    # that branch by noting them here; the caller handles the branch split.
    taken_writes: frozenset[StackVar] = frozenset()
    if isinstance(op, IfTask):
        taken = set()
        if isinstance(op.task_lhs, StackVar):
            taken.add(op.task_lhs)
        if isinstance(op.call_id_lhs, StackVar):
            taken.add(op.call_id_lhs)
        taken_writes = frozenset(taken)

    r_names = frozenset(v.name for v in reads)
    w_names = frozenset(v.name for v in writes) | frozenset(v.name for v in taken_writes)
    return r_names, w_names


def _iftask_taken_writes(op: IfTask) -> frozenset[str]:
    """Subset of writes that only happen on the branch taken."""
    s = set()
    if isinstance(op.task_lhs, StackVar):
        s.add(op.task_lhs.name)
    if isinstance(op.call_id_lhs, StackVar):
        s.add(op.call_id_lhs.name)
    return frozenset(s)


def check_function(fn: Function) -> None:
    """Raise UninitialisedReadError if any StackVar read could happen on a
    path where the variable has not been written.

    Parameters are treated as initialised on entry.  Unreachable ops are
    skipped.
    """
    ops = fn.ops
    n = len(ops)
    if n == 0:
        return

    labels = _build_label_index(ops)
    params: frozenset[str] = frozenset(name for name, _ in fn.params.fields)

    # entry[i] = set of var names definitely initialised on entry to ops[i];
    # None means "not reached yet" during fixpoint iteration.
    entry: list[frozenset[str] | None] = [None] * n
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
                f"  needs    : {sorted(reads)}\n"
                f"  init set : {sorted(e)}\n"
                f"  missing  : {sorted(missing)}\n"
                f"This is a codegen bug — either the lowering produced a read-"
                f"before-write, or the variable should have been promoted to "
                f"the task-heap state object.")


def check_application(app: Application) -> None:
    """Validate every compiled function in the application."""
    for fn in app.functions.values():
        if getattr(fn, "foreign_symbol", None):
            continue  # extern declarations have no ops to check
        check_function(fn)
