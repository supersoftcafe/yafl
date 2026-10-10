"""Member functions declare neither type parameters nor a `where` clause.

A member is a vtable slot: its signature is the interface declaration with
the OWNER's type arguments substituted, fully determined by the class /
instance header. A member-level `<U>` would need a vtable row per call-site
instantiation (object-safety), and a member `where` constrains generics a
member cannot declare. Generics and constraints belong on the class or
instance; member bodies resolve through the owner's `where` clause.

That the owner's `where` reaches member bodies, and that a global generic
function may hold a nested helper, are [test]s in
compiler/yafl_tests/member_signature_rule.yafl.
"""
from __future__ import annotations


from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_errors


def _errors(src: str) -> str:
    return compile_errors(src)


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

class TestMemberSignatureRule(TestCase):
    _TIMEOUT = 600

    def test_member_where_rejected(self):
        errs = _errors(_MEMBER_WHERE)
        self.assertIn("member", errs.lower())

    def test_member_generics_rejected(self):
        errs = _errors(_MEMBER_GENERICS)
        self.assertIn("member", errs.lower())


class TestOnlyGlobalDeclaresTypeParameters(TestCase):
    """Type parameters belong to GLOBAL functions.

    Anything else — an inner function, a class member, an instance member —
    has no scope of its own but inherits its owner's, so a type parameter
    there rebinds a name that is already bound. The symptoms are remote from
    the cause and differ by shape: a restated `<T>` resolves ambiguously, a
    fresh `<X>` is simply not in scope inside its own body, and neither says
    what is actually wrong. Found migrating RRBTree to nested helpers.

    One check answers all three, on the function itself: whoever declares it
    marks it non-global, and `FunctionStatement.check` asks `is_global`.
    """

    def test_inner_function_own_type_parameter(self):
        errs = _errors("""namespace Test
import System

fun outer(x: Int): Int
  fun helper<X>(v: X, k: Int): Int
    ret k + 1
  ret helper<Int>(x, 1)

fun main(): Int
  ret outer(1)
""")
        self.assertIn("only a global function declares type parameters", errs)

    def test_inner_function_restating_enclosing_parameter(self):
        errs = _errors("""namespace Test
import System

fun outer<T>(x: T, n: Int): Int
  fun helper<T>(v: T, k: Int): Int
    ret k + 1
  ret helper<T>(x, 1)

fun main(): Int
  ret outer<Int>(2, 3)
""")
        self.assertIn("only a global function declares type parameters", errs)

    def test_class_member_type_parameter(self):
        errs = _errors("""namespace Test
import System

class [final] Box(v: Int)
  fun pick<U>(x: U): Int
    ret v

fun main(): Int
  ret Box(1).pick<Int>(2)
""")
        self.assertIn("only a global function declares type parameters", errs)
