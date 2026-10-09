"""Numeric string/char escapes: `\\xNN`, `\\uXXXX`, and `\\u{…}`.

All three denote a Unicode codepoint (decoded in `_unescape_string`,
`parsing/parser.py`) and are encoded to UTF-8 like any other source character.
`\\xNN` is exactly two hex digits (U+0000–U+00FF); `\\uXXXX` is exactly four;
`\\u{…}` takes one to six and reaches the full scalar range. Out-of-range and
surrogate codepoints are rejected so a decoded literal is always valid UTF-8.
Char literals reuse the same decoder, so `'\\u{…}'` is an Int32 codepoint.
The runtime checks are [test]s in compiler/yafl_tests/string_escapes.yafl.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_c


class TestEscapeErrors(TestCase):
    """Malformed escapes are rejected at parse time (compile returns "")."""

    def _rejects(self, literal: str) -> None:
        src = (
            "import System\n"
            "fun main(): System::Int\n"
            f'    print("{literal}")\n'
            "    ret 0\n"
        )
        result = compile_c(src)
        self.assertEqual("", result, f"expected {literal!r} to be rejected")

    def test_x_too_few_digits(self):
        self._rejects("\\x4")

    def test_x_non_hex(self):
        self._rejects("\\xG0")

    def test_u_too_few_digits(self):
        self._rejects("\\u12")

    def test_u_braces_empty(self):
        self._rejects("\\u{}")

    def test_u_braces_unterminated(self):
        self._rejects("\\u{1F389")

    def test_u_out_of_range(self):
        self._rejects("\\u{110000}")

    def test_u_surrogate(self):
        self._rejects("\\u{D800}")
