"""
Two-axis (cpu, io) cost model + per-function summaries.

Used by the auto-parallelise pass to decide whether a TupleExpression's
children are heavy enough to be worth scheduling concurrently.

Pipeline placement: instantiate after ast_inline.inline_ast and before
lambdas.convert_lambdas_to_functions. Generic monomorphisation has already
run, so call-target names are concrete; lambdas are still embedded as
LambdaExpression nodes so their bodies are walked in place.

IO weight is seeded entirely from existing language attributes — foreign
functions tagged [impure] are taken to do IO. Non-foreign functions
inherit IO weight from their callees through the call-graph fixpoint, so
user code calling io.write(...) automatically picks up IO weight without
any new annotation.

Indirect calls (virtual dispatch, function-pointer values, lambda values
invoked through a let binding) currently use a fixed default. A follow-up
pass can narrow this via signature matching.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Iterable

import pyast.expression as e
import pyast.match as m
import pyast.statement as s


# ---------------------------------------------------------------------------
# Weight
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Weight:
    cpu: int = 0
    io:  int = 0

    def __add__(self, other: "Weight") -> "Weight":
        return Weight(self.cpu + other.cpu, self.io + other.io)

    def joined(self, other: "Weight") -> "Weight":
        return Weight(max(self.cpu, other.cpu), max(self.io, other.io))

    def capped(self) -> "Weight":
        return Weight(min(self.cpu, CAP_CPU), min(self.io, CAP_IO))

    def qualifies(self, t_cpu: int, t_io: int) -> bool:
        return self.cpu >= t_cpu or self.io >= t_io

    @classmethod
    def zero(cls) -> "Weight":
        return cls(0, 0)


# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

CAP_CPU = 1024
CAP_IO  = 64

LITERAL_W   = Weight(1, 0)
OP_W        = Weight(1, 0)
ALLOC_W     = Weight(5, 0)
DOT_W       = Weight(2, 0)
DISPATCH_W  = Weight(2, 0)
INDIRECT_DEFAULT = Weight(20, 0)
SPAWN_W     = Weight(50, 0)

# Auto-parallelise thresholds. A tuple child "qualifies" if its weight clears
# either axis. ~5× spawn cost on the CPU side gives meaningful break-even;
# any IO at all qualifies because IO latency dwarfs spawn overhead. Need at
# least MIN_QUALIFYING children before the whole tuple is rewritten.
T_CPU = 250
T_IO  = 1
MIN_QUALIFYING = 2

# Foreign functions have no body; the seed approximates their cost.
# An [impure] foreign is presumed to do IO (matches stdlib/io.yafl);
# a [sync] or unmarked foreign is treated as a cheap primitive call.
FOREIGN_IMPURE_W = Weight(4, 8)
FOREIGN_PLAIN_W  = Weight(2, 0)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class CostModel:
    """Pre-computed function summaries; weighs expressions on demand."""

    summaries: dict[str, Weight]

    def __init__(self, statements: list[s.Statement]) -> None:
        self._fns_by_name: dict[str, s.FunctionStatement] = {
            fn.name: fn for fn in _collect_functions(statements)
        }
        self.summaries = self._build_summaries()

    def weigh(self, expr: e.Expression | None) -> Weight:
        if expr is None:
            return Weight.zero()
        return self._weigh(expr, self_scc=frozenset())

    # -- internals -------------------------------------------------------

    def _build_summaries(self) -> dict[str, Weight]:
        summaries: dict[str, Weight] = {}

        # Foreign seeds (no body to walk).
        for name, fn in self._fns_by_name.items():
            if fn.body is None:
                summaries[name] = _foreign_seed(fn)

        # Direct-call graph over non-foreign functions.
        graph: dict[str, set[str]] = {}
        known = set(self._fns_by_name)
        for name, fn in self._fns_by_name.items():
            if fn.body is None:
                continue
            graph[name] = _direct_callees(fn.body, known)

        # Tarjan emits SCCs in reverse-topological (callees-first) order,
        # which is exactly what bottom-up summarisation needs.
        sccs = _tarjan_scc(graph)

        for scc in sccs:
            self.summaries = summaries  # in-progress, readable by _weigh
            # Recursive SCC = mutual cycle (size > 1) or self-loop.
            # Recursion implies a loop body whose iteration count we don't
            # model. We pessimistically lift the CPU summary to T_CPU so any
            # recursive function qualifies on its own — false positives here
            # cost a spawn, false negatives lose the parallel opportunity.
            is_recursive = (len(scc) > 1
                            or any(name in graph.get(name, ()) for name in scc))
            for name in scc:
                fn = self._fns_by_name[name]
                # Foreign functions appear here as singleton SCCs (Tarjan
                # follows call-graph edges into them). Their seed is already
                # set above; don't overwrite it with a zero weigh-of-None.
                if fn.body is None:
                    continue
                w = _weigh_expr(fn.body, summaries, self._fns_by_name, scc)
                if is_recursive:
                    w = w.joined(Weight(T_CPU, 0))
                # Cap protects against pathological depth and saturates the
                # answer near "is this above threshold?", which is all step 3
                # cares about.
                summaries[name] = w.capped()

        self.summaries = summaries
        return summaries

    def _weigh(self, expr: e.Expression, self_scc: frozenset[str]) -> Weight:
        return _weigh_expr(expr, self.summaries, self._fns_by_name, self_scc)


def _foreign_seed(fn: s.FunctionStatement) -> Weight:
    return FOREIGN_IMPURE_W if "impure" in fn.attributes else FOREIGN_PLAIN_W


# ---------------------------------------------------------------------------
# Function collection — top-level + nested in classes
# ---------------------------------------------------------------------------

def _collect_functions(stmts: Iterable[s.Statement]) -> Iterable[s.FunctionStatement]:
    for st in stmts:
        if isinstance(st, s.FunctionStatement):
            yield st
        elif isinstance(st, s.ClassStatement):
            yield from _collect_functions(st.statements)


# ---------------------------------------------------------------------------
# Direct-call discovery
# ---------------------------------------------------------------------------

def _resolve_direct_target(fn_expr: e.Expression, known: set[str]) -> str | None:
    """If `fn_expr` resolves to a known global function, return its name."""
    if isinstance(fn_expr, e.NamedExpression) and fn_expr.name in known:
        return fn_expr.name
    return None


def _direct_callees(expr: e.Expression, known: set[str]) -> set[str]:
    out: set[str] = set()

    def visit_stmt(st):
        if isinstance(st, s.LetStatement) and st.default_value is not None:
            visit(st.default_value)
        elif isinstance(st, s.FunctionStatement) and st.body is not None:
            visit(st.body)

    def visit(node):
        if node is None:
            return
        if isinstance(node, e.CallExpression):
            tgt = _resolve_direct_target(node.function, known)
            if tgt is not None:
                out.add(tgt)
            visit(node.function)
            visit(node.parameter)
        elif isinstance(node, e.TupleExpression):
            for entry in node.expressions:
                visit(entry.value)
        elif isinstance(node, e.ParallelExpression):
            for x in node.exprs:
                visit(x)
        elif isinstance(node, e.NewExpression):
            visit(node.parameter)
        elif isinstance(node, e.DotExpression):
            visit(node.base)
        elif isinstance(node, e.TernaryExpression):
            visit(node.condition); visit(node.trueResult); visit(node.falseResult)
        elif isinstance(node, e.BoxExpression):
            visit(node.inner)
        elif isinstance(node, e.NewEnumExpression):
            for arg in node.field_args.values():
                visit(arg)
        elif isinstance(node, e.LambdaExpression):
            visit(node.expression)
        elif isinstance(node, e.BuiltinOpExpression):
            visit(node.params)
        elif isinstance(node, e.BlockExpression):
            for st in node.statements:
                visit_stmt(st)
            visit(node.value)
        elif isinstance(node, m.MatchExpression):
            visit(node.subject)
            for arm in node.arms:
                visit(arm.body)
                visit(arm.literal)
        # Leaf nodes (literals, NamedExpression, NothingExpression) — done.

    visit(expr)
    return out


# ---------------------------------------------------------------------------
# Tarjan SCC (recursion-depth raised since YAFL function bodies can deep-nest)
# ---------------------------------------------------------------------------

def _tarjan_scc(graph: dict[str, set[str]]) -> list[frozenset[str]]:
    sys.setrecursionlimit(max(sys.getrecursionlimit(), 10_000))
    index_counter = [0]
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    result: list[frozenset[str]] = []

    def strongconnect(v: str) -> None:
        indices[v] = index_counter[0]
        lowlinks[v] = index_counter[0]
        index_counter[0] += 1
        stack.append(v)
        on_stack.add(v)

        for w in graph.get(v, ()):
            if w not in indices:
                strongconnect(w)
                lowlinks[v] = min(lowlinks[v], lowlinks[w])
            elif w in on_stack:
                lowlinks[v] = min(lowlinks[v], indices[w])

        if lowlinks[v] == indices[v]:
            scc: list[str] = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                scc.append(w)
                if w == v:
                    break
            result.append(frozenset(scc))

    for v in graph:
        if v not in indices:
            strongconnect(v)
    return result


# ---------------------------------------------------------------------------
# Expression weigher
# ---------------------------------------------------------------------------

def _weigh_expr(expr: e.Expression | None,
                summaries: dict[str, Weight],
                fns_by_name: dict[str, s.FunctionStatement],
                self_scc: frozenset[str]) -> Weight:
    if expr is None:
        return Weight.zero()

    def w(node: e.Expression | None) -> Weight:
        return _weigh_expr(node, summaries, fns_by_name, self_scc)

    # ParallelExpression: bottom-up, an already-rewritten parallel tuple
    # contributes its parallel cost (spawn + max of branches), not the sum.
    # This is what makes the auto-parallelise traversal in step 3 self-consistent.
    if isinstance(expr, e.ParallelExpression):
        body = Weight.zero()
        for x in expr.exprs:
            body = body.joined(w(x))
        return SPAWN_W + body

    if isinstance(expr, (e.IntegerExpression, e.FloatExpression,
                         e.StringExpression, e.NothingExpression,
                         e.NamedExpression)):
        return LITERAL_W

    if isinstance(expr, e.BuiltinOpExpression):
        return OP_W + w(expr.params)

    if isinstance(expr, e.DotExpression):
        return DOT_W + w(expr.base)

    if isinstance(expr, e.NewExpression):
        return ALLOC_W + w(expr.parameter)

    if isinstance(expr, e.NewEnumExpression):
        total = ALLOC_W
        for arg in expr.field_args.values():
            total = total + w(arg)
        return total

    if isinstance(expr, e.TupleExpression):
        total = Weight.zero()
        for entry in expr.expressions:
            total = total + w(entry.value)
        return total

    if isinstance(expr, e.TernaryExpression):
        return DISPATCH_W + w(expr.condition) + w(expr.trueResult).joined(w(expr.falseResult))

    if isinstance(expr, e.BlockExpression):
        total = Weight.zero()
        for st in expr.statements:
            if isinstance(st, s.LetStatement) and st.default_value is not None:
                total = total + w(st.default_value)
            # Nested function declarations don't pay until they're called.
        return total + w(expr.value)

    if isinstance(expr, m.MatchExpression):
        body = Weight.zero()
        for arm in expr.arms:
            body = body.joined(w(arm.body))
        return DISPATCH_W + w(expr.subject) + body

    if isinstance(expr, e.LambdaExpression):
        # As a value: closure allocation. Body cost is paid wherever invoked.
        return ALLOC_W

    if isinstance(expr, e.CallExpression):
        arg_w = w(expr.function) + w(expr.parameter)
        target = _resolve_direct_target(expr.function, set(fns_by_name))
        if target is not None and target in self_scc:
            return arg_w  # one-iteration weight: own SCC contributes zero
        if target is not None and target in summaries:
            return arg_w + summaries[target]
        return arg_w + INDIRECT_DEFAULT

    if isinstance(expr, e.BoxExpression):
        return w(expr.inner)

    return LITERAL_W
