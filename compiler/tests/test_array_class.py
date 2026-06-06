"""The stdlib `Array<T>` class — a fixed-size, inline-storage sibling to
List<T> with O(1) indexed access via the `[]` operator.

`Array<T>(n, initFn)` builds the array by tabulating `initFn` over 0..n-1;
`a[i]` reads element i (aborting out of range). These tests exercise the
generic class end-to-end through the `[]` operator.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


class TestArrayClass(TestCase):
    def test_index_operator_reads_element(self):
        rc, out = compile_and_run_stdlib_capture("""import System
fun main(): System::Int
  let a = System::Array<System::Int32>(5i32, (i: System::Int32) => i * 2i32)
  ret System::Int(a[3i32])
""", timeout=30)
        self.assertEqual(6, rc, f"expected a[3] == 6; stdout:\n{out}")

    def test_length_field_is_accessible(self):
        rc, out = compile_and_run_stdlib_capture("""import System
fun main(): System::Int
  let a = System::Array<System::Int32>(7i32, (i: System::Int32) => i)
  ret System::Int(a.length)
""", timeout=30)
        self.assertEqual(7, rc, f"expected a.length == 7; stdout:\n{out}")

    def test_pointer_elements(self):
        # String elements exercise the GC write barrier in the fill and the
        # pointer-element read path through `[]`. The element is bound to a typed
        # `let` so `[]`'s generic T resolves from the expected type (a free
        # generic operator can't infer T from arguments alone).
        rc, out = compile_and_run_stdlib_capture("""import System
fun main(): System::Int
  let a = System::Array<System::String>(3i32, (i: System::Int32) => "abcd")
  let s: System::String = a[1i32]
  ret System::length(s)
""", timeout=30)
        self.assertEqual(4, rc, f"expected length(a[1]) == 4; stdout:\n{out}")

    def test_index_out_of_bounds_aborts(self):
        rc, out = compile_and_run_stdlib_capture("""import System
fun main(): System::Int
  let a = System::Array<System::Int32>(5i32, (i: System::Int32) => i)
  ret System::Int(a[10i32])
""", timeout=30)
        self.assertNotEqual(0, rc, "out-of-bounds `[]` must abort, not return normally")
