"""List append under GC: each append links a new node after the list's last
node with a pinned compare-and-swap. Verifies order, scale (GC cycles and
compaction run during construction), two lists grown in step, and
construction across GC pressure with poison enabled.

Runtime behaviour is also checked by compiler/yafl_tests/list_append.yafl.
"""
from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


class TestListAppend(TestCase):
    _TIMEOUT = 600


    def test_order_scale_and_gc(self):
        src = """import System
import System::Containers

fun main(): System::Int
  # 100k elements: crosses many GC cycles; compaction churns while nodes
  # are being linked. Verify perfect order afterwards.
  fun [tail] fill(l: List<Int>, i: Int): List<Int>
    ret i >= 100000 ? l : fill(append(l, i), i + 1)
  let xs = fill(List<Int>(), 0)
  # Counts up from 0; a wrong element sticks at -1.
  fun check(l: List<Int>): Int
    let next = fold(l, 0, (e: Int, x: Int) => e >= 0 && x == e ? e + 1 : 0 - 1)
    ret next == 100000 ? 0 : next < 0 ? 2 : 1
  # Two lists grown in step must not cross-link.
  fun [tail] fill2(a: List<Int>, b: List<Int>, i: Int): (a2: List<Int>, b2: List<Int>)
    ret i >= 1000 ? (a, b) : fill2(append(a, i), append(b, 0 - i), i + 1)
  let pair = fill2(List<Int>(), List<Int>(), 0)
  fun sum(l: List<Int>): Int
    ret fold(l, 0, (acc: Int, x: Int) => acc + x)
  ret check(xs) + (sum(pair.a2) + sum(pair.b2) == 0 ? 0 : 4)
"""
        rc, _ = compile_and_run_stdlib_capture(src, timeout=120,
            env={"YAFL_GC_STEP_PAGES": "8", "YAFL_GC_POISON": "1"})
        self.assertEqual(0, rc)
