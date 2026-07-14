"""A match on a `T|None` subject whose NULL case is handled by the ELSE arm
(no explicit `(n: None)` arm) must emit the else body exactly once.

The DataPointer-union dispatch routes NULL to the else arm when no None arm
exists — but it used to do so by emitting the else arm's BODY as the null
arm AND again as the final fallback. Any stack variable defined in that body
(e.g. the parameter let of an inlined constructor) was then defined at two
sites, tripping the SSA single-definition validator. Nothing in stdlib or
the examples hit this because the house style writes explicit None arms.
"""
from tests.testutil import TimedTestCase, compile_and_run_stdlib

_SRC = """
namespace Main
import System

class [final] Boom(message: System::String)

fun probe(x: System::Int): System::Int|System::None
  ret x == 0 ? None : x

fun pick(x: System::Int|System::None): System::Int|Boom
  ret match(x)
    (n: System::Int) => n
    ()               => Boom("nothing")

fun classify(x: System::Int): System::Int
  ret match(pick(probe(x)))
    (b: Boom) => 1
    ()        => 0

fun main(): System::Int
  # probe(0) is None -> else arm constructs the Boom (1); probe(5) is Int (0).
  ret classify(0) * 10 + classify(5)
"""


class TestMatchNullElse(TimedTestCase):
    def test_else_arm_covers_null_o0(self):
        self.assertEqual(10, compile_and_run_stdlib(_SRC))

    def test_else_arm_covers_null_o2(self):
        self.assertEqual(10, compile_and_run_stdlib(_SRC, optimization_level=2))
