"""Calls inside a generic body whose type arguments come from the HOST's own
type parameters.

`shorter<T, U>(a: Chain<T>, b: Chain<U>)` calling `isEnd(b)` must bind
isEnd's `T` to the host's `U` — an in-scope placeholder is a genuine type
there, not a hole. Both compilers used to leave the callee's own placeholder
unbound, and monomorphisation then "completed" it by bare NAME: isEnd's `T`
became the host's `T`, so the `Chain<String>` argument was dispatched with
`Chain<Int>`'s tags and the program aborted at runtime — no compile error.

A callee parameter with no source at all (nothing in the arguments or the
expected type mentions it) is a "cannot infer" error, inside a generic body
exactly as outside one; guessing a binding by name is never an option.

The binding itself is a [test] in compiler/yafl_tests/generic_host_binding.yafl.
"""
from __future__ import annotations


from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_errors


_UNSOURCED = """
namespace Test
import System

fun g<T>(): System::Int
  ret 5

fun h<T>(x: T): System::Int
  ret g()

fun main(): System::Int
  ret h(true)
"""


def _errors(src: str) -> str:
    return compile_errors(src)


class TestGenericHostBinding(TestCase):
    def test_unsourced_callee_param_in_generic_body_is_an_error(self):
        errs = _errors(_UNSOURCED)
        self.assertIn("cannot infer the type arguments of generic function `g`", errs)
