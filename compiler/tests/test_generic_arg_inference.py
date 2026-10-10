"""A bare literal never takes a narrower type from its parameter.

RULED (2026-07-04): no conversion — `0` is Int and `1.5` is Float64, so
neither passes an Int32 or Float32 parameter. Type what you mean: `0i32`,
`1.5f32`. The accepted spellings, and argument-driven inference for generic
calls, are [test]s in compiler/yafl_tests/generic_arg_inference.yafl.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_errors


class Test(TestCase):
    def test_bare_literal_into_int32_param(self):
        content = ("import System\n"
                   "\n"
                   "fun takesI32(i: System::Int32): System::Int\n"
                   "    ret 0\n"
                   "\n"
                   "fun main(): System::Int\n"
                   "    ret takesI32(0)\n")
        self.assertEqual("file.yafl[7:18] - Parameters are not assignment compatible\n",
                         compile_errors(content, "file.yafl"))

    def test_bare_float_into_float32_param(self):
        content = ("import System\n"
                   "\n"
                   "fun takesF32(x: System::Float32): System::Int\n"
                   "    ret 0\n"
                   "\n"
                   "fun main(): System::Int\n"
                   "    ret takesF32(1.5)\n")
        self.assertEqual("file.yafl[7:18] - Parameters are not assignment compatible\n",
                         compile_errors(content, "file.yafl"))
