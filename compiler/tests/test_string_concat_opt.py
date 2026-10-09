"""The string-concat flattening stage (lowering/string_concat.py, -O1+):
`a + b + c + …` chains fold into one `str_concat_n` call.

This checks the rewrite fires in the emitted C. That the values are
byte-correct, past the 16-operand runtime cap included, is checked by
compiler/yafl_tests/string_concat_opt.yafl at -O0 and -O3.

Runtime behaviour is checked by compiler/yafl_tests/string_concat_opt.yafl.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_c


class TestStringConcatFlattening(TestCase):
    def test_chain_is_flattened(self):
        src = (
            "namespace Main\n"
            "import System\n"
            "fun label(name: System::String, n: System::Int): System::String\n"
            "  ret \"[\" + name + \"=\" + System::String(n) + \"]\"\n"
            "fun main(): System::Int\n"
            "  let s = label(\"alpha\", 42) + label(\"beta\", 7) + \"!\"\n"
            "  System::print(s)\n"
            "  ret System::length(s)\n")
        c_code = compile_c(src, optimization_level=3)
        self.assertIn("str_concat_n", c_code)
