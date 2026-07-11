"""Hoist nested FunctionStatements out of function bodies — its own pipeline
stage, run BEFORE tail_loop.

Nested function declarations live at the top of their host's body block. The
tail-to-loop rewrite wraps the whole body (declarations included) inside a
LoopExpression, after which nothing scanning body statements can see them —
running the hoist first means a [tail] host's helpers are already gone: a
non-capturing helper is a global by then, and a capturing one is a
LetStatement(lambda) that rides into the loop body and is constructed per
iteration, so it captures the CURRENT loop-carried parameter values (exactly
the semantics the recursive original had).

The SCC analysis and closure-vs-global strategy live in lowering/ast_inline.py
(shared with the inliner's machinery); this module is the stage entry point.
"""
from __future__ import annotations

import pyast.statement as s
from lowering.ast_inline import _hoist_nested_fns_to_lambdas


def hoist_nested_functions(statements: list[s.Statement]) -> list[s.Statement]:
    return _hoist_nested_fns_to_lambdas(list(statements))
