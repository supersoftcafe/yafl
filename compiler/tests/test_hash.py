"""Consolidated hashOf test.

Checks the BasicEquality<T>.hashOf contract across all hashable types:
  * Returns >= 0 for every input.
  * Equal values hash equal (specifically +0.0 == -0.0 hash equal under
    Float and Float32).

A single generic wrapper threads `where BasicEquality<T>` so the trait
dispatches correctly for each width / type.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


_SRC = """\
import System

fun emit(label: System::String, value: System::Int): System::None
  print(label + "=" + String(value) + "\\n")
  ret None

fun _h<T>(v: T): System::Int where BasicEquality<T>
  ret hashOf(v)

# Check non-negativity by widening to bigint and using bigint compare —
# 0 - h < 1 iff h >= 0.
fun nonneg(h: System::Int): System::Int
  ret 0 - h < 1 ? 1 : 0

fun main(): System::Int
  # ─── Non-negative invariant per type ──────────────────────────────────
  emit("Int_pos",        nonneg(_h<Int>(42)))
  emit("Int_neg",        nonneg(_h<Int>(-42)))
  emit("Int8_min",       nonneg(_h<Int8>(INT8_MIN)))
  emit("Int16_min",      nonneg(_h<Int16>(INT16_MIN)))
  emit("Int32_pos",      nonneg(_h<Int32>(42i32)))
  emit("Int32_min",      nonneg(_h<Int32>(INT32_MIN)))
  emit("Int64_min",      nonneg(_h<Int64>(INT64_MIN)))
  emit("Float_pi",       nonneg(_h<Float>(3.14)))
  emit("Float32_pi",     nonneg(_h<Float32>(3.14f32)))
  emit("String_hello",   nonneg(_h<String>("hello")))
  # Bool has Show but no BasicEquality / hashOf — omit.

  # ─── +0.0 == -0.0 collapse: their hashes must agree ───────────────────
  emit("Float_pos_neg_zero_collide",   _h<Float>(0.0)    == _h<Float>(-0.0)    ? 1 : 0)
  emit("Float32_pos_neg_zero_collide", _h<Float32>(0.0f32) == _h<Float32>(-0.0f32) ? 1 : 0)

  # ─── Specific known value: hashOf(42i32) == 42 (current impl detail) ──
  emit("Int32_42_value", _h<Int32>(42i32) == 42 ? 1 : 0)

  ret 0
"""


_EXPECTED_LINES = [
    "Int_pos=1",
    "Int_neg=1",
    "Int8_min=1",
    "Int16_min=1",
    "Int32_pos=1",
    "Int32_min=1",
    "Int64_min=1",
    "Float_pi=1",
    "Float32_pi=1",
    "String_hello=1",
    "Float_pos_neg_zero_collide=1",
    "Float32_pos_neg_zero_collide=1",
    "Int32_42_value=1",
]


class TestAllHashOf(TestCase):
    def test_all_hashof_invariants(self):
        rc, stdout = compile_and_run_stdlib_capture(_SRC, timeout=15)
        self.assertEqual(0, rc, f"program exited with {rc}; stdout:\n{stdout}")
        self.assertEqual(_EXPECTED_LINES, stdout.splitlines())
