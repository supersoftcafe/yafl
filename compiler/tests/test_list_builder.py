"""ListBuilder: linear in-order construction on ordinary movable cells; the
tail-`next` write is a locking late init (runtime list_builder_link's
pin-resolve/store/unpin bracket + the [linear] stdlib wrapper). Verifies
order, scale (GC cycles + compaction run during construction), interleaved
builders, and construction across GC pressure with poison enabled."""
from tests.testutil import BatchedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


class TestListBuilder(TestCase):
    _TIMEOUT = 600

    def test_order_scale_and_gc(self):
        src = """import System

fun main(): System::Int
  # 100k elements: crosses many GC cycles; compaction churns while cells
  # are being linked. Verify perfect order afterwards.
  fun [tail] fill(b: ListBuilder<Int>, i: Int): ListBuilder<Int>
    ret i >= 100000 ? b : fill(push(b, i), i + 1)
  let xs = build(fill(builder<Int>(), 0))
  fun [tail] check(c: Chain<Int>, expect: Int): Int
    ret match(c)
      (nil: ChainEnd) => expect == 100000 ? 0 : 1
      (l: ChainLink)  => l.value == expect ? check(l.next, expect + 1) : 2
  # Two interleaved builders must not cross-link.
  fun [tail] fill2(a: ListBuilder<Int>, b2: ListBuilder<Int>, i: Int): (a2: ListBuilder<Int>, b3: ListBuilder<Int>)
    ret i >= 1000 ? (a, b2) : fill2(push(a, i), push(b2, 0 - i), i + 1)
  let pair = fill2(builder<Int>(), builder<Int>(), 0)
  fun [tail] sum(c: Chain<Int>, acc: Int): Int
    ret match(c)
      (nil: ChainEnd) => acc
      (l: ChainLink)  => sum(l.next, acc + l.value)
  let sa = sum(chain(build(pair.a2)), 0)
  let sb = sum(chain(build(pair.b3)), 0)
  ret check(chain(xs), 0) + (sa + sb == 0 ? 0 : 4)
"""
        rc, _ = compile_and_run_stdlib_capture(src, timeout=120,
            env={"YAFL_GC_STEP_PAGES": "8", "YAFL_GC_POISON": "1"})
        self.assertEqual(0, rc)
