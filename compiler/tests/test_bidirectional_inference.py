"""Bidirectional inference across a generic call and a lambda argument.

`mapBox<T, U>(b: Box<T>, f: (:T): U): Box<U>` called as `mapBox(b, (x) => x + 1)`
with no type arguments is the canonical mutually-dependent case:

  * `T` comes from the `b: Box<T>` argument, and
  * `U` comes from the lambda's body — but the lambda can only type `x` once `T`
    is known.

It works only if the partial inference (`T = Int`) is threaded back into the
lambda's expected parameter type so `x: Int` resolves, after which the body type
pins `U = Int`. Before that, the call failed with "Not enough type parameters".
"""
from __future__ import annotations

from tests.testutil import BatchedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


_SRC = """
namespace Test
import System

class [final] Box<T>(value: T)

fun mapBox<T, U>(b: Box<T>, f: (:T): U): Box<U>
  ret Box<U>(f(b.value))

fun main(): System::Int
  let b = Box<System::Int>(5)
  let r = mapBox(b, (x) => x + 1)   # no type args: T from b, U from the lambda
  ret r.value
"""


# The callee's second param is named `U`, the SAME source identifier as the
# enclosing `outer`'s type param. Placeholder names carry the hash6 of their
# declaration site, so the two `U`s are different names and never collide — the
# partial-inference re-inference guard (which leaves an enclosing/self param
# alone but re-infers a callee's own leftover) must still bind `mapBox`'s `U`.
_SRC_NAME_REUSE = """
namespace Test
import System

class [final] Box<T>(value: T)

fun mapBox<T, U>(b: Box<T>, f: (:T): U): Box<U>
  ret Box<U>(f(b.value))

fun outer<U>(seed: U): System::Int
  let b = Box<System::Int>(10)
  let r = mapBox(b, (x) => x + 1)   # mapBox's U != outer's U (distinct hashes)
  ret r.value

fun main(): System::Int
  ret outer<System::Bool>(true)
"""


class TestBidirectionalInference(TestCase):
    def test_lambda_param_inferred_from_sibling_arg(self):
        rc, _out = compile_and_run_stdlib_capture(_SRC, timeout=120)
        self.assertEqual(6, rc)

    def test_callee_param_name_reused_by_enclosing_generic(self):
        rc, _out = compile_and_run_stdlib_capture(_SRC_NAME_REUSE, timeout=120)
        self.assertEqual(11, rc)
