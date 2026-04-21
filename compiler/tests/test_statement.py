from __future__ import annotations

from dataclasses import dataclass
from unittest import TestCase

import pyast.expression as e
import pyast.match as m
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


class TestFindLocalsDestructure(TestCase):
    def test_destructure_leaf_names_are_resolved(self):
        """BlockExpression.__find_locals must match leaf names from DestructureStatement.

        When a block body contains `let (a, b) = expr`, the DestructureStatement
        has name='_' and targets=[LetStatement('a',...), LetStatement('b',...)].
        BlockExpression.__find_locals must find the leaf names via flatten().
        """
        int32_type = t.BuiltinSpec(lr, "int32")
        tuple_type = t.TupleSpec(lr, [
            t.TupleEntrySpec("a", int32_type, None),
            t.TupleEntrySpec("b", int32_type, None),
        ])
        leaf_a = s.LetStatement(lr, "a@abc123", None, {}, (), None, int32_type)
        leaf_b = s.LetStatement(lr, "b@abc123", None, {}, (), None, int32_type)
        destr = s.DestructureStatement(lr, "_", None, {}, (), None, tuple_type, [leaf_a, leaf_b])

        value_expr = e.IntegerExpression(lr, 0, 32)
        block = e.BlockExpression(lr, [destr], value_expr)

        find_locals = block._find_locals()

        resolved_a = find_locals({"a@abc123"})
        self.assertEqual(len(resolved_a), 1,
            "__find_locals must resolve leaf 'a' from DestructureStatement in block")
        self.assertIs(resolved_a[0].statement, leaf_a)

        resolved_b = find_locals({"b@abc123"})
        self.assertEqual(len(resolved_b), 1,
            "__find_locals must resolve leaf 'b' from DestructureStatement in block")
        self.assertIs(resolved_b[0].statement, leaf_b)

        # The synthetic root name '_' must NOT be returned when querying for real names
        resolved_underscore = find_locals({"_"})
        self.assertEqual(len(resolved_underscore), 0,
            "__find_locals must not resolve the synthetic '_' root as a real local")


class TestDestructureStatementAddNamespace(TestCase):
    def test_add_namespace_does_not_raise(self):
        """DestructureStatement.add_namespace must use super() not super(self).

        super(self) passes an instance where a type is expected and raises
        TypeError at runtime.  The fix is to use the no-argument super() form.
        """
        int32_type = t.BuiltinSpec(lr, "int32")
        tuple_type = t.TupleSpec(lr, [
            t.TupleEntrySpec("a", int32_type, None),
            t.TupleEntrySpec("b", int32_type, None),
        ])
        leaf_a = s.LetStatement(lr, "a", None, {}, (), None, int32_type)
        leaf_b = s.LetStatement(lr, "b", None, {}, (), None, int32_type)
        destr = s.DestructureStatement(lr, "_", None, {}, (), None, tuple_type, [leaf_a, leaf_b])

        # add_namespace must not raise; the root name '_' stays as '_' and leaf
        # targets get the namespace prefix applied.
        result = destr.add_namespace("NS::")
        self.assertIsInstance(result, s.DestructureStatement,
            "add_namespace on a DestructureStatement must return a DestructureStatement")
        self.assertEqual(result.name, "_",
            "root name '_' must be preserved by add_namespace")
        self.assertEqual(result.targets[0].name, "NS::a",
            "leaf target 'a' must be prefixed with namespace")
        self.assertEqual(result.targets[1].name, "NS::b",
            "leaf target 'b' must be prefixed with namespace")


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


class TestMatchArmCompile(TestCase):
    def test_match_expression_propagates_arm_hoisted_statements(self):
        """MatchExpression.compile must propagate hoisted statements from arm bodies.

        MatchArm.compile previously used `new_body, _ = self.body.compile(...)`
        which silently discarded any list[Statement] the body expression returned.
        The same bug existed for the type_spec compile call.  Both drops must be
        fixed: the statements must flow up through MatchArm.compile and then
        through MatchExpression.compile to the caller.
        """
        resolver = g.ResolverRoot([])
        int32_type = t.BuiltinSpec(lr, "int32")
        side_stmt = _DummyStatement(lr)
        body_expr = _ExprWithSideEffect(lr, side_stmt)
        # Else arm (type_spec=None) so only the body path is exercised here.
        arm = m.MatchArm(lr, None, None, body_expr)
        subject = e.IntegerExpression(lr, 0, precision=32)
        match_expr = m.MatchExpression(lr, subject, [arm])

        _, stmts = match_expr.compile(resolver, int32_type)

        self.assertIn(
            side_stmt,
            stmts,
            "MatchExpression.compile must propagate hoisted statements from arm bodies",
        )
