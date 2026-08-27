"""The stdlib `Seq<T>` — an unrolled list: a chain of Segments, each one heap
object holding up to 16 elements inline. A sequence IS `Segment<T>|None`
(None is empty — there is deliberately no wrapper enum), built forwards with
SeqBuilder and consumed via fold/map/filter/any or the SeqStream instance.

Segment capacities ramp along the Fibonacci sequence 1, 1, 2, 3, 5, 8, 13 and
then stay at the 16 cap, so cumulative fill boundaries fall at 1, 2, 4, 7, 12,
20, 33, 49, 65, ... The boundary sweep below builds every size 0..55, which
exercises every ladder rung, exactly-full tails, fresh-tail-one-element pushes
and mid-segment build trims.

The builder pins the open tail from allocation until it is linked (non-tail)
or sealed (build/discard), so a fill that crosses safe points stores at a
stable address even as the collector compacts around it — the GC-interaction
tests force major cycles mid-fill, promote then churn minors, and park in an
async heap frame, mirroring the ArrayBuilder suite.
"""
from __future__ import annotations

import io
import contextlib

import compiler as c
from tests.testutil import BatchedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


class TestSeq(TestCase):
    _HDR = "namespace Main\nimport System\n"

    # Shared build-and-verify helpers: fill pushes 1..stop ascending; hSeq is
    # an order-sensitive positional hash via fold; hRef is the same recurrence
    # over the plain integers.
    _FILL = """\
fun [tail] fill(b: SeqBuilder<Int>, n: Int, stop: Int): SeqBuilder<Int>
  ret n > stop ? b : fill(push<Int>(b, n), n + 1, stop)
fun mkSeq(stop: Int): Segment<Int>|None
  ret build<Int>(fill(seqBuilder<Int>(), 1, stop))
fun hSeq(s: Segment<Int>|None): Int
  ret fold<Int, Int>(s, 7, (acc: Int, x: Int) => acc * 31 + x)
fun [tail] hRef(n: Int, stop: Int, acc: Int): Int
  ret n > stop ? acc : hRef(n + 1, stop, acc * 31 + n)
fun check(stop: Int): Bool
  ret hSeq(mkSeq(stop)) == hRef(1, stop, 7)
"""

    def test_single_element(self):
        # First-push path: one cap-1 segment that is both head and tail.
        rc, out = compile_and_run_stdlib_capture(self._HDR + self._FILL + """
fun main(): System::Int
  let s = mkSeq(1)
  ret !isEmpty<Int>(s) && hSeq(s) == 7 * 31 + 1 ? 0 : 1
""", timeout=30)
        self.assertEqual(0, rc, f"single-element seq failed; stdout:\n{out}")

    def test_empty_build(self):
        # A never-pushed builder allocated nothing; build makes NO seal call
        # and answers None, over which every combinator is a no-op.
        rc, out = compile_and_run_stdlib_capture(self._HDR + self._FILL + """
fun main(): System::Int
  let s = build<Int>(seqBuilder<Int>())
  ret isEmpty<Int>(s) && hSeq(s) == 7 ? 0 : 1
""", timeout=30)
        self.assertEqual(0, rc, f"empty build failed; stdout:\n{out}")

    def test_boundary_fills(self):
        # Every size 0..55: covers each Fibonacci rung (1,1,2,3,5,8,13,16),
        # every exactly-full tail (1,2,4,7,12,20,33,49), every fresh-tail
        # single element (3,5,8,13,21,34,50) and every mid-segment trim.
        rc, out = compile_and_run_stdlib_capture(self._HDR + self._FILL + """
fun [tail] checkUpTo(n: Int, stop: Int, bad: Int): Int
  ret n > stop ? bad : checkUpTo(n + 1, stop, bad + (check(n) ? 0 : 1))
fun main(): System::Int
  ret checkUpTo(0, 55, 0)
""", timeout=60)
        self.assertEqual(0, rc, f"{rc} boundary size(s) replayed wrongly; stdout:\n{out}")

    def test_stream_order_matches_fold(self):
        # Drain via the Stream instance across every kind of segment-boundary
        # hop and compare against the reference recurrence (fold agrees by
        # test_boundary_fills). Never owes no value, but Result's Error arm
        # is still spelled — the established Never-stream idiom.
        rc, out = compile_and_run_stdlib_capture(self._HDR + self._FILL + """
fun [tail] drainS(st: SeqStream<Int>, acc: Int): Int
  let r = streamNext<SeqStream<Int>, Int, Never>(st)
  ret match(r.value)
    (ok: Ok<Int | None, Never>) => match(ok.value)
      (x: Int)  => drainS(r.stream, acc * 31 + x)
      (n: None) => acc
    (er: Error<Int | None, Never>) => acc
fun checkStream(stop: Int): Bool
  ret drainS(seqStream<Int>(mkSeq(stop)), 7) == hRef(1, stop, 7)
fun main(): System::Int
  ret checkStream(0) && checkStream(1) && checkStream(21) && checkStream(33) && checkStream(50) ? 0 : 1
""", timeout=60)
        self.assertEqual(0, rc, f"stream drain mismatch; stdout:\n{out}")

    def test_stream_composes_with_map(self):
        # A SeqStream through the generic Map combinator: the trait constraint
        # discharges for the new source inside a conditional instance.
        rc, out = compile_and_run_stdlib_capture(self._HDR + self._FILL + """
fun [tail] drainM(st: Map<SeqStream<Int>, Int, Int, Never>, acc: Int): Int
  let r = streamNext<Map<SeqStream<Int>, Int, Int, Never>, Int, Never>(st)
  ret match(r.value)
    (ok: Ok<Int | None, Never>) => match(ok.value)
      (x: Int)  => drainM(r.stream, acc + x)
      (n: None) => acc
    (er: Error<Int | None, Never>) => acc
fun main(): System::Int
  let st = Map<SeqStream<Int>, Int, Int, Never>(seqStream<Int>(mkSeq(10)), (x: Int) => x * 2)
  ret drainM(st, 0) == 110 ? 0 : 1
""", timeout=30)
        self.assertEqual(0, rc, f"map-combinator drain failed; stdout:\n{out}")

    def test_pointer_elements(self):
        # String elements: pointer element masks, barrier-free fresh stores
        # over the zero fill, and a mid-segment trim (6 elements end inside
        # the cap-3 segment).
        rc, out = compile_and_run_stdlib_capture(self._HDR + """
fun [tail] fillS(b: SeqBuilder<String>, n: Int): SeqBuilder<String>
  ret n == 0 ? b : fillS(push<String>(b, String(n * 111)), n - 1)
fun main(): System::Int
  let s = build<String>(fillS(seqBuilder<String>(), 6))
  let cat = fold<String, String>(s, "", (acc: String, x: String) => acc + x)
  ret cat == "666555444333222111" ? 0 : 1
""", timeout=30)
        self.assertEqual(0, rc, f"pointer-element seq failed; stdout:\n{out}")

    def test_struct_elements(self):
        # A by-value tagged-struct element type (Result<Int,Int>) through the
        # inline store and read-back — coverage the Array suite lacks.
        rc, out = compile_and_run_stdlib_capture(self._HDR + """
fun [tail] fillR(b: SeqBuilder<Result<Int, Int>>, n: Int, stop: Int): SeqBuilder<Result<Int, Int>>
  ret n > stop ? b
    : fillR(push<Result<Int, Int>>(b, n == (n / 2) * 2 ? Ok<Int, Int>(n) : Error<Int, Int>(n * 100)), n + 1, stop)
fun scoreOf(x: Result<Int, Int>): Int
  ret match(x)
    (o: Ok<Int, Int>)    => o.value
    (e: Error<Int, Int>) => e.error
fun [tail] refR(n: Int, stop: Int, acc: Int): Int
  ret n > stop ? acc : refR(n + 1, stop, acc * 1000 + (n == (n / 2) * 2 ? n : n * 100))
fun main(): System::Int
  let s = build<Result<Int, Int>>(fillR(seqBuilder<Result<Int, Int>>(), 1, 9))
  let h = fold<Result<Int, Int>, Int>(s, 7, (acc: Int, x: Result<Int, Int>) => acc * 1000 + scoreOf(x))
  ret h == refR(1, 9, 7) ? 0 : 1
""", timeout=30)
        self.assertEqual(0, rc, f"struct-element seq failed; stdout:\n{out}")

    def test_int32_elements(self):
        # Pointer-free payload takes array_create's fast path, which skips the
        # element fill but must still zero the header — including `next`.
        rc, out = compile_and_run_stdlib_capture(self._HDR + self._FILL + """
fun [tail] fill32(b: SeqBuilder<Int32>, n: Int32, stop: Int32): SeqBuilder<Int32>
  ret n > stop ? b : fill32(push<Int32>(b, n), n + 1i32, stop)
fun main(): System::Int
  let s = build<Int32>(fill32(seqBuilder<Int32>(), 1i32, 21i32))
  let h = fold<Int32, Int>(s, 7, (acc: Int, x: Int32) => acc * 31 + Int(x))
  ret h == hRef(1, 21, 7) ? 0 : 1
""", timeout=30)
        self.assertEqual(0, rc, f"int32-element seq failed; stdout:\n{out}")

    def test_pushAll_list_and_seq(self):
        # Cross-container feeds: a List's elements pushed in traversal order,
        # then a Seq's own elements re-pushed (the concatenation primitive).
        rc, out = compile_and_run_stdlib_capture(self._HDR + self._FILL + """
fun main(): System::Int
  let l = prepend<Int>(1, prepend<Int>(2, prepend<Int>(3, List<Int>())))
  let s = build<Int>(pushAll<Int>(seqBuilder<Int>(), l))
  let s2 = build<Int>(pushAll<Int>(pushAll<Int>(seqBuilder<Int>(), s), l))
  let okList = hSeq(s) == ((7 * 31 + 1) * 31 + 2) * 31 + 3
  let okSeq = hSeq(s2) == (((((7 * 31 + 1) * 31 + 2) * 31 + 3) * 31 + 1) * 31 + 2) * 31 + 3
  ret okList && okSeq ? 0 : 1
""", timeout=30)
        self.assertEqual(0, rc, f"pushAll feeds failed; stdout:\n{out}")

    def test_combinators(self):
        # map/filter/any/isEmpty overloads; filter-to-nothing builds None.
        rc, out = compile_and_run_stdlib_capture(self._HDR + self._FILL + """
fun main(): System::Int
  let s = mkSeq(10)
  let doubled = map<Int, Int>(s, (x: Int) => x * 2)
  let evens = filter<Int>(s, (x: Int) => x == (x / 2) * 2)
  let okMap = fold<Int, Int>(doubled, 0, (a: Int, x: Int) => a + x) == 110
  let okFilter = fold<Int, Int>(evens, 0, (a: Int, x: Int) => a + x) == 30
  let okAny = any<Int>(s, (x: Int) => x == 7) && !any<Int>(s, (x: Int) => x == 11)
  let okEmpty = !isEmpty<Int>(s) && isEmpty<Int>(filter<Int>(s, (x: Int) => x > 100))
  ret okMap && okFilter && okAny && okEmpty ? 0 : 1
""", timeout=30)
        self.assertEqual(0, rc, f"combinator chain failed; stdout:\n{out}")

    def test_discard(self):
        # The failure-path counterpart of build: seals the tail empty and
        # releases its pin; the chain dies as ordinary garbage.
        rc, out = compile_and_run_stdlib_capture(self._HDR + """
fun afterDiscard(n: None): Int
  ret 0
fun main(): System::Int
  ret afterDiscard(discard<Int>(push<Int>(push<Int>(seqBuilder<Int>(), 7), 8)))
""", timeout=30)
        self.assertEqual(0, rc, f"discard failed; stdout:\n{out}")

    def test_discard_empty(self):
        # Discarding a never-pushed builder takes the no-runtime-call arm.
        rc, out = compile_and_run_stdlib_capture(self._HDR + """
fun afterDiscard(n: None): Int
  ret 0
fun main(): System::Int
  ret afterDiscard(discard<Int>(seqBuilder<Int>()))
""", timeout=30)
        self.assertEqual(0, rc, f"empty discard failed; stdout:\n{out}")

    def test_abandoned_builder_drops(self):
        # An unused builder is auto-released by the drops pass through the
        # ambient Drop instance — the third generic ambient Drop in the
        # stdlib, the combination that exposed the instance-resolution bug
        # the ArrayBuilder landing fixed. Without it this is a linearity
        # error; with it, the tail pin is not leaked.
        rc, out = compile_and_run_stdlib_capture(self._HDR + """
fun main(): System::Int
  let b = push<Int>(seqBuilder<Int>(), 1)
  ret 0
""", timeout=30)
        self.assertEqual(0, rc, f"abandoned-builder drop failed; stdout:\n{out}")

    def test_builder_is_linear(self):
        # Using a consumed builder again is a linearity error, not a program.
        src = self._HDR + """
fun main(): System::Int
  let b = seqBuilder<Int>()
  let b1 = push<Int>(b, 1)
  let b2 = push<Int>(b, 2)
  ret isEmpty<Int>(build<Int>(b1)) == isEmpty<Int>(build<Int>(b2)) ? 0 : 1
"""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            c_code = c.compile([c.Input(src, "t.yafl")], use_stdlib=True, just_testing=False)
        self.assertFalse(c_code, "double-use of a linear builder must not compile")

    def test_interleaved_builders(self):
        # Two live builders pushed alternately must keep their chains — and
        # their pinned tails — fully separate.
        rc, out = compile_and_run_stdlib_capture(self._HDR + self._FILL + """
fun [tail] fill2(ba: SeqBuilder<Int>, bb: SeqBuilder<Int>, n: Int, stop: Int): (a: Segment<Int>|None, b: Segment<Int>|None)
  ret n > stop
    ? (a=build<Int>(ba), b=build<Int>(bb))
    : fill2(push<Int>(ba, n), push<Int>(bb, n * 1000), n + 1, stop)
fun main(): System::Int
  let r = fill2(seqBuilder<Int>(), seqBuilder<Int>(), 1, 20)
  let okA = hSeq(r.a) == hRef(1, 20, 7)
  let okB = fold<Int, Int>(r.b, 7, (acc: Int, x: Int) => acc * 31 + x / 1000) == hRef(1, 20, 7)
  ret okA && okB ? 0 : 1
""", timeout=30)
        self.assertEqual(0, rc, f"interleaved builders failed; stdout:\n{out}")

    def test_fill_across_forced_major_cycles(self):
        # The half-built chain crosses full GC cycles: a forced major before
        # every push makes the collector trace the pinned open tail (length
        # still reading capacity, unwritten slots as NULLs) and compact
        # everything around it — across seven links' worth of segments. The
        # nudge's result feeds the pushed value so no pass can discard it.
        rc, out = compile_and_run_stdlib_capture(self._HDR + """
fun gcNudge(x: Int): Int
  ret __builtin_op__<bool>("gc_debug_major_now", x) ? x : x
fun [tail] fillG(b: SeqBuilder<String>, n: Int): SeqBuilder<String>
  let b2 = push<String>(b, String(gcNudge(n) * 111))
  ret n == 1 ? b2 : fillG(b2, n - 1)
fun [tail] refCat(n: Int, acc: String): String
  ret n == 0 ? acc : refCat(n - 1, acc + String(n * 111))
fun main(): System::Int
  let s = build<String>(fillG(seqBuilder<String>(), 40))
  let cat = fold<String, String>(s, "", (acc: String, x: String) => acc + x)
  ret cat == refCat(40, "") ? 0 : 1
""", timeout=60)
        self.assertEqual(0, rc, f"fill across forced majors failed; stdout:\n{out}")

    def test_fill_across_promotion_then_minors(self):
        # Promote the half-built chain once (a single forced major), then
        # keep pushing under young-generation churn only; verify every
        # element by position through fold.
        rc, out = compile_and_run_stdlib_capture(self._HDR + """
fun gcNudge(x: Int): Int
  ret __builtin_op__<bool>("gc_debug_major_now", x) ? x : x
fun [tail] waste(k: Int, acc: Int): Int
  ret k == 0 ? acc : waste(k - 1, acc + length(String(k + 1000000)))
fun [tail] fillP(b: SeqBuilder<Int>, n: Int): SeqBuilder<Int>
  ret n == 0 ? b
    : n == 3900 ? fillP(push<Int>(b, gcNudge(n)), n - 1)
    : fillP(push<Int>(b, n + waste(40, 0) - 280), n - 1)
fun step(acc: (expect: Int, bad: Int), x: Int): (expect: Int, bad: Int)
  ret (expect=acc.expect - 1, bad=acc.bad + (x == acc.expect ? 0 : 1))
fun main(): System::Int
  let s = build<Int>(fillP(seqBuilder<Int>(), 4000))
  let r = fold<Int, (expect: Int, bad: Int)>(s, (expect=4000, bad=0), step)
  ret r.bad == 0 && r.expect == 0 ? 0 : 1
""", timeout=120)
        self.assertEqual(0, rc, f"promotion-then-minors fill failed; stdout:\n{out}")

    def test_async_fill_across_forced_major_cycles(self):
        # The motivating scenario for the pin: the producer contains a
        # [future] read, so async lowering gives it a heap frame — the
        # flattened builder's two segment pointers are saved and reloaded
        # across parks while forced majors compact around the pinned tail.
        rc, out = compile_and_run_stdlib_capture(self._HDR + """
fun gcNudge(x: Int): Int
  ret __builtin_op__<bool>("gc_debug_major_now", x) ? x : x
fun slowValue(n: Int): String
  ret String(gcNudge(n) * 111)
fun [tail] fillA(b: SeqBuilder<String>, n: Int): SeqBuilder<String>
  let [future] s = slowValue(n)
  let b2 = push<String>(b, s)
  ret n == 1 ? b2 : fillA(b2, n - 1)
fun [tail] refCat(n: Int, acc: String): String
  ret n == 0 ? acc : refCat(n - 1, acc + String(n * 111))
fun main(): System::Int
  let s = build<String>(fillA(seqBuilder<String>(), 12))
  let cat = fold<String, String>(s, "", (acc: String, x: String) => acc + x)
  ret cat == refCat(12, "") ? 0 : 1
""", timeout=60)
        self.assertEqual(0, rc, f"async fill across forced majors failed; stdout:\n{out}")

    def test_order_scale_gc_poison(self):
        # 100k elements (≈6,250 segments) under tight incremental pacing and
        # GC poison: position-weighted checksum pins complete in-order
        # replay. Sum k*x_k with x_k = k is n(n+1)(2n+1)/6.
        rc, out = compile_and_run_stdlib_capture(self._HDR + """
fun [tail] fillBig(b: SeqBuilder<Int>, n: Int, stop: Int): SeqBuilder<Int>
  ret n > stop ? b : fillBig(push<Int>(b, n), n + 1, stop)
fun step(acc: (k: Int, sum: Int), x: Int): (k: Int, sum: Int)
  ret (k=acc.k + 1, sum=acc.sum + acc.k * x)
fun main(): System::Int
  let s = build<Int>(fillBig(seqBuilder<Int>(), 1, 100000))
  let r = fold<Int, (k: Int, sum: Int)>(s, (k=1, sum=0), step)
  ret r.sum == 333338333350000 && r.k == 100001 ? 0 : 1
""", timeout=300, env={"YAFL_GC_STEP_PAGES": "8", "YAFL_GC_POISON": "1"})
        self.assertEqual(0, rc, f"100k poison run failed; stdout:\n{out}")
