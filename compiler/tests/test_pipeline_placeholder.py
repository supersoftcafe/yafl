"""Pipeline placeholder: `x |> f(a, _)` slots the piped value into the `_`
argument position — a point-free stage needing no lambda. The `_` must be a
top-level argument of the stage's call, and at most one per stage. Lowered at
parse time to the same capture-avoiding block binding the lambda form uses.
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

fun scale(x: Int, factor: Int = 10, bias: Int = 1): Int
  ret x * factor + bias

fun main(): Int
  let a = 7 |> scale(_, 2)
  let b = 3 |> scale(2, _, 0)
  let c = 4 |> scale(_)
  let d = 7
    |> scale(_, 2)
    |> scale(_, 3)
  # Lambda stages are untouched by the placeholder — the two forms mix
  # freely in one pipeline.
  let f = 7
    |> scale(_, 2)
    |> (n) => n + 1
    |> scale(_, 1, 0)
  ret a == 15 && b == 6 && c == 41 && d == 46 && f == 16 ? 0 : 1
"""


class TestPipelinePlaceholderRuntime(TestCase):
    def test_placeholder_slots_the_piped_value(self):
        rc, out = compile_and_run_stdlib_capture(_RUNTIME, timeout=60)
        self.assertEqual(0, rc, f"program failed; stdout:\n{out}")


class TestPipelinePlaceholderErrors(TestCase):
    def test_two_placeholders_in_one_stage_are_rejected(self):
        errs = _errors(
            "namespace Test\nimport System\n"
            "fun add2(a: Int, b: Int): Int\n  ret a + b\n"
            "fun main(): Int\n  ret 7 |> add2(_, _)\n")
        self.assertIn("placeholder", errs.lower())
