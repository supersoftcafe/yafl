"""Numeric string/char escapes: `\\xNN`, `\\uXXXX`, and `\\u{…}`.

All three denote a Unicode codepoint (decoded in `_unescape_string`,
`parsing/parser.py`) and are encoded to UTF-8 like any other source character.
`\\xNN` is exactly two hex digits (U+0000–U+00FF); `\\uXXXX` is exactly four;
`\\u{…}` takes one to six and reaches the full scalar range. Out-of-range and
surrogate codepoints are rejected so a decoded literal is always valid UTF-8.
Char literals reuse the same decoder, so `'\\u{…}'` is an Int32 codepoint.
"""
from __future__ import annotations

import compiler as c
from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


class TestEscapesRuntime(TestCase):
    def test_codepoints_decode_and_encode(self):
        # Each escape equals its literal spelling; byte lengths confirm UTF-8
        # encoding (é = 2 bytes, 🎉 = 4 bytes). `&&` chains the checks; rc 0 = all
        # passed.
        src = """\
import System

fun main(): System::Int
  ret ("\\x41" == "A")
   && ("\\u0042" == "B")
   && ("\\u{43}" == "C")
   && ("\\u{E9}" == "é")
   && ("\\u{1F389}" == "🎉")
   && (System::length("\\u{1F389}") == 4)
   && (System::length("\\u{E9}") == 2)
   && ('\\x41' == 65i32)
   && ('\\u{1F389}' == 0x1F389i32)
   ? 0 : 1
"""
        rc, _ = compile_and_run_stdlib_capture(src)
        self.assertEqual(0, rc)


class TestEscapeErrors(TestCase):
    """Malformed escapes are rejected at parse time (compile returns "")."""

    def _rejects(self, literal: str) -> None:
        src = (
            "import System\n"
            "fun main(): System::Int\n"
            f'    print("{literal}")\n'
            "    ret 0\n"
        )
        result = c.compile([c.Input(src, "test.yafl")], use_stdlib=True, just_testing=False)
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
