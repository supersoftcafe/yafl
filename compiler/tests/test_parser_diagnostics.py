"""Parser diagnostics quality.

When a parse fails, the *specific* message produced deep in the grammar (a bad
string escape, an orphan `else`, …) must reach the user — not be swallowed by
the combinator pipeline and replaced with the generic "extra unexpected
characters". The `|` (ordered-choice) combinator used to discard a failed
alternative's errors wholesale; it now keeps a hard failure's diagnostic when no
alternative matches. See parsing/parselib.py (`__or__`, `block`).
"""
from __future__ import annotations

from parsing.tokenizer import tokenize
from parsing.parser import parse
from tests.testutil import TimedTestCase as TestCase


class TestParserDiagnostics(TestCase):
    def _messages(self, src: str) -> list[str]:
        return [e.message for e in parse(tokenize(src, "test.yafl")).errors]

    def _assert_mentions(self, src: str, needle: str) -> None:
        msgs = self._messages(src)
        self.assertTrue(
            any(needle in m for m in msgs),
            f"expected a diagnostic mentioning {needle!r}, got: {msgs}")

    def test_bad_x_escape_message_surfaces(self):
        src = ('import System\n'
               'fun main(): System::Int\n'
               '    print("\\x4")\n'
               '    ret 0\n')
        self._assert_mentions(src, "\\x escape")

    def test_surrogate_escape_message_surfaces(self):
        src = ('import System\n'
               'fun main(): System::Int\n'
               '    print("\\u{D800}")\n'
               '    ret 0\n')
        self._assert_mentions(src, "surrogate")

    def test_unknown_escape_message_surfaces(self):
        src = ('import System\n'
               'fun main(): System::Int\n'
               '    print("\\q")\n'
               '    ret 0\n')
        self._assert_mentions(src, "unknown string escape")
