"""stdlib Complex: a [final] (re, im) Float64 pair with value semantics.

`+` and `==`/hashOf are trait instances (generic BasicPlus/BasicEquality code
accepts Complex); `-`, `*`, `/`, conj, abs are plain operators — Complex has
no ordering, so it is deliberately NOT a BasicMath. The `im` field defaults
to 0.0 (`Complex(3.0)` is the real number 3 — the tuple-default machinery).
"""
from __future__ import annotations

from tests.testutil import BatchedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture

_RUNTIME = """namespace Test
import System

fun ceq(a: Complex, b: Complex): Bool
  ret a == b

fun ceq32(a: Complex32, b: Complex32): Bool
  ret a == b

fun main(): Int
  let z = Complex(3.0, 4.0)
  let w = Complex(1.0, -2.0)
  let ok1 = ceq(z + w, Complex(4.0, 2.0))
  let ok2 = ceq(z - w, Complex(2.0, 6.0))
  let ok3 = ceq(z * conj(z), Complex(25.0))
  let ok4 = ceq(z / z, Complex(1.0))
  let ok5 = abs(z) == 5.0
  let ok6 = ceq(-z, Complex(-3.0, -4.0))
  let ok7 = ceq(Complex(2.0), Complex(2.0, 0.0))
  let ok8 = ceq(I * I, Complex(-1.0))
  let ok9 = !ceq(z, w) && hashOf(z) >= 0i32
  let ok10 = isNaN(Complex(0.0 / 0.0, 1.0)) && !isNaN(z)
  # Complex is the 64-bit default, exactly as Float is Float64.
  let z64: Complex64 = z
  let ok11 = ceq(z64, z)
  # Complex32 mirrors the whole surface at Float32 width.
  let s = Complex32(3.0f32, 4.0f32)
  let t = Complex32(1.0f32, -2.0f32)
  let ok12 = ceq32(s + t, Complex32(4.0f32, 2.0f32))
  let ok13 = ceq32(s * conj(s), Complex32(25.0f32))
  let ok14 = abs(s) == 5.0f32
  let ok15 = ceq32(Complex32(2.0f32), Complex32(2.0f32, 0.0f32))
  let ok16 = ceq32(s / s, Complex32(1.0f32)) && hashOf(s) >= 0i32
  ret ok1 && ok2 && ok3 && ok4 && ok5 && ok6 && ok7 && ok8 && ok9 && ok10
      && ok11 && ok12 && ok13 && ok14 && ok15 && ok16 ? 0 : 1
"""


class TestComplex(TestCase):
    def test_complex_arithmetic(self):
        rc, out = compile_and_run_stdlib_capture(_RUNTIME, timeout=60)
        self.assertEqual(0, rc, f"complex arithmetic failed; stdout:\n{out}")

    def test_complex_arithmetic_optimised(self):
        rc, out = compile_and_run_stdlib_capture(_RUNTIME, timeout=60,
                                                 optimization_level=3)
        self.assertEqual(0, rc, f"complex arithmetic at -O3 failed; stdout:\n{out}")
