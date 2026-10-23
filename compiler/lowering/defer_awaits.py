"""Deferred awaits: a call that may suspend is awaited where its result is
used, not where it is made.

The call's result is MARKED: kept in the task-carrying shape the callee
returned, which the collector reads as a reference to the task (`gc_ref`,
yafl.h). A copy or field read of a marked variable is VIRTUAL — the root plus
a field path — and costs nothing, so destructuring a pending tuple waits for
nothing. A Phi with a whole marked value among its sources is a PENDING join:
it joins the pending values, so the join waits for nothing either; its other
sources are wrapped into the same shape. Every other op that reads a marked
variable is preceded by an `Await` of its root, under a fresh name, and by the
projection of each virtual variable it reads, also fresh; the op reads those.
A Phi source that must be realised is realised on its edge, where phi_removal
will place the edge's copy. A Return of a whole marked value of the function's
own result type is not a use: its Await is `returned`, and async lowering's
hot path hands the pending value to the caller as it stands.

Runs in SSA, after sroa and before phi_removal: every name has one definition,
so a virtual variable always stands for the one value its root was given, and
a join is a Phi. A call in literal tail position (`Call(R); Return(R)`) is left
alone — async lowering makes it a tail call, which is better than passing its
task through.
"""
from __future__ import annotations

import dataclasses

from codegen.gen import Application
from codegen.ir import Function
from codegen.ops import Op, Call, Move, Phi, Return, Await, Label, Jump
from codegen.param import RParam, StackVar, StructField
from codegen.typedecl import Struct
from lowering.task_abi import wrap_return_type, wrap_value


def defer_awaits(app: Application) -> Application:
    """Defer the awaits of every function (see the module docstring)."""
    return dataclasses.replace(app, functions={
        name: fn if fn.bypass_async or name == "__entrypoint__" else _defer(fn)
        for name, fn in app.functions.items()})


def _tail_called(ops: tuple[Op, ...], k: int, fn: Function) -> bool:
    """`ops[k]` is a call in literal tail position (async_lower's
    __discover_tail_calls, pattern 1)."""
    op = ops[k]
    nxt = ops[k + 1] if k + 1 < len(ops) else None
    return (isinstance(op, Call) and isinstance(op.register, StackVar)
            and isinstance(nxt, Return) and isinstance(nxt.value, StackVar)
            and nxt.value.name == op.register.name and op.register.get_type() == fn.result)


def _projection(value: RParam) -> tuple[str, tuple[str, ...]] | None:
    path: tuple[str, ...] = ()
    while isinstance(value, StructField):
        path = (value.field,) + path
        value = value.struct
    return (value.name, path) if isinstance(value, StackVar) else None


def _project(root: RParam, path: tuple[str, ...]) -> RParam:
    for f in path:
        root = StructField(root, f)
    return root


