"""Growable containers and the collector: every element must survive.

Array push and SeqBuilder push elements into storage filled across safe
points, and List.append links each new node onto the last with a pinned
compare-and-swap. Two hazards, one test each:

LONG BUILD (cycles). A build outlives root scans and whole cycles: the
elements pushed after a scan are newer than the array and reachable only
through it. The element stores are write-barriered like every other heap
store; there is no list of builders in flight. (Written for the thread-local
nursery, since removed, whose collections freed an element the array still
held when the store was barrier-free.) Run with the dwell between cycles and
without it, so builds straddle as many cycles as their work allows.

SUSPENDING PRODUCER (the snapshot). The producer forks, so builds straddle
global cycles. A grown Array copies into a fresh run and abandons the old
one; an element reachable at the snapshot only through the old run, and since
copied into a run allocated during the cycle (not traced this cycle), was
freed under it. The copy owes the snapshot barrier for the references it
carries. Before that, this aborted on every run.

Elements are large integers — real heap objects (small Ints are immediates
and single-field classes flatten to values, so neither can be lost). Freed
memory is poisoned so a lost element cannot pass for a plausible value.
"""
from __future__ import annotations

import os
import subprocess
import tempfile

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import _CLANG_BUILD_FLAGS, _RUN_ENV, static_link_for
from tests.testutil import compile_c

_LONG_SRC = (
    'import System\n'
    'import System::Containers\n'
    'fun big(): Int\n'
    '  ret 100000000000000000000000\n'
    'fun [tail] churn(n: Int, acc: Int): Int\n'
    '  ret n <= 0 ? acc : churn(n - 1, acc + big())\n'
    'fun elem(i: Int): Int\n'
    '  let g = churn(20, 0)\n'
    '  ret big() + i + g - big() * 20\n'
    'fun [tail] fillA(b: Array<Int>, i: Int, n: Int): Array<Int>\n'
    '  ret i >= n ? b : fillA(push<Int>(b, elem(i)), i + 1, n)\n'
    'fun [tail] sumA(a: Array<Int>, i: Int32, acc: Int): Int\n'
    '  ret i >= a.length ? acc : sumA(a, i + 1i32, (acc * 31 + a[i] - big()) % 1000000007)\n'
    'fun [tail] check(a: Array<Int>, i: Int32, bad: Int): Int\n'
    '  ret i >= a.length ? bad : check(a, i + 1i32, a[i] - big() == Int(i) ? bad : bad + 1)\n'
    'fun [tail] rounds(k: Int, bad: Int): Int\n'
    '  if k <= 0\n'
    '    ret bad\n'
    '  let a = fillA(Array<Int>(), 0, 50000)\n'
    '  ret rounds(k - 1, bad + check(a, 0i32, 0))\n'
    'fun main(): Int\n'
    '  let bad = rounds(10, 0)\n'
    '  System::print(String(bad))\n'
    '  ret bad > 0 ? 1 : 0\n'
)

