"""The `[]` index operator.

`left[right]` lowers to ``[]``(left, right), exactly as `left + right` lowers
to `+`(left, right). The parser does the rewrite at the invoke tier (so it
chains and interleaves with calls); resolution then finds whatever ``[]`` is
in scope, like any other operator. Nothing is auto-generated for arrays yet —
these tests only confirm the operator itself works.
"""
from __future__ import annotations

from parsing.tokenizer import tokenize
import parsing.parser as parser
import pyast.expression as e

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


class TestIndexOperatorParsing(TestCase):
    def test_index_lowers_to_bracket_operator_call(self):
        x = parser.parse_expression(tokenize("a[b]", "f")).value
        self.assertIsInstance(x, e.CallExpression)
        self.assertIsInstance(x.function, e.NamedExpression)
        self.assertEqual("`[]`", x.function.name)
        args = [en.value for en in x.parameter.expressions]
        self.assertEqual(2, len(args))
        self.assertEqual("a", args[0].name)
        self.assertEqual("b", args[1].name)

    def test_index_chains_left_associatively(self):
        # a[b][c] is `[]`(`[]`(a, b), c)
        x = parser.parse_expression(tokenize("a[b][c]", "f")).value
        self.assertEqual("`[]`", x.function.name)
        inner = x.parameter.expressions[0].value
        self.assertIsInstance(inner, e.CallExpression)
        self.assertEqual("`[]`", inner.function.name)


class TestIndexOperatorRuntime(TestCase):
    def test_user_defined_index_operator_is_called(self):
        # A plain top-level ``[]`` resolves and runs. Subtraction is
        # non-commutative, so 10[3] == 7 (not -7) confirms the operands map to
        # (left, right) in order.
        rc, out = compile_and_run_stdlib_capture("""import System
fun `[]`(left: System::Int, right: System::Int): System::Int
  ret left - right
fun main(): System::Int
  ret 10[3]
""", timeout=30)
        self.assertEqual(7, rc, f"expected 10[3] == 10 - 3 == 7; stdout:\n{out}")
