"""System::splitLines — split a String into lines on '\\n', dropping a trailing
'\\r' so both LF and CRLF work; the text after the final newline is the last
element."""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


def _joined(literal_src: str) -> str:
    # Print each element wrapped in [...] so the split is checked exactly.
    return f"""\
import System

fun main(): System::Int
  let parts: List<System::String> = System::splitLines({literal_src})
  print(fold<System::String, System::String>(parts, "",
        (acc: System::String, s: System::String) => acc + "[" + s + "]"))
  ret 0
"""


class TestSplitLines(TestCase):
    def _split(self, literal_src: str) -> str:
        rc, out = compile_and_run_stdlib_capture(_joined(literal_src))
        self.assertEqual(0, rc, f"exited {rc}; stdout:\n{out}")
        return out

    def test_lf_and_crlf(self):
        # '\r' before the '\n' in "bb\r\n" is stripped → "bb".
        self.assertEqual("[a][bb][ccc]", self._split(r'"a\nbb\r\nccc"'))

    def test_trailing_newline_gives_empty_last(self):
        self.assertEqual("[a][]", self._split(r'"a\n"'))

    def test_no_newline_single_element(self):
        self.assertEqual("[x]", self._split('"x"'))

    def test_empty_string_one_empty_line(self):
        self.assertEqual("[]", self._split('""'))
