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
"""
from __future__ import annotations

import contextlib
import io

import compiler as c
from tests.testutil import BatchedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


_HOST_BINDING = """
namespace Test
import System

fun isEnd<T>(c: System::Chain<T>): System::Bool
  ret match(c)
    (nil: System::ChainEnd) => true
    (l: System::ChainLink)  => false

fun restOf<T>(c: System::Chain<T>): System::Chain<T>
  ret match(c)
    (nil: System::ChainEnd) => c
    (l: System::ChainLink)  => l.next

# Two chains of DIFFERENT element types, no explicit type arguments inside.
fun [tail] shorter<T, U>(a: System::Chain<T>, b: System::Chain<U>): System::Bool
  ret isEnd(b)
    ? false
    : (isEnd(a) ? true : shorter(restOf(a), restOf(b)))

fun main(): System::Int
  let ints = System::prepend(1, System::List<System::Int>())
  let strs = System::prepend("a", System::prepend("b", System::List<System::String>()))
  ret shorter(System::chain(ints), System::chain(strs)) ? 7 : 3
"""


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
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        c.compile([c.Input(src, "test.yafl")], use_stdlib=True, just_testing=True)
    return buf.getvalue()


class TestGenericHostBinding(TestCase):
    def test_callee_param_binds_to_host_param(self):
        rc, _out = compile_and_run_stdlib_capture(_HOST_BINDING, timeout=120)
        self.assertEqual(7, rc)

    def test_unsourced_callee_param_in_generic_body_is_an_error(self):
        errs = _errors(_UNSOURCED)
        self.assertIn("cannot infer the type arguments of generic function `g`", errs)
