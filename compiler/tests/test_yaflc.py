"""The `examples/yaflc` self-hosting prototype: a miniature compiler for
"core YAFL" (single-expression functions over Int), written in YAFL.

Builds the example once, then drives the full chain per test: mini-YAFL
source on yaflc's stdin -> C on stdout -> clang -> run the binary and check
its answer. Covers arithmetic/precedence, recursion, mutual recursion via
forward declarations, comments, unary minus, and each compile-error path
(exit 1 with an `error:` line).
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_to_binary, _RUN_ENV

_EXAMPLE = Path(__file__).parent.parent.parent / "examples" / "yaflc.yafl"


class TestYaflc(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.yaflc = compile_to_binary(_EXAMPLE.read_text(), optimization_level=1)
        cls.tmp = tempfile.TemporaryDirectory()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()
        try:
            os.unlink(cls.yaflc)
        except OSError:
            pass

    def _compile(self, source: str) -> tuple[int, str]:
        r = subprocess.run([self.yaflc], input=source, capture_output=True,
                           timeout=30, text=True, env=_RUN_ENV)
        return r.returncode, r.stdout

    def _run_mini(self, source: str) -> int:
        """mini-YAFL -> yaflc -> C -> clang -> run; the printed number."""
        rc, c_code = self._compile(source)
        self.assertEqual(0, rc, f"yaflc rejected the program:\n{c_code}")
        binary = str(Path(self.tmp.name, "prog"))
        r = subprocess.run(["clang", "-x", "c", "-", "-O1", "-o", binary],
                           input=c_code, text=True, capture_output=True, timeout=30)
        self.assertEqual(0, r.returncode, f"clang rejected yaflc's C:\n{r.stderr}\n{c_code}")
        out = subprocess.run([binary], capture_output=True, timeout=30, text=True)
        self.assertEqual(0, out.returncode)
        return int(out.stdout.strip())

    def _expect_error(self, source: str, fragment: str):
        rc, out = self._compile(source)
        self.assertEqual(1, rc)
        self.assertIn("error:", out)
        self.assertIn(fragment, out)

    # ── programs that must compile and answer correctly ─────────────────────

    def test_fib_recursion(self):
        self.assertEqual(75025, self._run_mini(
            "fun fib(n) => n < 2 ? n : fib(n - 1) + fib(n - 2)\n"
            "fun main() => fib(25)\n"))

    def test_mutual_recursion_forward_decls(self):
        self.assertEqual(1, self._run_mini(
            "fun isEven(n) => n == 0 ? 1 : isOdd(n - 1)\n"
            "fun isOdd(n)  => n == 0 ? 0 : isEven(n - 1)\n"
            "fun main() => isEven(10)\n"))

    def test_precedence_and_parens(self):
        self.assertEqual(14, self._run_mini("fun main() => 2 + 3 * 4\n"))
        self.assertEqual(20, self._run_mini("fun main() => (2 + 3) * 4\n"))
        self.assertEqual(1, self._run_mini("fun main() => 1 + 2 * 3 == 7 ? 1 : 0\n"))

    def test_ternary_right_associative(self):
        # a ? b : c ? d : e parses as a ? b : (c ? d : e)
        self.assertEqual(5, self._run_mini("fun main() => 0 == 1 ? 2 : 0 == 2 ? 4 : 5\n"))

    def test_unary_minus_and_comments(self):
        self.assertEqual(7, self._run_mini(
            "# leading comment\n"
            "fun main() => -3 + 10   # trailing comment\n"))

    def test_params_and_calls(self):
        self.assertEqual(42, self._run_mini(
            "fun mul(a, b) => a * b\n"
            "fun main() => mul(2 + 4, 7)\n"))

    # ── programs that must be rejected, with the right diagnostic ───────────

    def test_unknown_variable(self):
        self._expect_error("fun main() => x + 1\n", "unknown variable x")

    def test_unknown_function(self):
        self._expect_error("fun main() => g(1)\n", "unknown function g")

    def test_arity_mismatch(self):
        self._expect_error("fun f(a) => a\nfun main() => f(1, 2)\n",
                           "f expects 1 argument(s), got 2")

    def test_duplicate_function(self):
        self._expect_error("fun f() => 1\nfun f() => 2\nfun main() => f()\n",
                           "duplicate function f")

    def test_missing_main(self):
        self._expect_error("fun f() => 1\n", "no main() function")

    def test_main_with_params(self):
        self._expect_error("fun main(x) => x\n", "main must take no parameters")

    def test_syntax_error_eof(self):
        self._expect_error("fun main() => 1 +\n", "unexpected end of input")

    def test_syntax_error_params(self):
        self._expect_error("fun main( => 1\n", "expected parameter name")

    def test_bad_character(self):
        self._expect_error("fun main() => 1 @ 2\n", "unexpected character")
