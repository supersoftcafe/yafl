"""List construction on claimable segments (stdlib list.yafl, runtime
object.c "List segments"): append/prepend write a segment's spare slot in
place under a late pin, and a second extension of the same list value copies.
Verifies order and scale while GC cycles, promotion and compaction run during
construction, forks under GC pressure, and construction with poison enabled."""
from tests.testutil import BatchedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


class TestListSegments(TestCase):
    _TIMEOUT = 600

    def test_fill_across_promotion_then_minors(self):
        # Promote the half-built list once (a single forced major), then
        # continue appending under young churn only. The list must be
        # complete and ordered — a claim must land on the segment's CURRENT
        # copy, and a walk must resolve each segment it enters, or a stale
        # copy ends the list early or reads an unwritten slot.
        src = """import System
fun gcNudge(x: Int): Int
  ret __builtin_op__<bool>("gc_debug_major_now", x) ? x : x
fun [tail] waste(k: Int, acc: Int): Int
  ret k == 0 ? acc : waste(k - 1, acc + length(String(k + 1000000)))
fun [tail] fill(b: List<Int>, n: Int): List<Int>
  ret n == 0 ? b
    : n == 19900 ? fill(append(b, gcNudge(n)), n - 1)
    : fill(append(b, n + waste(40, 0) - 280), n - 1)
fun [tail] check(c: List<Int>, expect: Int): Int
  ret isEmpty(c) ? (expect == 0 ? 0 : 1)
    : first(c) == expect ? check(tail(c), expect - 1) : 2
fun main(): System::Int
  let xs = fill(List<Int>(), 20000)
  ret check(xs, 20000)
"""
        rc, out = compile_and_run_stdlib_capture(src, timeout=240)
        self.assertEqual(0, rc, f"promotion-then-minors list fill failed; stdout:\n{out}")

    def test_order_scale_and_gc(self):
        src = """import System

fun main(): System::Int
  # 100k elements: crosses many GC cycles; compaction churns while segments
  # are being filled and linked. Verify perfect order afterwards.
  fun [tail] fill(b: List<Int>, i: Int): List<Int>
    ret i >= 100000 ? b : fill(append(b, i), i + 1)
  let xs = fill(List<Int>(), 0)
  fun [tail] check(c: List<Int>, expect: Int): Int
    ret isEmpty(c) ? (expect == 100000 ? 0 : 1)
      : first(c) == expect ? check(tail(c), expect + 1) : 2
  # Two interleaved lists must not cross-link.
  fun [tail] fill2(a: List<Int>, b2: List<Int>, i: Int): (a2: List<Int>, b3: List<Int>)
    ret i >= 1000 ? (a, b2) : fill2(append(a, i), append(b2, 0 - i), i + 1)
  let pair = fill2(List<Int>(), List<Int>(), 0)
  let sa = fold(pair.a2, 0, (acc: Int, x: Int) => acc + x)
  let sb = fold(pair.b3, 0, (acc: Int, x: Int) => acc + x)
  ret check(xs, 0) + (sa + sb == 0 ? 0 : 4)
"""
        rc, _ = compile_and_run_stdlib_capture(src, timeout=120,
            env={"YAFL_GC_STEP_PAGES": "8", "YAFL_GC_POISON": "1"})
        self.assertEqual(0, rc)

    def test_forks_under_gc(self):
        # Every 7th step forks: the abandoned branch extends the SAME list
        # value the kept branch extends, so the kept branch's claim fails
        # every time and it must copy — under poison and a small GC step, so
        # the copies, claims and links all cross collections.
        src = """import System

fun main(): System::Int
  fun [tail] fill(b: List<Int>, i: Int, junk: Int): (l: List<Int>, junk: Int)
    ret i >= 3000 ? (l = b, junk = junk)
      : i % 7 == 0
        ? fill(append(b, i), i + 1, junk + size(append(b, 0 - i)))
        : fill(append(b, i), i + 1, junk)
  let r = fill(List<Int>(), 0, 0)
  fun [tail] check(c: List<Int>, expect: Int): Int
    ret isEmpty(c) ? (expect == 3000 ? 0 : 1)
      : first(c) == expect ? check(tail(c), expect + 1) : 2
  ret check(r.l, 0) + (r.junk > 0 ? 0 : 4)
"""
        rc, _ = compile_and_run_stdlib_capture(src, timeout=120,
            env={"YAFL_GC_STEP_PAGES": "8", "YAFL_GC_POISON": "1"})
        self.assertEqual(0, rc)
