"""Loop-carried String accumulation: `acc + x` in a [tail] loop is linear.

It used to be made linear by a compiler stage (lowering/string_accumulation.py,
now retired) that deforested the loop into in-place builder writes. A String
is now a VALUE that extends its own head buffer in place whenever it owns the
end of it (yafllib/str.c), so naive user code is linear with no rewrite: the
accumulator's appends ARE the builder.

The runtime checks, the 1MB linear-time build included, are [test]s in
compiler/yafl_tests/string_accumulation.yafl. Here: the loop appends in the C,
and the in-place extension survives compaction relocating the buffer while the
loop is suspended (which needs the GC environment set for the run).

Runtime behaviour is checked by compiler/yafl_tests/string_accumulation.yafl.
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import _CLANG_BUILD_FLAGS, _RUN_ENV, static_link_for
from tests.testutil import compile_c

_NAIVE_LOOP = (
    "namespace Main\n"
    "import System\n"
    "fun [tail] go(n: System::Int, acc: System::String): System::String\n"
    "  ret n <= 0 ? acc : go(n - 1, acc + %s)\n"
    "fun main(): System::Int\n"
    "  let s = go(%d, \"x\")\n"
    "  System::print(System::slice(s, 0, 5))\n"
    "  ret System::length(s) == %d ? 0 : 1\n")


class TestStringAccumulation(TestCase):
    def test_accumulator_appends_in_place(self):
        src = _NAIVE_LOOP % ('"ab"', 50, 101)
        c_code = compile_c(src, optimization_level=3)
        # The loop appends String values directly.
        self.assertTrue("str_append" in c_code or "str_concat_n" in c_code)

    def test_buffer_survives_compaction_across_a_suspension(self):
        # The loop's piece comes from a function that forks, so the loop
        # suspends between appends and its buffer is parked in a heap frame,
        # reachable from no stack. Compaction may relocate anything parked
        # like that — unless it is pinned — and the next in-place append then
        # writes a stale copy. `straight` builds the same text without ever
        # suspending; every round must agree with it. Compaction is forced on
        # every cycle so the window is hit rather than hoped for.
        src = (
            "import System\n"
            "fun piece(i: Int): String\n"
            "  let (a, b) = __parallel__(() => String(i), () => String(i + 1))\n"
            "  ret a + \",\" + b + \";\"\n"
            "fun plain(i: Int): String\n"
            "  ret String(i) + \",\" + String(i + 1) + \";\"\n"
            "fun [tail] suspending(i: Int, n: Int, acc: String): String\n"
            "  ret i >= n ? acc : suspending(i + 1, n, acc + piece(i))\n"
            "fun [tail] straight(i: Int, n: Int, acc: String): String\n"
            "  ret i >= n ? acc : straight(i + 1, n, acc + plain(i))\n"
            "fun [tail] rounds(k: Int, bad: Int): Int\n"
            "  if k <= 0\n"
            "    ret bad\n"
            "  let ok = suspending(0, 3000, \"\") == straight(0, 3000, \"\")\n"
            "  ret rounds(k - 1, ok ? bad : bad + 1)\n"
            "fun main(): Int\n"
            "  ret rounds(40, 0)\n")
        c_code = compile_c(src, optimization_level=2)
        # The suspending loop itself must append to its String accumulator,
        # or the run below proves nothing about in-place extension.
        head = re.search(r"^(?:object_t\*|str_t) Main__suspending_\w+\(.*\)\n\{", c_code, re.MULTILINE)
        self.assertIsNotNone(head)
        body = c_code[head.end():c_code.index("\n}\n", head.end())]
        self.assertTrue("str_append" in body or "str_concat_n" in body)
        with tempfile.NamedTemporaryFile(suffix="", delete=False) as tmp:
            binary = tmp.name
        try:
            built = subprocess.run(
                ["clang", "-g", "-x", "c", "-", "-O0", *_CLANG_BUILD_FLAGS,
                 *static_link_for(2), "-o", binary],
                input=c_code, text=True, capture_output=True, timeout=60)
            self.assertEqual(0, built.returncode, built.stderr)
            run = subprocess.run(
                [binary], capture_output=True, timeout=60, stdin=subprocess.DEVNULL,
                env={**_RUN_ENV, "YAFL_THREADS": "2", "YAFL_GC_COMPACT_PERCENT": "100"})
            self.assertEqual(0, run.returncode, "rounds that disagreed")
        finally:
            os.unlink(binary)
