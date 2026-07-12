"""Regular expressions: `re"..."` raw literals + the stdlib RE2-style engine.

The literal is RAW (no yafl escapes — regex owns its backslashes), validated
at COMPILE time, and interned: every distinct pattern becomes one shared
`$regexes::` global (compiled once, lazily), so identical literals dedup and
a literal in a loop never reconstructs its Regex. The engine is pure YAFL —
a Pike VM: linear time guaranteed, no backreferences, leftmost-then-greedy
(Perl priority) semantics, byte-oriented with UTF-8 literals working
naturally. Spans are byte offsets; group() copies on demand.
"""
from __future__ import annotations

import contextlib
import io

import compiler as c

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


def _errors(src: str) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        c.compile([c.Input(src, "test.yafl")], use_stdlib=True, just_testing=True)
    return buf.getvalue()


_RUNTIME = """namespace Test
import System

let word  = re"[A-Za-z_][A-Za-z0-9_]*"
let word2 = re"[A-Za-z_][A-Za-z0-9_]*"
let num   = re"-?[0-9]+"
let kv    = re"([a-z]+)=([0-9]+)"
let pet   = re"cat|dog"
let deci  = re"\\d+\\.\\d+"
let exact = re"^abc$"
let tagG  = re"<(.+)>"
let tagL  = re"<(.+?)>"

fun spanIs(m: Match|None, start: Int, end: Int): Bool
  ret match(m)
    (x: Match)        => x.start == start && x.end == end
    (n: System::None) => false

fun g(m: Match|None, s: String, i: Int): String
  ret match(m)
    (x: Match) => match(group(x, s, i))
      (v: String)       => v
      (n: System::None) => "<none>"
    (n: System::None) => "<nomatch>"

fun main(): Int
  # find + span (byte offsets, end exclusive)
  let ok1 = spanIs(find(num, "abc-42def"), 3, 6)
  # anywhere-semantics matches
  let ok2 = matches(word, "9hello") && !matches(num, "abcdef")
  # anchors make it exact
  let ok3 = matches(exact, "abc") && !matches(exact, "xabcy")
  # alternation
  let ok4 = matches(pet, "hotdog stand") && !matches(pet, "canary")
  # capture groups
  let m = find(kv, "size count=42;")
  let ok5 = g(m, "size count=42;", 1) == "count" && g(m, "size count=42;", 2) == "42"
  # escapes (raw literal: single backslash reaches the engine)
  let ok6 = spanIs(find(deci, "pi=3.14!"), 3, 7)
  # greedy vs lazy
  let ok7 = g(find(tagG, "<a><b>"), "<a><b>", 1) == "a><b"
         && g(find(tagL, "<a><b>"), "<a><b>", 1) == "a"
  # find honours `from` (defaults machinery)
  let ok8 = spanIs(find(num, "1 22", 1), 2, 4)
  # negated classes and plus
  let ok9 = spanIs(find(re"[^ ]+", "  jam  "), 2, 5)
  # group 0 is the whole match
  let ok10 = g(find(kv, "count=42"), "count=42", 0) == "count=42"
  ret ok1 && ok2 && ok3 && ok4 && ok5 && ok6 && ok7 && ok8 && ok9 && ok10 ? 0 : 1
"""


class TestRegexRuntime(TestCase):
    _TIMEOUT = 300

    def test_engine(self):
        rc, out = compile_and_run_stdlib_capture(_RUNTIME, timeout=120)
        self.assertEqual(0, rc, f"regex runtime failed; stdout:\n{out}")


class TestRegexCompileTime(TestCase):
    _TIMEOUT = 300

    def test_identical_literals_share_one_global(self):
        code = c.compile([c.Input(_RUNTIME, "test.yafl")], use_stdlib=True,
                         just_testing=False, optimization_level=0)
        assert code, "compilation failed"
        # The pattern text is interned once as a string global; two identical
        # re-literals must not produce two copies of it.
        self.assertEqual(1, code.count("[A-Za-z_][A-Za-z0-9_]*"),
                         "identical regex literals were not deduplicated")

    def test_invalid_pattern_is_a_compile_error(self):
        errs = _errors("namespace Test\nimport System\n"
                       "let broken = re\"[abc\"\n"
                       "fun main(): Int\n  ret matches(broken, \"a\") ? 0 : 1\n")
        self.assertIn("regex", errs.lower())

    def test_backreference_is_rejected(self):
        # Linear-time guarantee: backreferences are not a thing, ever.
        errs = _errors("namespace Test\nimport System\n"
                       "let b = re\"(a)\\1\"\n"
                       "fun main(): Int\n  ret matches(b, \"aa\") ? 0 : 1\n")
        self.assertIn("regex", errs.lower())
