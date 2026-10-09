"""The `is` / `!is` type-test operators.

`L is R` is parse-time sugar for `match(L) (_: R) => true; () => false`, and
`L !is R` is its negation. R is a TYPE, so this is a runtime variant test over
any union the match machinery already supports (most commonly `T|None`).
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib


_P = "namespace Main\nimport System\n"


class TestIsOperator(TestCase):
    def _b(self, body: str) -> int:
        # `body` defines `probe(): System::Bool`; exit 1 if true, 0 if false.
        src = _P + body + (
            "fun main(): System::Int\n"
            "  ret probe() ? 1 : 0\n")
        return compile_and_run_stdlib(src)

    def test_is_none_true(self):
        self.assertEqual(1, self._b(
            "fun pick(): System::Int|System::None\n  ret None\n"
            "fun probe(): System::Bool\n  ret pick() is System::None\n"))

    def test_is_none_false(self):
        self.assertEqual(0, self._b(
            "fun pick(): System::Int|System::None\n  ret 7\n"
            "fun probe(): System::Bool\n  ret pick() is System::None\n"))

    def test_not_is_none_true_when_present(self):
        self.assertEqual(1, self._b(
            "fun pick(): System::Int|System::None\n  ret 7\n"
            "fun probe(): System::Bool\n  ret pick() !is System::None\n"))

    def test_not_is_none_false_when_none(self):
        self.assertEqual(0, self._b(
            "fun pick(): System::Int|System::None\n  ret None\n"
            "fun probe(): System::Bool\n  ret pick() !is System::None\n"))

    def test_is_selects_non_none_member(self):
        # R need not be None: test the String arm of a String|Int union.
        self.assertEqual(1, self._b(
            "fun pick(): System::String|System::Int\n  ret \"hi\"\n"
            "fun probe(): System::Bool\n  ret pick() is System::String\n"))

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
