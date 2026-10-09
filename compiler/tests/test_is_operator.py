"""The `is` / `!is` type-test operators.

`L is R` is parse-time sugar for `match(L) (_: R) => true; () => false`, and
`L !is R` is its negation. R is a TYPE, so this is a runtime variant test over
any union the match machinery already supports (most commonly `T|None`).

The runtime checks are [test]s in compiler/yafl_tests/is_operator.yafl.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase


class TestIsOperator(TestCase):
    def test_is_binds_looser_than_arithmetic(self):
        # `a + b is None` must read as `(a + b) is None`, not `a + (b is None)`.
        # Checked structurally: the whole expression is the `is` match, and its
        # subject is the `+` call (had `is` bound tighter, the top node would be
        # the `+` call instead).
        from parsing.tokenizer import tokenize
        import parsing.parser as parser
        import pyast.match as m
        import pyast.expression as e
        r = parser.parse_expression(tokenize("a + b is System::None", "f"))
        self.assertIsInstance(r.value, m.MatchExpression)
        self.assertIsInstance(r.value.subject, e.CallExpression)
