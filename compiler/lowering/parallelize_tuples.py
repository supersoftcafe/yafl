"""
Auto-parallelise heavy tuple constructions.

Walks function bodies bottom-up. For each TupleExpression, weighs each child
via the cost model; if at least MIN_QUALIFYING children clear the threshold,
rewrites the entire tuple as a ParallelExpression of zero-arg lambdas.
All-or-nothing: trivial children come along for the ride and pay a small
spawn-cost dominated by the heavy ones.

Pipeline placement: between ast_inline.inline_ast and lambdas.convert_lambdas_to_functions
in __iterate_and_compile (compiler.py). Lambda lowering then hoists the
synthesised () => expr lambdas to top-level functions, exactly as it does
for user-written __parallel__ arguments.

Synthesised lambdas have return_type populated up-front by inspecting each
child's type via the live resolver. This avoids a chicken-and-egg with
CallExpression.compile, which bails when a parameter's type is unresolved —
without a populated return_type, ParallelExpression.get_type returns None,
causing the surrounding call to refuse to recurse and never compile the
lambdas.
"""
from __future__ import annotations

from typing import Any, Callable

import pyast.expression as e
import pyast.resolver as g
import pyast.statement as s
import pyast.typespec as t
import pyast.match as m

from lowering.cost_model import (
    CostModel,
    T_CPU, T_IO, MIN_QUALIFYING,
)


def parallelize_heavy_tuples(statements: list[s.Statement]) -> list[s.Statement]:
    cm = CostModel(statements)
    root: g.Resolver = g.ResolverRoot(statements)

    def replace(resolver: g.Resolver, node: Any) -> Any:
        if isinstance(node, e.TupleExpression):
            return _maybe_parallelise(node, cm, resolver)
        return node

    def visit_top(stmt: s.Statement) -> s.Statement:
        # Skip generic templates: lifting a tuple from a generic body into
        # a closure would bake the captured field types in with placeholder
        # types, and monomorphisation later doesn't propagate substitutions
        # all the way through the synthesised closure shape. Run this pass
        # only on non-generic top-level statements; concrete monomorphised
        # callees are still seen via the cost model's call-graph.
        if isinstance(stmt, s.NamedStatement) and stmt.type_params:
            return stmt
        return stmt.search_and_replace(root, replace)

    return [visit_top(stmt) for stmt in statements]


def _maybe_parallelise(node: e.TupleExpression,
                       cm: CostModel,
                       resolver: g.Resolver) -> e.Expression:
    if len(node.expressions) < MIN_QUALIFYING:
        return node
    weights = [cm.weigh(entry.value) for entry in node.expressions]
    qualifying = sum(1 for w in weights if w.qualifies(T_CPU, T_IO))
    if qualifying < MIN_QUALIFYING:
        return node
    lambdas = [_wrap_zero_arg_lambda(entry.value, resolver)
               for entry in node.expressions]
    # Bail if we couldn't determine any child's type — without it, the
    # synthesised ParallelExpression won't type-check downstream.
    if any(lmd is None for lmd in lambdas):
        return node
    return e.ParallelExpression(line_ref=node.line_ref, exprs=lambdas)


def _wrap_zero_arg_lambda(expr: e.Expression,
                          resolver: g.Resolver) -> e.LambdaExpression | None:
    """Mirror the parser's `() => expr` shape, with return_type pre-populated.

    The empty DestructureStatement has the same field layout as parser.py:232.
    """
    body_type = expr.get_type(resolver)
    if body_type is None:
        return None
    empty_params = s.DestructureStatement(
        expr.line_ref, '_', None, {}, (), None, None, [])
    params_type = empty_params.get_type()
    return_type = t.CallableSpec(expr.line_ref, params_type, body_type)
    return e.LambdaExpression(expr.line_ref, empty_params, expr, return_type)
