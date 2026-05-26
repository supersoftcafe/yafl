"""Float + Constants residual tests.

Most of the original test_strings_floats has been consolidated into
mega-tests (test_arithmetic, test_comparisons, test_conversions,
test_parse, test_string_ops). What remains:

  * Float runtime: isNaN(real value) + literal-truncate round-trip,
    both rolled into one compile alongside the [const] inlining checks.
  * [const]-with-non-literal compile-error rejection: separate test
    because it asserts a *compile failure*, not a runtime value.
"""
from __future__ import annotations

import compiler as c
from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


_SRC = """\
namespace Main
import System

let [const] HALF: System::Float = 0.5

fun emit(label: System::String, value: System::Int): System::None
  System::print(label + "=" + System::String(value) + "\\n")
  ret None

fun main(): System::Int
  # ─── isNaN on a real value ─────────────────────────────────────────────
  let a: System::Float = 1.0
  emit("isNaN_real",   System::isNaN(a) ? 1 : 0)

  # ─── Float literal → Int truncation ────────────────────────────────────
  let f: System::Float = 3.5
  emit("trunc_3_5",    System::truncateToInt(f))     # 3

  # ─── User-defined [const] inlines ──────────────────────────────────────
  let v: System::Float = HALF
  emit("HALF_plus_HALF", System::truncateToInt(v + v))   # 1

  # ─── Stdlib PI is reachable and has the expected value ────────────────
  let r: System::Float = System::PI * 10.0
  emit("PI_times_10",   System::truncateToInt(r))    # 31

  # ─── TAU == 2*PI exactly (both [const] inlined literals) ──────────────
  emit("TAU_eq_2_PI",   System::PI + System::PI == System::TAU ? 1 : 0)

  ret 0
"""


_EXPECTED_LINES = [
    "isNaN_real=0",
    "trunc_3_5=3",
    "HALF_plus_HALF=1",
    "PI_times_10=31",
    "TAU_eq_2_PI=1",
]


class TestFloatAndConstantsRuntime(TestCase):
    def test_float_and_constants_runtime(self):
        rc, stdout = compile_and_run_stdlib_capture(_SRC, timeout=15)
        self.assertEqual(0, rc, f"program exited with {rc}; stdout:\n{stdout}")
        self.assertEqual(_EXPECTED_LINES, stdout.splitlines())


class TestConstWithNonLiteralRejected(TestCase):
    """`[const]` requires a literal value; a function-call initialiser is
    rejected at compile time. Can't share a compile with the runtime
    tests because the compile here is *expected* to fail."""

    def test_const_with_non_literal_is_rejected(self):
        src = """namespace Main
import System
fun zero(): System::Float
  ret 0.0
let [const] BAD: System::Float = zero()
fun main(): System::Int
  ret truncateToInt(BAD)
"""
        result = c.compile([c.Input(src, "test.yafl")], use_stdlib=True, just_testing=False)
        self.assertEqual("", result)