_SUSPEND_SRC = (
    'import System\n'
    'import System::Containers\n'
    'fun big(): Int\n'
    '  ret 100000000000000000000000\n'
    'fun [tail] churn(n: Int, acc: Int): Int\n'
    '  ret n <= 0 ? acc : churn(n - 1, acc + big())\n'
    'fun [future] shifted(k: Int): Int\n'
    '  ret big() + k\n'
    'fun piece(i: Int): Int\n'
    '  let a = shifted(i)\n'
    '  let b = shifted(i * 3)\n'
    '  let g = churn(200, 0)\n'
    '  ret a + b + g - big() * 200\n'
    'fun plain(i: Int): Int\n'
    '  ret big() * 2 + i + i * 3\n'
    'fun [tail] fillA(b: Array<Int>, i: Int, n: Int, s: Bool): Array<Int>\n'
    '  ret i >= n ? b : fillA(push<Int>(b, s ? piece(i) : plain(i)), i + 1, n, s)\n'
    'fun [tail] sumA(a: Array<Int>, i: Int32, acc: Int): Int\n'
    '  ret i >= a.length ? acc : sumA(a, i + 1i32, (acc * 31 + a[i]) % 1000000007)\n'
    'fun arr(n: Int, s: Bool): Int\n'
    '  ret sumA(fillA(Array<Int>(), 0, n, s), 0i32, 0)\n'
    'fun [tail] fillS([terminal] b: SeqBuilder<Int>, i: Int, n: Int, s: Bool): SeqBuilder<Int>\n'
    '  ret i >= n ? b : fillS(push<Int>(b, s ? piece(i) : plain(i)), i + 1, n, s)\n'
    'fun [tail] sumS(x: Segment<Int>|None, i: Int32, acc: Int): Int\n'
    '  ret match(x)\n'
    '    (nil: None)         => acc\n'
    '    (seg: Segment<Int>) => i < seg.length ? sumS(x, i + 1i32, (acc * 31 + seg.array(i)) % 1000000007) : sumS(seg.next, 0i32, acc)\n'
    'fun seq(n: Int, s: Bool): Int\n'
    '  ret sumS(build<Int>(fillS(seqBuilder<Int>(), 0, n, s)), 0i32, 0)\n'
    'fun [tail] fillL(l: List<Int>, i: Int, n: Int, s: Bool): List<Int>\n'
    '  ret i >= n ? l : fillL(append<Int>(l, s ? piece(i) : plain(i)), i + 1, n, s)\n'
    'fun lst(n: Int, s: Bool): Int\n'
    '  ret fold<Int, Int>(fillL(List<Int>(), 0, n, s), 0, (acc: Int, x: Int) => (acc * 31 + x) % 1000000007)\n'
    'fun [tail] rounds(k: Int, bad: Int): Int\n'
    '  if k <= 0\n'
    '    ret bad\n'
    '  let okA = arr(100, true) == arr(100, false)\n'
    '  let okS = seq(100, true) == seq(100, false)\n'
    '  let okL = lst(100, true) == lst(100, false)\n'
    '  ret rounds(k - 1, okA && okS && okL ? bad : bad + 1)\n'
    'fun main(): Int\n'
    '  ret rounds(200, 0)\n'
)


class TestBuilderGc(TestCase):
    def _build(self, src: str, level: int) -> str:
        c_code = compile_c(src, optimization_level=level)
        with tempfile.NamedTemporaryFile(suffix="", delete=False) as tmp:
            binary = tmp.name
        built = subprocess.run(
            ["clang", "-g", "-x", "c", "-", "-O0", *_CLANG_BUILD_FLAGS,
             *static_link_for(level), "-o", binary],
            input=c_code, text=True, capture_output=True, timeout=60)
        self.assertEqual(0, built.returncode, built.stderr)
        return binary

    def _run(self, binary: str, **env: str) -> int:
        return subprocess.run([binary], capture_output=True, timeout=300,
                              stdin=subprocess.DEVNULL,
                              env={**_RUN_ENV, "YAFL_GC_POISON": "1", **env}).returncode

    def test_long_build_keeps_young_elements(self):
        for level in (0, 2):
            binary = self._build(_LONG_SRC, level)
            try:
                for idle in ("0", "64", "1024"):
                    with self.subTest(level=level, idle_pages=idle):
                        self.assertEqual(0, self._run(binary, YAFL_THREADS="1",
                                                      YAFL_GC_IDLE_PAGES=idle),
                                         "elements lost (or a crash)")
            finally:
                os.unlink(binary)

    def test_suspended_builders_keep_their_elements(self):
        for level in (0, 2):
            binary = self._build(_SUSPEND_SRC, level)
            try:
                for threads, idle in (("1", "0"), ("2", "0"), ("2", "1024")):
                    with self.subTest(level=level, threads=threads, idle_pages=idle):
                        self.assertEqual(0, self._run(binary, YAFL_THREADS=threads,
                                                      YAFL_GC_IDLE_PAGES=idle,
                                                      YAFL_GC_COMPACT_PERCENT="100"),
                                         "rounds that disagreed (or a crash)")
            finally:
                os.unlink(binary)
