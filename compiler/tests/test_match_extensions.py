"""Match extensions: multi-literal arms (any-of, separated by `|`) and arm guards.

`(a, b, c) => body` — one arm matching any of several literals (all the same
kind: chars are Int32, so char classification lands here). `<arm> if cond =>
body` — a guard evaluated after the arm's binding; a failing guard falls
through to the NEXT arm. A guarded arm covers nothing for exhaustiveness, and
the else arm may not carry a guard (it must stay total).
"""
from __future__ import annotations

import contextlib
import io

import compiler as c

from tests.testutil import BatchedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


def _errors(src: str) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        c.compile([c.Input(src, "test.yafl")], use_stdlib=True, just_testing=True)
    return buf.getvalue()


_RUNTIME = """namespace Test
import System

fun classify(c: Int32): Int
  ret match(c)
    (' ' | 9i32 | 10i32) => 0
    ('0')              => 1
    ()                 => 2

fun bucket(n: Int): Int
  ret match(n)
    (0)       => 0
    (1 | 2 | 3) => 1
    ()        => 9

fun kind(v: Int|String): Int
  ret match(v)
    (x: Int) if x < 0 => 0
    (x: Int)          => 1
    (s: String) if s == "" => 2
    (s: String)       => 3

fun choose(b: Bool): Int|String
  ret b ? -5 : "hi"

fun strpick(s: String): Int
  ret match(s)
    ("a" | "b") => 0
    ()         => 1

fun main(): Int
  let ok1 = classify(' ') == 0 && classify(9i32) == 0 && classify('0') == 1 && classify('x') == 2
  let ok2 = bucket(0) == 0 && bucket(2) == 1 && bucket(7) == 9
  let ok3 = kind(choose(true)) == 0 && kind(choose(false)) == 3 && kind(7) == 1 && kind("") == 2
  let ok4 = strpick("b") == 0 && strpick("z") == 1
  ret ok1 && ok2 && ok3 && ok4 ? 0 : 1
"""


class TestMatchExtensionsRuntime(TestCase):
    def test_multi_literals_and_guards(self):
        rc, out = compile_and_run_stdlib_capture(_RUNTIME, timeout=60)
        self.assertEqual(0, rc, f"program failed; stdout:\n{out}")


_RANGES = """namespace Test
import System

fun digit(c: Int32): Int
  ret match(c)
    ('0' .. '9')             => 0
    ('a' .. 'z' | 'A' .. 'Z') => 1
    (' ' | 9i32)              => 2
    ()                       => 3

fun bucket(n: Int): Int
  ret match(n)
    (0 | 5 .. 7) => 0
    (1 .. 4)    => 1
    ()          => 2

# Unspaced `lo..hi` — the tokeniser's lookahead keeps `5.` from lexing as a
# float when the dot is the range symbol, so spacing is a style choice.
fun tight(n: Int): Int
  ret match(n)
    (5..7) => 0
    ()     => 1

fun tightc(c: Int32): Int
  ret match(c)
    ('a'..'z') => 0
    ()         => 1

fun main(): Int
  let ok1 = digit('5') == 0 && digit('q') == 1 && digit('Z') == 1 && digit(' ') == 2 && digit('!') == 3
  let ok2 = bucket(0) == 0 && bucket(6) == 0 && bucket(3) == 1 && bucket(9) == 2
  let ok3 = tight(6) == 0 && tight(9) == 1 && tightc('k') == 0 && tightc('K') == 1
  ret ok1 && ok2 && ok3 ? 0 : 1
"""


class TestMatchRanges(TestCase):
    def test_range_arms(self):
        rc, out = compile_and_run_stdlib_capture(_RANGES, timeout=60)
        self.assertEqual(0, rc, f"program failed; stdout:\n{out}")

    def test_range_on_string_subject_is_rejected(self):
        errs = _errors(_PRELUDE
            + "fun f(s: String): Int\n"
            + "  ret match(s)\n"
            + "    (\"a\" .. \"z\") => 0\n"
            + "    ()             => 1\n"
            + "fun main(): Int\n  ret f(\"q\")\n")
        self.assertTrue(errs.strip(), "expected an error for a string range")

    def test_empty_range_is_rejected(self):
        errs = _errors(_PRELUDE
            + "fun f(n: Int): Int\n"
            + "  ret match(n)\n"
            + "    (5 .. 1) => 0\n"
            + "    ()       => 1\n"
            + "fun main(): Int\n  ret f(3)\n")
        self.assertIn("range", errs.lower())


_FLOATS = """namespace Test
import System

fun fb(x: Float): Int
  ret match(x)
    (0.0)        => 0
    (1.0 .. 2.0) => 1
    (-1.0)       => 3
    ()           => 2

fun fc(x: Float32): Int
  ret match(x)
    (0.5f32 .. 1.5f32) => 0
    ()                 => 1

fun main(): Int
  let nan = 0.0 / 0.0
  let ok1 = fb(0.0) == 0 && fb(1.5) == 1 && fb(1.0) == 1 && fb(2.0) == 1 && fb(3.0) == 2 && fb(-1.0) == 3
  let ok2 = fb(nan) == 2
  let ok3 = fc(1.0f32) == 0 && fc(2.0f32) == 1
  ret ok1 && ok2 && ok3 ? 0 : 1
"""


class TestMatchFloats(TestCase):
    def test_float_literal_and_range_arms(self):
        # NaN matches no literal and no range — it lands in the else arm.
        rc, out = compile_and_run_stdlib_capture(_FLOATS, timeout=60)
        self.assertEqual(0, rc, f"program failed; stdout:\n{out}")

    def test_mixed_int_float_bounds_are_rejected(self):
        errs = _errors(_PRELUDE
            + "fun f(x: Float): Int\n"
            + "  ret match(x)\n"
            + "    (1 .. 2.0) => 0\n"
            + "    ()         => 1\n"
            + "fun main(): Int\n  ret f(1.5)\n")
        self.assertTrue(errs.strip(), "expected an error for mixed int/float bounds")


_PRELUDE = "namespace Test\nimport System\n"


class TestMatchExtensionsErrors(TestCase):
    def test_guard_on_else_arm_is_rejected(self):
        errs = _errors(_PRELUDE
            + "fun f(n: Int): Int\n"
            + "  ret match(n)\n"
            + "    (0) => 0\n"
            + "    () if n > 0 => 1\n"
            + "  ret 2\n"
            + "fun main(): Int\n  ret f(1)\n")
        self.assertIn("guard", errs.lower())

    def test_mixed_literal_kinds_in_one_arm_are_rejected(self):
        errs = _errors(_PRELUDE
            + "fun f(n: Int): Int\n"
            + "  ret match(n)\n"
            + "    (1 | \"a\") => 0\n"
            + "    ()        => 1\n"
            + "fun main(): Int\n  ret f(1)\n")
        self.assertTrue(errs.strip(), "expected an error for mixed literal kinds")

    def test_guarded_arms_do_not_satisfy_exhaustiveness(self):
        errs = _errors(_PRELUDE
            + "class A(x: Int)\nclass B(y: Int)\n"
            + "fun f(v: A|B): Int\n"
            + "  ret match(v)\n"
            + "    (a: A) if a.x > 0 => 0\n"
            + "    (b: B) => 1\n"
            + "fun main(): Int\n  ret f(B(1))\n")
        self.assertIn("non-exhaustive", errs)
