"""Regular expressions: `re"..."` raw literals + the stdlib RE2-style engine.

The literal is RAW (no yafl escapes — regex owns its backslashes), validated
at COMPILE time, and interned: every distinct pattern becomes one shared
`$regexes::` global (compiled once, lazily), so identical literals dedup and
a literal in a loop never reconstructs its Regex. The engine is pure YAFL —
a Pike VM: linear time guaranteed, no backreferences, leftmost-then-greedy
(Perl priority) semantics, byte-oriented with UTF-8 literals working
naturally. Spans are byte offsets; group() copies on demand.

The engine's behaviour is checked by compiler/yafl_tests/regex.yafl; here, the
compile-time side.

Runtime behaviour is checked by compiler/yafl_tests/regex.yafl.
"""
from __future__ import annotations


from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_c
from tests.testutil import compile_errors


def _errors(src: str) -> str:
    return compile_errors(src)


# Two identical literals among others.
_DEDUP = """namespace Test
import System

let word  = re"[A-Za-z_][A-Za-z0-9_]*"
let word2 = re"[A-Za-z_][A-Za-z0-9_]*"
let num   = re"-?[0-9]+"

fun main(): Int
  ret matches(word, "x") && matches(word2, "y") && matches(num, "1") ? 0 : 1
"""


class TestRegexCompileTime(TestCase):
    _TIMEOUT = 300

    def test_identical_literals_share_one_global(self):
        code = compile_c(_DEDUP, optimization_level=0)
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
