"""Constant inlining pass.

A `let [const] NAME = literal` declaration is a name → literal alias.  At
every reference site the bare name is replaced by a fresh copy of the literal
expression, after which the const declaration itself is removed.

The literal-hoisting passes (lowering/integers.py, lowering/strings.py) run
later and naturally deduplicate any literals introduced by inlining, so a
const used in 100 places does not produce 100 copies in the emitted code.
"""
from __future__ import annotations

import dataclasses
from typing import Any

import pyast.statement as s
import pyast.expression as e
import pyast.resolver as g


def _is_literal(expr: e.Expression | None) -> bool:
    return isinstance(expr, (e.IntegerExpression, e.FloatExpression, e.StringExpression))


def inline_constants(statements: list[s.Statement]) -> list[s.Statement]:
    # Collect every const let's unique name → literal value.
    const_values: dict[str, e.Expression] = {}
    for stmt in statements:
        if isinstance(stmt, s.LetStatement) and "const" in stmt.attributes and _is_literal(stmt.default_value):
            const_values[stmt.name] = stmt.default_value

    if not const_values:
        return statements

    def replace(_resolver: g.Resolver, thing: Any) -> Any:
        if isinstance(thing, e.NamedExpression) and thing.name in const_values:
            literal = const_values[thing.name]
            # Re-stamp the line_ref so error messages point at the use site, not
            # the declaration. Other fields (value, precision) carry through.
            return dataclasses.replace(literal, line_ref=thing.line_ref)
        return thing

    rewritten: list[s.Statement] = []
    for stmt in statements:
        if isinstance(stmt, s.LetStatement) and stmt.name in const_values:
            continue  # drop const declarations — they live entirely as inlined uses
        rewritten.append(stmt.search_and_replace(g.ResolverRoot(statements), replace))
    return rewritten
