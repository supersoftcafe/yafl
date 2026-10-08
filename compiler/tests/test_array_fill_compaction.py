"""Array tabulation across a suspension must survive compaction.

`Array<T>(n, (i) => f(i))` allocates the array, then calls the init function
once per element and stores the result. When the init function suspends (here
it forks with `__parallel__`), the fill loop's frame — the half-built array
among it — is parked in a heap state object, reachable from no stack. Nothing
stops compaction from relocating the array then, and on resume the loop
reloads the OLD address from its state and keeps storing into it: the
elements end up split between the stale original and the relocated copy, and
whichever copy a reader reaches is missing some of them.

The array must stay put until its initialisation is finished — pinned — as the
String accumulator's in-place buffer already is (test_string_accumulation.py,
test_buffer_survives_compaction_across_a_suspension, the model for this test).

`straight` builds the same array without ever suspending; every round must
agree with it. Two workers and the default compaction threshold already hit
the window every run; forcing compaction on every cycle makes certain of it.
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile

import compiler as c
from tests.testutil import BatchedTestCase as TestCase
from tests.testutil import _CLANG_BUILD_FLAGS, _RUN_ENV, static_link_for

_SRC = (
    "import System\n"
    "class Box(v: Int)\n"
    "fun piece(i: Int32): Box\n"
    "  let (a, b) = __parallel__(() => Box(Int(i)), () => Box(Int(i) * 3))\n"
    "  ret Box(a.v + b.v)\n"
    "fun plain(i: Int32): Box\n"
    "  ret Box(Int(i) + Int(i) * 3)\n"
    "fun suspending(n: Int32): Array<Box>\n"
    "  ret Array<Box>(n, (i: Int32) => piece(i))\n"
    "fun straight(n: Int32): Array<Box>\n"
    "  ret Array<Box>(n, (i: Int32) => plain(i))\n"
    "fun [tail] same(a: Array<Box>, b: Array<Box>, i: Int32): Bool\n"
    "  ret i >= a.length ? true : (a[i].v == b[i].v ? same(a, b, i + 1i32) : false)\n"
    "fun [tail] rounds(k: Int, bad: Int): Int\n"
    "  if k <= 0\n"
    "    ret bad\n"
    "  let ok = same(suspending(200i32), straight(200i32), 0i32)\n"
    "  ret rounds(k - 1, ok ? bad : bad + 1)\n"
    "fun main(): Int\n"
    "  ret rounds(200, 0)\n")


class TestArrayFillCompaction(TestCase):
    def _build(self, level: int) -> tuple[str, str]:
        c_code = c.compile([c.Input(_SRC, "test.yafl")], use_stdlib=True,
                           just_testing=True, optimization_level=level)
        # The suspending fill must really be a parked state machine, or the
        # run below proves nothing about a fill that outlives its stack frame.
        self.assertIsNotNone(
            re.search(r"^void Main__suspending_\w+_async\(", c_code, re.MULTILINE),
            "the suspending fill did not become an $async state machine")
        with tempfile.NamedTemporaryFile(suffix="", delete=False) as tmp:
            binary = tmp.name
        built = subprocess.run(
            ["clang", "-g", "-x", "c", "-", "-O0", *_CLANG_BUILD_FLAGS,
             *static_link_for(level), "-o", binary],
            input=c_code, text=True, capture_output=True, timeout=60)
        self.assertEqual(0, built.returncode, built.stderr)
        return binary, c_code

    def _run(self, binary: str, compact_percent: str) -> int:
        run = subprocess.run(
            [binary], capture_output=True, timeout=120, stdin=subprocess.DEVNULL,
            env={**_RUN_ENV, "YAFL_THREADS": "2", "YAFL_GC_COMPACT_PERCENT": compact_percent})
        return run.returncode

    def test_suspended_fill_survives_compaction(self):
        for level in (0, 2):
            binary, _ = self._build(level)
            try:
                for pct in ("33", "100"):   # the default threshold, and every page
                    with self.subTest(level=level, compact_percent=pct):
                        self.assertEqual(0, self._run(binary, pct),
                                         "rounds that disagreed (or a crash)")
            finally:
                os.unlink(binary)
