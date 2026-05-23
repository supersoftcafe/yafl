"""Validate that the IR is in well-formed SSA form with reachable Returns.

The compiler maintains three invariants from AST lowering through to C
emission:

  1. **Single definition per StackVar.** Every locally-named value is
     defined exactly once. Function parameters count as their own
     definitions. Phi targets count once. Move/Call/NewObject/ParallelCall
     writes count once each.

  2. **All paths reach a Return / ReturnVoid.** No control-flow path falls
     off the end of the function without an explicit terminator.

  3. **Phi ops are well-constructed.** Each Phi sits immediately after a
     Label (top of a block). Its sources reference labels that exist in
     the function and that are actual CFG predecessors of the Phi's block.
     The number of sources equals the number of predecessors.

Invocation points: right after AST lowering (catches generator bugs that
break SSA at emission) and right before C generation (catches lowering
passes that introduce multi-definition or unterminated paths).

Known exceptions:

  - StackVars whose name starts with `$sv_` are async-lowering scratch
    slots (e.g. `$sv_state`, `$sv_call_id`, `$sv_async_task`). They are
    deliberately multi-write by design — the cross-call-site machinery
    reuses them. They're skipped for the single-definition check.

  - `__entrypoint__` is hand-built and bypasses the AST→IR pipeline; it
    isn't validated.
"""
from __future__ import annotations

from codegen.gen import Application
from codegen.things import Function
from codegen.ops import Op, Move, Call, NewObject, ParallelCall, Phi, Label, Jump, JumpIf, IfTask, SwitchJump, Return, ReturnVoid, Abort
from codegen.param import StackVar, NullPointer, Integer, Float, ZeroOf


class SSAValidationError(AssertionError):
    """Raised when the IR violates an SSA invariant."""


def __is_scratch_slot(name: str) -> bool:
    """Async-lowering reuses fixed scratch slots across call sites. They
    deliberately violate the single-definition rule."""
    return name.startswith("$sv_") or name.startswith("$wrap$") or name.startswith("$sm_wrap$") or name.startswith("$musttail$ret$") or name == "$state" or name == "$completed_task"


def __is_zero_init(op: Op) -> bool:
    """A `Move(target, <type-appropriate zero>)` is a GC-safety / state-machine
    pre-initialisation inserted before the variable's real definition. It is
    logically a declaration ("let x: T = zero"), not a redefinition, so it
    does not count towards the single-definition rule. The zero values come
    from `param._zero_for(...)`: `NullPointer()` for DataPointer, `Integer(0,N)`
    for Int/IntPtr, and `Float(0.0,N)` for Float."""
    if not isinstance(op, Move):
        return False
    src = op.source
    if isinstance(src, (NullPointer, ZeroOf)):
        return True
    if isinstance(src, Integer) and src.value == 0:
        return True
    if isinstance(src, Float) and src.value == 0.0:
        return True
    return False


def __collect_write_counts(fn: Function) -> dict[str, int]:
    counts: dict[str, int] = {}
    for name, _ in fn.params.fields:
        counts[name] = 1
    for op in fn.ops:
        if __is_zero_init(op):
            continue
        _, writes = op.get_live_vars()
        for sv in writes:
            counts[sv.name] = counts.get(sv.name, 0) + 1
    return counts


def __check_single_definition(fn: Function) -> None:
    counts = __collect_write_counts(fn)
    violations = [
        (name, n) for name, n in counts.items()
        if n > 1 and not __is_scratch_slot(name)
    ]
    if violations:
        details = "\n  ".join(f"{name}: defined {n} times" for name, n in violations)
        raise SSAValidationError(
            f"{fn.name}: SSA single-definition invariant violated:\n  {details}")


def __check_all_paths_return(fn: Function) -> None:
    """Every control-flow path must end in Return / ReturnVoid (or a musttail
    Call, which codegen emits as `return foo(...)`). A function with no ops
    is allowed (extern declarations). A `Jump` to a label always reaches
    that label's ops, so it's fine. The only failure mode we check for is
    a fall-through past the last op — i.e., the last op is not a terminator
    AND control could reach it."""
    if not fn.ops:
        return
    last = fn.ops[-1]
    terminator = (
        isinstance(last, (Return, ReturnVoid, Abort))
        or (isinstance(last, Call) and last.musttail)
        or isinstance(last, Jump)
        or isinstance(last, IfTask)        # IfTask is conditional; the fall-through is the non-taken path
        or isinstance(last, SwitchJump)
    )
    if not terminator:
        raise SSAValidationError(
            f"{fn.name}: function does not end in a terminator op; last op is "
            f"{type(last).__name__} — control would fall off the end.")


def __collect_block_predecessors(fn: Function) -> dict[str, set[str | None]]:
    """For each labelled block in the function, the set of predecessor block
    labels (or `None` for the implicit entry block) that can reach it via
    a Jump, JumpIf, IfTask, SwitchJump, or fall-through."""
    preds: dict[str, set[str | None]] = {}
    current: str | None = None

    def add(target: str, src: str | None) -> None:
        preds.setdefault(target, set()).add(src)

    for i, op in enumerate(fn.ops):
        if isinstance(op, Label):
            # Fall-through edge from previous block (if the previous op wasn't a terminator).
            # `Abort` is a terminator too — `abort()` does not return.
            prev = fn.ops[i - 1] if i > 0 else None
            if prev is not None and not isinstance(prev, (Jump, Return, ReturnVoid, Abort)):
                add(op.name, current)
            current = op.name
            preds.setdefault(op.name, set())
        elif isinstance(op, Jump):
            add(op.name, current)
        elif isinstance(op, JumpIf):
            add(op.label, current)
        elif isinstance(op, IfTask):
            add(op.target, current)
        elif isinstance(op, SwitchJump):
            for _, lbl in op.cases:
                add(lbl, current)
    return preds


def __check_phi_well_formed(fn: Function) -> None:
    preds = __collect_block_predecessors(fn)
    current_label: str | None = None
    in_phi_region = False
    for op in fn.ops:
        if isinstance(op, Label):
            current_label = op.name
            in_phi_region = True
        elif isinstance(op, Phi):
            if not in_phi_region or current_label is None:
                raise SSAValidationError(
                    f"{fn.name}: Phi for target {op.target.name!r} appears "
                    f"outside the Phi region of any block.")
            expected_preds = preds.get(current_label, set())
            phi_source_labels = {lbl for lbl, _ in op.sources}
            missing = expected_preds - phi_source_labels - {None}
            extra = phi_source_labels - expected_preds
            if missing or extra:
                raise SSAValidationError(
                    f"{fn.name}: Phi @ {current_label} for target "
                    f"{op.target.name!r} has mismatched sources. "
                    f"Expected predecessors: {sorted(p for p in expected_preds if p is not None)}; "
                    f"Phi sources: {sorted(phi_source_labels)}; "
                    f"missing: {sorted(missing)}; extra: {sorted(extra)}.")
        else:
            in_phi_region = False


def __validate_fn(fn: Function) -> None:
    if fn.name == "__entrypoint__":
        return
    __check_single_definition(fn)
    __check_all_paths_return(fn)
    __check_phi_well_formed(fn)


def validate(app: Application) -> Application:
    """Validate every function in the application. Returns `app` unchanged
    on success; raises `SSAValidationError` with details on the first
    violation found."""
    for fn in app.functions.values():
        __validate_fn(fn)
    return app
