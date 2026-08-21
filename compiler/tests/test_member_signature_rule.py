"""Member functions declare neither type parameters nor a `where` clause.

A member is a vtable slot: its signature is the interface declaration with
the OWNER's type arguments substituted, fully determined by the class /
instance header. A member-level `<U>` would need a vtable row per call-site
instantiation (object-safety), and a member `where` constrains generics a
member cannot declare. Generics and constraints belong on the class or
instance; member bodies resolve through the owner's `where` clause.
"""
from __future__ import annotations

import contextlib
import io

import compiler as c
from tests.testutil import BatchedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


def _errors(src: str) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        c.compile([c.Input(src, "test.yafl")], use_stdlib=True, just_testing=True)
    return buf.getvalue()


_MEMBER_WHERE = """namespace Test
import System

interface Sized<T>
  fun sizeOf(v: T): Int

class Box(v: Int)

instance [ambient] Sized<Box>
  fun sizeOf(_v: Box): Int where Show<Int>
    ret 1

fun main(): Int
  ret 0
"""

_MEMBER_GENERICS = """namespace Test
import System

class Holder(v: Int)
  fun pick<U>(self: Holder, a: U, b: U): U
    ret a

fun main(): Int
  ret 0
"""

# The reason the drift happened: an instance-level `where` must reach the
# MEMBER BODIES (the stream combinators used to fake this with per-member
# wheres). The instance's constraint discharges sizeOf's inner call.
_OWNER_WHERE_REACHES_BODY = """namespace Test
import System

interface Sized<T>
  fun sizeOf(v: T): Int

instance [ambient]<T> Sized<List<T>> where Show<T>
  fun sizeOf(v: List<T>): Int
    ret length(fold(v, "", (acc: String, x: T) => acc + show(x)))

fun main(): Int
  let l = prepend(4, prepend(25, List<Int>()))
  ret sizeOf(l) == 3 ? 0 : 1
"""


class TestMemberSignatureRule(TestCase):
    _TIMEOUT = 600

    def test_member_where_rejected(self):
        errs = _errors(_MEMBER_WHERE)
        self.assertIn("member", errs.lower())

    def test_member_generics_rejected(self):
        errs = _errors(_MEMBER_GENERICS)
        self.assertIn("member", errs.lower())

    def test_owner_where_reaches_member_body(self):
        code, _out = compile_and_run_stdlib_capture(_OWNER_WHERE_REACHES_BODY)
        self.assertEqual(code, 0)
