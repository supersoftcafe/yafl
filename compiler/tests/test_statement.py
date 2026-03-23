from __future__ import annotations

from dataclasses import dataclass
from unittest import TestCase

import pyast.expression as e
import pyast.resolver as g
import pyast.statement as s
import pyast.typespec as t
from parsing.tokenizer import LineRef


lr = LineRef("test", 1, 0)


@dataclass
class _DummyStatement(s.Statement):
    """A minimal Statement subclass for use as a side-effect in tests."""

    def compile(self, resolver, func_ret_type):
        return self, []

    def check(self, resolver, func_ret_type):
        return []


@dataclass
class _ExprWithSideEffect(e.Expression):
    """An expression whose compile() returns a side statement."""
    side_stmt: s.Statement

    def get_type(self, resolver):
        return t.BuiltinSpec(lr, "int32")

    def compile(self, resolver, expected_type):
        return e.IntegerExpression(lr, 42), [self.side_stmt]

    def check(self, resolver, expected_type):
        return []

    def generate(self, resolver):
        raise NotImplementedError()


class TestReturnStatementCompile(TestCase):
    def test_propagates_statements_from_expression_compile(self):
        """ReturnStatement.compile must propagate statements returned by value.compile.

        If the return expression's compile() yields hoisted statements (e.g. a
        global constant it introduces), those must flow back to the caller; the
        old code discarded them by returning [] unconditionally.
        """
        resolver = g.ResolverRoot([])
        int32_type = t.BuiltinSpec(lr, "int32")
        side_stmt = _DummyStatement(lr)
        expr = _ExprWithSideEffect(lr, side_stmt)
        ret_stmt = s.ReturnStatement(lr, expr)

        _, stmts = ret_stmt.compile(resolver, int32_type)

        self.assertIn(
            side_stmt,
            stmts,
            "ReturnStatement.compile must propagate statements from expression.compile",
        )
