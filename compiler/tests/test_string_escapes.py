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
from tests.testutil import compile_errors


class TestEscapeErrors(TestCase):
    """Malformed escapes are rejected at parse time, at the literal."""

    def _rejects(self, literal: str, message: str) -> None:
        src = (
            "import System\n"
            "fun main(): System::Int\n"
            f'    print("{literal}")\n'
            "    ret 0\n"
        )
        # Reported at the literal: line 3, column 11.
        self.assertEqual(f"test.yafl[3:11] - {message}\n", compile_errors(src))

    def test_x_too_few_digits(self):
        self._rejects("\\x4",
                      "\\x escape needs exactly two hex digits")

    def test_x_non_hex(self):
        self._rejects("\\xG0",
                      "\\x escape needs exactly two hex digits")

    def test_u_too_few_digits(self):
        self._rejects("\\u12",
                      "\\u escape needs exactly four hex digits (or use \\u{…})")

    def test_u_braces_empty(self):
        self._rejects("\\u{}",
                      "\\u{…} escape needs one to six hex digits")

    def test_u_braces_unterminated(self):
        self._rejects("\\u{1F389",
                      "unterminated \\u{…} escape")

    def test_u_out_of_range(self):
        self._rejects("\\u{110000}",
                      "codepoint U+110000 is out of range (max U+10FFFF)")

    def test_u_surrogate(self):
        self._rejects("\\u{D800}",
                      "codepoint U+D800 is a UTF-16 surrogate, not a scalar value")
