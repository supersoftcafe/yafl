"""An UN-annotated value parameter of a GENERIC function infers from call sites too.

`fun pickSecond<N>(a: N, b) ret b` declares a type for `a` (the generic `N`) but
not for `b`. `b` is a plain hole — no different from an untyped parameter of a
non-generic function — and must be filled from the call-site argument (`99` → Int).
The generic-ness of the function is irrelevant to `b`; only `a`'s declared type
makes `a` ignore suggestions.
"""
from __future__ import annotations

from tests.testutil import BatchedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


_SRC = """
namespace Test
import System

fun pickSecond<N>(a: N, b)
  ret b

fun main(): System::Int
  ret pickSecond<System::Bool>(true, 99)
"""


class TestGenericUntypedParam(TestCase):
    def test_untyped_param_of_generic_fn_infers_from_call_site(self):
        rc, _out = compile_and_run_stdlib_capture(_SRC, timeout=120)
        self.assertEqual(99, rc)
