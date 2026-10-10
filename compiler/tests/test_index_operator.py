"""The `[]` index operator.

`left[right]` lowers to ``[]``(left, right), exactly as `left + right` lowers
to `+`(left, right). The parser does the rewrite at the invoke tier (so it
chains and interleaves with calls); resolution then finds whatever ``[]`` is
in scope, like any other operator. Nothing is auto-generated for arrays yet —
these tests only confirm the operator itself parses. That it runs is a [test]
in compiler/yafl_tests/index_operator.yafl.
"""
from __future__ import annotations

from parsing.tokenizer import tokenize
import parsing.parser as parser
import pyast.expression as e

from tests.testutil import TimedTestCase as TestCase


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
