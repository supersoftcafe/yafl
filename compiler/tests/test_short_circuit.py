"""Short-circuit logical operators `&&` and `||`.

These are parse-time sugar for the ternary expression (`parser.py`):
    a && b   ->   a ? b : false
    a || b   ->   a ? true : b
so short-circuit is a *guaranteed* semantic — the right operand is not evaluated
when the left already decides the result — rather than an optimiser artefact.
The eager both-operands bool ops remain `&`/`|`.

Precedence (tightest first among these): comparison/bind > `&&` > `||` > `?:`.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


# A bool-returning function that announces every time it runs, so a missing /
# present "L"/"R" in stdout proves which operands were actually evaluated.
_LOUD = """\
import System

fun left(v: System::Bool): System::Bool
  System::print("L")
  ret v

fun right(v: System::Bool): System::Bool
  System::print("R")
  ret v
"""


class TestShortCircuit(TestCase):
    def _run(self, body: str) -> tuple[int, str]:
        return compile_and_run_stdlib_capture(_LOUD + body)

    # ── && truth table (exit code is the bool, 1/0) ───────────────────────────
    def test_and_true_true(self):
        rc, _ = self._run("fun main(): System::Int\n  ret true && true ? 1 : 0\n")
        self.assertEqual(1, rc)

    def test_and_true_false(self):
        rc, _ = self._run("fun main(): System::Int\n  ret true && false ? 1 : 0\n")
        self.assertEqual(0, rc)

    def test_and_false_x(self):
        rc, _ = self._run("fun main(): System::Int\n  ret false && true ? 1 : 0\n")
        self.assertEqual(0, rc)

    # ── || truth table ────────────────────────────────────────────────────────
    def test_or_false_false(self):
        rc, _ = self._run("fun main(): System::Int\n  ret false || false ? 1 : 0\n")
        self.assertEqual(0, rc)

    def test_or_false_true(self):
        rc, _ = self._run("fun main(): System::Int\n  ret false || true ? 1 : 0\n")
        self.assertEqual(1, rc)

    def test_or_true_x(self):
        rc, _ = self._run("fun main(): System::Int\n  ret true || false ? 1 : 0\n")
        self.assertEqual(1, rc)

    # ── short-circuit: the skipped operand must NOT run ───────────────────────
    def test_and_short_circuits_right(self):
        # left() returns false, so right() must never be called.
        rc, out = self._run("fun main(): System::Int\n  ret left(false) && right(true) ? 1 : 0\n")
        self.assertEqual(0, rc)
        self.assertEqual("L", out)

    def test_and_evaluates_right_when_left_true(self):
        rc, out = self._run("fun main(): System::Int\n  ret left(true) && right(true) ? 1 : 0\n")
        self.assertEqual(1, rc)
        self.assertEqual("LR", out)

    def test_or_short_circuits_right(self):
        # left() returns true, so right() must never be called.
        rc, out = self._run("fun main(): System::Int\n  ret left(true) || right(false) ? 1 : 0\n")
        self.assertEqual(1, rc)
        self.assertEqual("L", out)

    def test_or_evaluates_right_when_left_false(self):
        rc, out = self._run("fun main(): System::Int\n  ret left(false) || right(true) ? 1 : 0\n")
        self.assertEqual(1, rc)
        self.assertEqual("LR", out)

    # ── precedence ────────────────────────────────────────────────────────────
    def test_and_binds_tighter_than_or(self):
        # `false && false || true` parses as `(false && false) || true` == true.
        rc, _ = self._run("fun main(): System::Int\n  ret false && false || true ? 1 : 0\n")
        self.assertEqual(1, rc)

    def test_comparison_binds_tighter_than_logical(self):
        # `1 > 0 && 2 > 3` parses as `(1 > 0) && (2 > 3)` == false; no parens needed.
        rc, _ = self._run("fun main(): System::Int\n  ret 1 > 0 && 2 > 3 ? 1 : 0\n")
        self.assertEqual(0, rc)