def _defer(fn: Function) -> Function:
    ops = fn.ops
    reads: dict[str, int] = {}
    for op in ops:
        for v in op.get_live_vars()[0]:
            reads[v.name] = reads.get(v.name, 0) + 1

    # root name -> pending source; marked name -> (its variable, root, field path)
    roots: dict[str, StackVar] = {}
    marked: dict[str, tuple[StackVar, StackVar, tuple[str, ...]]] = {}

    def add_root(r: StackVar) -> None:
        roots[r.name] = StackVar(wrap_return_type(r.get_type()), f"{r.name}$pending")
        marked[r.name] = (r, r, ())

    for k, op in enumerate(ops):
        if (isinstance(op, Call) and op.may_suspend and isinstance(op.register, StackVar)
                and reads.get(op.register.name, 0) > 0 and not _tail_called(ops, k, fn)):
            add_root(op.register)
    if not roots:
        return fn

    def whole(value: RParam, of: RParam) -> bool:
        """`value` is a whole marked value, of the type of its root and of `of`."""
        if not (isinstance(value, StackVar) and value.name in marked):
            return False
        _, root, path = marked[value.name]
        return path == () and value.get_type() == root.get_type() == of.get_type()

    phis = [op for op in ops if isinstance(op, Phi) and isinstance(op.target, StackVar)]
    virtual: set[int] = set()
    changed = True
    while changed:   # a copy may sit textually before its source's definition
        changed = False
        for k, op in enumerate(ops):
            if (k not in virtual and isinstance(op, Move) and not op.keep
                    and isinstance(op.target, StackVar)
                    and (pr := _projection(op.source)) is not None and pr[0] in marked):
                _, root, path = marked[pr[0]]
                marked[op.target.name] = (op.target, root, path + pr[1])
                virtual.add(k)
                changed = True
        for phi in phis:
            if (phi.target.name not in marked and reads.get(phi.target.name, 0) > 0
                    and any(whole(v, phi.target) for _, v in phi.sources)):
                add_root(phi.target)
                changed = True

    counter = [0]
    fresh_vars: list[StackVar] = []

    def realise(params: list[RParam], returned: bool) -> tuple[list[Op], dict[str, str]]:
        """Awaits and projections for the marked variables `params` read, and
        the renaming that points the reads at them."""
        used = sorted({v.name for p in params for v in p.get_live_vars() if v.name in marked})
        out: list[Op] = []
        renames: dict[str, str] = {}
        awaited: dict[str, tuple[StackVar, int]] = {}   # root name -> (its awaited name, its number)
        for name in used:
            var, root, path = marked[name]
            if root.name not in awaited:
                awaited[root.name] = (StackVar(root.get_type(), f"{root.name}$aw{counter[0]}"), counter[0])
                counter[0] += 1
                fresh_vars.append(awaited[root.name][0])
                out.append(Await(awaited[root.name][0], roots[root.name], returned=returned))
                renames[root.name] = awaited[root.name][0].name
            if var is not root:
                fresh = StackVar(var.get_type(), f"{var.name}$aw{awaited[root.name][1]}")
                fresh_vars.append(fresh)
                out.append(Move(fresh, _project(awaited[root.name][0], path)))
                renames[var.name] = fresh.name
        return out, renames

    def returned(op: Op) -> bool:
        return isinstance(op, Return) and whole(op.value, op.value) and op.value.get_type() == fn.result

    phis_at: dict[str, list[Phi]] = {}
    current: str | None = None
    for op in ops:
        if isinstance(op, Label):
            current = op.name
        elif isinstance(op, Phi):
            phis_at.setdefault(current, []).append(op)

    # (join label, predecessor label) -> each of the join's Phis' source from it
    edge_sources: dict[tuple[str, str | None], list[RParam]] = {}

    def edge(join: str, pred: str | None) -> list[Op]:
        """Realise, on the edge pred -> join, the Phi sources that need it."""
        out: list[Op] = []
        sources: list[RParam] = []
        for phi in phis_at.get(join, []):
            value = next(v for lbl, v in phi.sources if lbl == pred)
            pending = isinstance(phi.target, StackVar) and phi.target.name in roots
            if pending and whole(value, phi.target):
                sources.append(roots[marked[value.name][1].name])
                continue
            pre, renames = realise([value], False)
            out.extend(pre)
            value = value.rename_vars(renames)
            sources.append(wrap_value(value, roots[phi.target.name].get_type()) if pending else value)
        edge_sources[(join, pred)] = sources
        return out

    new_ops: list[Op | None] = []
    phi_slots: list[tuple[int, str, int]] = []   # (index in new_ops, join label, Phi index)
    current = None
    last: Op | None = None   # the last op emitted other than a Phi
    for k, op in enumerate(ops):
        if k in virtual:
            continue
        if isinstance(op, Phi):
            phi_slots.append((len(new_ops), current, phis_at[current].index(op)))
            new_ops.append(None)
            continue
        if isinstance(op, Label):
            if op.name in phis_at and last is not None and last.falls_through():
                new_ops.extend(edge(op.name, current))
            current = op.name
        elif isinstance(op, Jump) and op.name in phis_at:
            new_ops.extend(edge(op.name, current))
        pre, renames = realise(list(op.get_live_vars()[0]), returned(op))
        new_ops.extend(pre)
        op = op.rename_vars(renames) if renames else op
        if isinstance(op, Call) and isinstance(op.register, StackVar) and op.register.name in roots:
            op = dataclasses.replace(op, register=roots[op.register.name], deferred=True)
        new_ops.append(op)
        last = op

    for index, join, i in phi_slots:
        phi = phis_at[join][i]
        target = roots.get(phi.target.name, phi.target) if isinstance(phi.target, StackVar) else phi.target
        new_ops[index] = Phi(target, tuple((lbl, edge_sources[(join, lbl)][i])
                                           for lbl, _ in phi.sources))
    # Every marked name is now unwritten and unread: each root became its
    # pending source and its awaited names, each virtual its projections.
    kept = tuple((name, typ) for name, typ in fn.stack_vars.fields if name not in marked)
    new_vars = tuple((v.name, v.get_type()) for v in (*roots.values(), *fresh_vars))
    return dataclasses.replace(fn, ops=tuple(new_ops), stack_vars=Struct(kept + new_vars))
