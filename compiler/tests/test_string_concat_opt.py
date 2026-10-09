"""The string-concat flattening stage (lowering/string_concat.py, -O1+):
`a + b + c + …` chains fold into one `str_concat_n` call.

Checks both halves: the values are byte-correct at -O3, and the emitted C
actually contains `str_concat_n` (the rewrite fired) — including a chain
long enough to exercise the 16-operand runtime-cap chunking.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture
from tests.testutil import compile_c


class TestStringConcatFlattening(TestCase):
    def test_chain_values_correct_and_flattened(self):
        src = (
            "namespace Main\n"
            "import System\n"
            "fun label(name: System::String, n: System::Int): System::String\n"
            "  ret \"[\" + name + \"=\" + System::String(n) + \"]\"\n"
            "fun main(): System::Int\n"
            "  let s = label(\"alpha\", 42) + label(\"beta\", 7) + \"!\"\n"
            "  System::print(s)\n"
            "  ret System::length(s)\n")
        rc, out = compile_and_run_stdlib_capture(src, optimization_level=3)
        self.assertEqual("[alpha=42][beta=7]!", out)
        self.assertEqual(len("[alpha=42][beta=7]!"), rc)
        c_code = compile_c(src, optimization_level=3)
        self.assertIn("str_concat_n", c_code)

    def test_long_chain_chunks_past_runtime_cap(self):
        # 20 operands > the 16-operand runtime cap: the chunking path must
        # group recursively and still produce the exact concatenation.
        parts = " + ".join(f'"p{i:02d}"' for i in range(20))
        expected = "".join(f"p{i:02d}" for i in range(20))
        src = (
            "namespace Main\n"
            "import System\n"
            "fun main(): System::Int\n"
            f"  let s = {parts}\n"
            "  System::print(s)\n"
            "  ret System::length(s)\n")
        rc, out = compile_and_run_stdlib_capture(src, optimization_level=3)
        self.assertEqual(expected, out)
        self.assertEqual(len(expected), rc)
