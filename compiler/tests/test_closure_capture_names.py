"""Closure-class field names for captures (pyast/utils.py capture_field_name).

A closure class stores each capture as a field. Name lookup matches by PREFIX
(`name_matches`), so a field whose name starts `this@` answers to the class's
own receiver `this` as well, and every `this` in the method then has two
candidates. The captured receiver has always been stored under a `$`-prefixed
field; a captured LOCAL named `this` — uniquified to `this@<hash>` — must be
too. (The bootstrap's own `makeFetchFunction` names a local `this`; it was
harmless only until some lambda captured it.)
"""
from __future__ import annotations

from tests.testutil import BatchedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib


class TestClosureCaptureNames(TestCase):
    def test_a_captured_local_named_this(self):
        src = (
            "import System\n"
            "fun [tail] applyN(k: Int, f: (): Int, acc: Int): Int\n"
            "  ret k <= 0 ? acc : applyN(k - 1, f, acc + f())\n"
            "fun main(): Int\n"
            "  let this = 42\n"
            "  ret applyN(2, () => this + 1, 0) == 86 ? 0 : 1\n")
        self.assertEqual(0, compile_and_run_stdlib(src))
