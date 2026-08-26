"""The stdlib `Array<T>` class — a fixed-size, inline-storage sibling to
List<T> with O(1) indexed access via the `[]` operator.

`Array<T>(n, initFn)` builds the array by tabulating `initFn` over 0..n-1;
`a[i]` reads element i (aborting out of range). These tests exercise the
generic class end-to-end through the `[]` operator.

ArrayBuilder<T> is the linear incremental constructor: allocate at an
estimated capacity, push, and build() publishes by SHORTENING length from
capacity to the filled count. The array is pinned from allocation to seal so
a fill that crosses safe points (an async producer parks in a heap frame)
stores at a stable address even if the collector compacts around it — the
GC-interaction tests below force major cycles mid-fill to exercise exactly
that, including the scanner tracing the zero-filled unwritten tail of a
half-built pointer array.
"""
from __future__ import annotations

import io
import contextlib

import compiler as c
from tests.testutil import BatchedTestCase as TestCase
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


class TestArrayBuilder(TestCase):
    _HDR = "namespace Main\nimport System\n"

    _FILL = """\
fun [tail] fill(b: ArrayBuilder<Int>, n: Int): ArrayBuilder<Int>
  ret n == 0 ? b : fill(push<Int>(b, n), n - 1)
"""

    def test_exact_estimate_no_growth(self):
        # Estimate == push count: the initial run is filled precisely and
        # sealed from capacity down to itself.
        rc, out = compile_and_run_stdlib_capture(self._HDR + self._FILL + """
fun main(): System::Int
  let a = build<Int>(fill(arrayBuilder<Int>(5), 5))
  ret a.length == 5i32 && a[0] == 5 && a[4] == 1 ? 0 : 1
""", timeout=30)
        self.assertEqual(0, rc, f"exact-estimate build failed; stdout:\n{out}")

    def test_growth_path(self):
        # Estimate 4, ten pushes: capacity doubles 4 -> 8 -> 16, elements are
        # copied across, the abandoned runs are sealed empty, and the final
        # seal shortens 16 down to 10.
        rc, out = compile_and_run_stdlib_capture(self._HDR + self._FILL + """
fun main(): System::Int
  let a = build<Int>(fill(arrayBuilder<Int>(4), 10))
  ret a.length == 10i32 && a[0] == 10 && a[5] == 5 && a[9] == 1 ? 0 : 1
""", timeout=30)
        self.assertEqual(0, rc, f"growth-path build failed; stdout:\n{out}")

    def test_zero_estimate_clamps(self):
        # A hopeless estimate still works: cap clamps to 1 and growth does
        # the rest.
        rc, out = compile_and_run_stdlib_capture(self._HDR + self._FILL + """
fun main(): System::Int
  let a = build<Int>(fill(arrayBuilder<Int>(0), 3))
  ret a.length == 3i32 && a[0] == 3 && a[2] == 1 ? 0 : 1
""", timeout=30)
        self.assertEqual(0, rc, f"zero-estimate build failed; stdout:\n{out}")

    def test_empty_build(self):
        # No pushes: build seals length to 0; the capacity-sized run was all
        # zeros throughout.
        rc, out = compile_and_run_stdlib_capture(self._HDR + """
fun main(): System::Int
  let a = build<Int>(arrayBuilder<Int>(8))
  ret a.length == 0i32 ? 0 : 1
""", timeout=30)
        self.assertEqual(0, rc, f"empty build failed; stdout:\n{out}")

    def test_discard(self):
        # The failure-path counterpart: consumes the builder, seals empty.
        rc, out = compile_and_run_stdlib_capture(self._HDR + """
fun afterDiscard(n: None): Int
  ret 0
fun main(): System::Int
  ret afterDiscard(discard<Int>(push<Int>(arrayBuilder<Int>(2), 7)))
""", timeout=30)
        self.assertEqual(0, rc, f"discard failed; stdout:\n{out}")

    def test_abandoned_builder_drops(self):
        # An unused builder is auto-released by the drops pass through the
        # ambient Drop instance (which seals and unpins). Without it this
        # program is a linearity error; with it, the pin is not leaked.
        rc, out = compile_and_run_stdlib_capture(self._HDR + """
fun main(): System::Int
  let b = push<Int>(arrayBuilder<Int>(4), 1)
  ret 0
""", timeout=30)
        self.assertEqual(0, rc, f"abandoned-builder drop failed; stdout:\n{out}")

    def test_pointer_elements(self):
        # String elements through push and read-back: the builder's stores
        # are barrier-free fresh stores over the allocator's zero fill.
        rc, out = compile_and_run_stdlib_capture(self._HDR + """
fun [tail] fillS(b: ArrayBuilder<String>, n: Int): ArrayBuilder<String>
  ret n == 0 ? b : fillS(push<String>(b, String(n * 111)), n - 1)
fun main(): System::Int
  let a = build<String>(fillS(arrayBuilder<String>(2), 6))
  let first: String = a[0]
  let last: String = a[5]
  ret a.length == 6i32 && first == "666" && last == "111" ? 0 : 1
""", timeout=30)
        self.assertEqual(0, rc, f"pointer-element build failed; stdout:\n{out}")

    def test_combinators(self):
        # map/fold/isEmpty overloads. map's closure captures (a, f), so the
        # ctor fill loop's call is not sync-provable and the loop becomes an
        # async state machine whose BACK-EDGE Jump is the function's final op
        # — the shape that exposed the last-op special case in async_lower's
        # liveness (the loop-carried length var wasn't saved across the park).
        rc, out = compile_and_run_stdlib_capture(self._HDR + """
fun main(): System::Int
  let a = Array<Int>(5i32, (i: Int32) => Int(i) * 3)
  let doubled = map<Int, Int>(a, (x: Int) => x * 2)
  let total = fold<Int, Int>(doubled, 0, (acc: Int, x: Int) => acc + x)
  ret isEmpty<Int>(a) ? 1 : (total == 60 ? 0 : 2)
""", timeout=30)
        self.assertEqual(0, rc, f"combinator chain failed; stdout:\n{out}")

    def test_builder_is_linear(self):
        # Using a consumed builder again is a linearity error, not a program.
        src = self._HDR + """
fun main(): System::Int
  let b = arrayBuilder<Int>(2)
  let b1 = push<Int>(b, 1)
  let b2 = push<Int>(b, 2)
  ret build<Int>(b1).length == build<Int>(b2).length ? 0 : 1
"""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            c_code = c.compile([c.Input(src, "t.yafl")], use_stdlib=True, just_testing=False)
        self.assertFalse(c_code, "double-use of a linear builder must not compile")

    def test_fill_across_forced_major_cycles(self):
        # The half-built array crosses full GC cycles: before every push the
        # program requests a major and takes a safe point (gc_debug_major_now),
        # so the collector repeatedly traces the array while length still
        # reads capacity — walking pushed Strings AND the zero-filled
        # unwritten tail — and any compaction moves everything around the
        # pinned array. The nudge's result feeds the pushed value so no pass
        # can discard the call.
        rc, out = compile_and_run_stdlib_capture(self._HDR + """
fun gcNudge(x: Int): Int
  ret __builtin_op__<bool>("gc_debug_major_now", x) ? x : x
fun [tail] fillG(b: ArrayBuilder<String>, n: Int): ArrayBuilder<String>
  let b2 = push<String>(b, String(gcNudge(n) * 111))
  ret n == 1 ? b2 : fillG(b2, n - 1)
fun main(): System::Int
  let a = build<String>(fillG(arrayBuilder<String>(3), 12))
  let first: String = a[0]
  let mid: String = a[6]
  let last: String = a[11]
  ret a.length == 12i32 && first == "1332" && mid == "666" && last == "111" ? 0 : 1
""", timeout=60)
        self.assertEqual(0, rc, f"fill across forced majors failed; stdout:\n{out}")

    def test_fill_across_promotion_then_minors(self):
        # Promote the half-built array's storage once (a single forced
        # major), then keep pushing under young-generation churn only. The
        # sealed result is read back in full — stale mirrors of the run must
        # resolve relocation ([pinnable]) rather than read pre-store slots.
        rc, out = compile_and_run_stdlib_capture(self._HDR + """
fun gcNudge(x: Int): Int
  ret __builtin_op__<bool>("gc_debug_major_now", x) ? x : x
fun [tail] waste(k: Int, acc: Int): Int
  ret k == 0 ? acc : waste(k - 1, acc + length(String(k + 1000000)))
fun [tail] fillP(b: ArrayBuilder<Int>, n: Int): ArrayBuilder<Int>
  ret n == 0 ? b
    : n == 3900 ? fillP(push<Int>(b, gcNudge(n)), n - 1)
    : fillP(push<Int>(b, n + waste(40, 0) - 280), n - 1)
fun [tail] checkAll(a: Array<Int>, i: Int, bad: Int): Int
  ret i >= 4000 ? bad
    : checkAll(a, i + 1, bad + (a[i] == 4000 - i ? 0 : 1))
fun main(): System::Int
  let a = build<Int>(fillP(arrayBuilder<Int>(64), 4000))
  ret a.length == 4000i32 ? checkAll(a, 0, 0) : 0 - 1
""", timeout=120)
        self.assertEqual(0, rc, f"promotion-then-minors fill failed; stdout:\n{out}")

    def test_async_fill_across_forced_major_cycles(self):
        # The motivating scenario for the pin: the producer contains a
        # [future] read, so async lowering gives it a heap frame and the
        # half-built array is live across suspension points while forced
        # majors run. Pinned, every store lands in the real array.
        rc, out = compile_and_run_stdlib_capture(self._HDR + """
fun gcNudge(x: Int): Int
  ret __builtin_op__<bool>("gc_debug_major_now", x) ? x : x
fun slowValue(n: Int): String
  ret String(gcNudge(n) * 111)
fun [tail] fillA(b: ArrayBuilder<String>, n: Int): ArrayBuilder<String>
  let [future] s = slowValue(n)
  let b2 = push<String>(b, s)
  ret n == 1 ? b2 : fillA(b2, n - 1)
fun main(): System::Int
  let a = build<String>(fillA(arrayBuilder<String>(3), 12))
  let first: String = a[0]
  let mid: String = a[6]
  let last: String = a[11]
  ret a.length == 12i32 && first == "1332" && mid == "666" && last == "111" ? 0 : 1
""", timeout=60)
        self.assertEqual(0, rc, f"async fill across forced majors failed; stdout:\n{out}")
