"""Polymorphic recursion — a generic function recursing at a DEEPER type
(`depth<T>` calling `depth<Wrap<T>>`) — cannot be monomorphised: every
iteration mints a new instantiation (`Wrap<Wrap<...<Int>>>`), forever. That
must be a compile error naming the offender, not a compiler hang.
"""


from tests.testutil import TimedTestCase
from tests.testutil import compile_errors

_SRC = """
namespace Main
import System

class [final] Wrap<T>(v: T)

fun depth<T>(x: T, n: System::Int): System::Int
  ret n == 0 ? 0 : depth(Wrap<T>(x), n - 1) + 1

fun main(): System::Int
  ret depth(1, 3)
"""


class TestPolymorphicRecursion(TimedTestCase):
    _TIMEOUT = 240  # the detector needs a few dozen monomorphisation rounds

    def test_polymorphic_recursion_is_an_error(self):
        out = compile_errors(_SRC).lower()
        self.assertIn("polymorphic recursion", out)
        self.assertIn("depth", out)
