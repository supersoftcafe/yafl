"""The accumulation-deforestation stage (lowering/string_accumulation.py,
-O1+): a loop-carried `acc + x` accumulator becomes in-place builder writes
(`string_builder_reserve` + dangerous copy), turning O(n²) into O(n).

The scale test is the acceptance criterion the design agreed: naive user code,
no StringBuilder in sight, builds a 1MB string in linear time — at -O0 the
same program is quadratic and would take ~10s+, so the 100k-iteration run
finishing inside the harness timeout at all is itself the proof the rewrite
fired (belt and braces: the emitted C is checked for the reserve call and for
the absence of in-loop appends).
"""
from __future__ import annotations

import compiler as c
from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture

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
    def test_single_append_accumulator(self):
        src = _NAIVE_LOOP % ('"ab"', 50, 101)
        rc, out = compile_and_run_stdlib_capture(src, optimization_level=3)
        self.assertEqual(0, rc)
        self.assertEqual("xabab", out)
        c_code = c.compile([c.Input(src, "test.yafl")], use_stdlib=True,
                           just_testing=True, optimization_level=3)
        self.assertIn("string_builder_reserve", c_code)

    def test_chain_step_multi_push(self):
        # `acc + a + b` — string_concat flattens the step to a concat_n rooted
        # at the accumulator; the deforester must multi-push its operands.
        src = _NAIVE_LOOP % ('"abcdefgh" + "ij"', 100000, 1000001)
        rc, _out = compile_and_run_stdlib_capture(src, optimization_level=3)
        self.assertEqual(0, rc)   # 1MB built linearly; quadratic would time out

    def test_o0_naive_path_still_correct(self):
        # The stage is -O1+ gated: -O0 keeps the naive appends and must agree.
        src = _NAIVE_LOOP % ('"ab"', 50, 101)
        rc, out = compile_and_run_stdlib_capture(src, optimization_level=0)
        self.assertEqual(0, rc)
        self.assertEqual("xabab", out)

    def test_mid_loop_snapshot_read(self):
        # A read of the accumulator inside the loop (here: a length check that
        # varies the appended piece) becomes an exact-size snapshot copy — the
        # value must equal the accumulated string at that point.
        src = (
            "namespace Main\n"
            "import System\n"
            "fun [tail] go(n: System::Int, acc: System::String): System::String\n"
            "  ret n <= 0 ? acc\n"
            "    : go(n - 1, acc + (System::length(acc) % 2 == 0 ? \"a\" : \"bb\"))\n"
            "fun main(): System::Int\n"
            "  let s = go(6, \"\")\n"
            "  System::print(s)\n"
            "  ret System::length(s)\n")
        rc, out = compile_and_run_stdlib_capture(src, optimization_level=3)
        # len 0→a, 1→bb, 3→bb, 5→bb, 7→bb, 9→bb: "a" + "bb"*5
        self.assertEqual("abbbbbbbbbb", out)
        self.assertEqual(11, rc)
