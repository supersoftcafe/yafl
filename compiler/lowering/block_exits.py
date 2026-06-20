"""Assign block-exit identifiers.

A `return` branches to the end of its nearest enclosing `BlockExpression`,
supplying its value as one source of that block's end Phi (see
`BlockExpression.generate_to` and `ReturnStatement.generate`). For the end
label, the per-return exit labels, and the per-return value vars to survive
`with_prefix` matched, they embed a unique '@'-bearing tag — the same trick
`LoopExpression` uses for its head label.

This pass stamps every `BlockExpression` with a unique tag and every
`ReturnStatement` with a unique index. It runs once, late — after every AST
pass that creates or copies blocks (inlining, [tail]-loop lowering, lambda
lifting, class lowering) — so each block instance, including inlined copies of
the same source body, gets its own tag and a copied early return is scoped to
the copy. These are lowering-time ordinals, exactly like
`RecurExpression.index`, not generation-time counters.
"""
from __future__ import annotations

import dataclasses

import pyast.expression as e
import pyast.statement as s
import pyast.resolver as g


def assign_block_exits(statements: list[s.Statement]) -> list[s.Statement]:
    # Mutable counters live only for this single deterministic walk; nothing
    # crosses a call boundary. A structural walk with an integer ordinal is
    # PYTHONHASHSEED-independent, so the tags are reproducible run to run.
    counters = {"block": 0, "ret": 0}

    def stamp(_resolver: g.Resolver, thing):
        if isinstance(thing, e.BlockExpression):
            n = counters["block"]
            counters["block"] = n + 1
            return dataclasses.replace(thing, tag=f"blk@{n}")
        if isinstance(thing, s.ReturnStatement):
            n = counters["ret"]
            counters["ret"] = n + 1
            return dataclasses.replace(thing, index=n)
        return thing

    resolver = g.ResolverRoot(statements)
    return [stmt.search_and_replace(resolver, stamp) for stmt in statements]
