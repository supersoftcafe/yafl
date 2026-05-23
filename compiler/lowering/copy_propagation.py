"""Copy propagation: when `Move(M, S)` is immediately followed by an op
that uses `M`, and `M` is otherwise unused, substitute `S` for `M` in that
op and drop the `Move`.

This collapses bookkeeping patterns the upstream code introduces — most
importantly the ternary / match join `Move(result_var, branch_result)`
preceding a `Return(result_var)`, which becomes `Return(branch_result)`.
With that fold, the per-branch shape becomes `Call(register=R); Return(R)`,
which `__discover_tail_calls` already recognises as musttail.

Conservative rules:

  - The Move's target `M` must be a StackVar.
  - The Move's source `S` must also be a StackVar. Substituting a non-LParam
    (NullPointer, Invoke, etc.) is unsafe because `replace_params` walks both
    read and write positions of the next op — if `M` happens to appear as an
    LParam there, propagating an RParam-only value into that slot is a type
    error.
  - The immediately-following op must read `M`.
  - We do not propagate across labels — a control-flow merge could see `M`
    carrying a different value on another edge.
  - We substitute `S` for `M` in the next op whenever it reads `M`. The
    substitution itself is always safe: the read becomes a read of `S`, and
    the Move's value of `M` remains available for any other reader.
  - We drop the Move only when `M`'s total read count was exactly 1 — the
    substituted read was the only one. Multi-reader cases keep the Move so
    other paths still see `M` defined. (Cross-branch / cross-Return cases
    where the Move is locally dead but globally counted as multi-read are
    deliberately left alone — turning those into real drop-safe analysis
    would require reaching-definitions, and the safer rule still catches
    enough single-use cases to make the simple `Move(M, R); Return(M)`
    → `Return(R)` collapse fire wherever it matters.)

Iterates to a fixed point so chains (a Move feeding a Move feeding a Return)
collapse one hop at a time.
"""
from __future__ import annotations

import dataclasses

from codegen.gen import Application
from codegen.things import Function
from codegen.ops import Op, Move, Label, Return, ReturnVoid
from codegen.param import StackVar, RParam


def __count_reads(ops: tuple[Op, ...]) -> dict[str, int]:
    """For each StackVar name, count how many times any op reads it."""
    counts: dict[str, int] = {}
    for op in ops:
        reads, _ = op.get_live_vars()
        for sv in reads:
            counts[sv.name] = counts.get(sv.name, 0) + 1
    return counts


def __propagate_once(fn: Function) -> Function:
    read_counts = __count_reads(fn.ops)
    ops = fn.ops
    new_ops: list[Op] = []
    skip_next = False
    changed = False

    for i, op in enumerate(ops):
        if skip_next:
            skip_next = False
            continue

        if (isinstance(op, Move)
                and isinstance(op.target, StackVar)
                and isinstance(op.source, StackVar)
                and i + 1 < len(ops)
                and not isinstance(ops[i + 1], Label)):
            m_name = op.target.name
            nxt = ops[i + 1]
            nxt_reads, _ = nxt.get_live_vars()
            reads_m = any(sv.name == m_name for sv in nxt_reads)
            if reads_m:
                source = op.source
                def replacer(p: RParam, m=m_name, s=source) -> RParam:
                    if isinstance(p, StackVar) and p.name == m:
                        return s
                    return p
                substituted = nxt.replace_params(replacer)
                if read_counts.get(m_name, 0) == 1:
                    # M's only read was the one we just substituted — drop
                    # the Move entirely.
                    new_ops.append(substituted)
                else:
                    # Other readers of M exist elsewhere; keep the Move so
                    # those reads still find M defined.
                    new_ops.append(op)
                    new_ops.append(substituted)
                skip_next = True
                changed = True
                continue

        new_ops.append(op)

    if not changed:
        return fn

    new_ops_t = tuple(new_ops)

    # Drop any stack_var declarations that are no longer referenced.
    mentioned: set[str] = set()
    for op in new_ops_t:
        r, w = op.get_live_vars()
        mentioned.update(sv.name for sv in r | w)

    new_stack_vars = dataclasses.replace(
        fn.stack_vars,
        fields=tuple((n, t) for n, t in fn.stack_vars.fields if n in mentioned))

    return dataclasses.replace(fn, ops=new_ops_t, stack_vars=new_stack_vars)


def __propagate_copies_fn(fn: Function) -> Function:
    while True:
        new_fn = __propagate_once(fn)
        if new_fn is fn:
            return fn
        fn = new_fn


def propagate_copies(app: Application) -> Application:
    """Apply copy propagation to every function in the application."""
    return dataclasses.replace(
        app,
        functions={name: __propagate_copies_fn(fn) for name, fn in app.functions.items()})
