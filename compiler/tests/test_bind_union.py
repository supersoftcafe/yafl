"""`?>` threads plain error unions: `value ?> (v: T) => next(v)`.

The lambda's TYPED parameter picks the success member; every other member of
the subject union passes through unchanged. The stage's result type is the
lambda's result unioned with the passed-through members — set semantics
collapse the duplicates, so chains of `X|Err` stages stay `…|Err`. This is
the union analogue of the (io, v: T|IOError) overload; it exists so error
threading reads as a pipeline instead of a ladder of match expressions
(found writing the yaflc self-hosting prototype).
"""
from tests.testutil import TimedTestCase, compile_and_run_stdlib

_CHAIN = """
namespace Main
import System

class [final] Oops(message: System::String)

fun half(n: System::Int): System::Int|Oops
  ret n % 2 == 0 ? n / 2 : Oops("odd " + String(n))

fun run(n: System::Int): System::Int
  let r = half(n)
    ?> (a: System::Int) => half(a)
    ?> (b: System::Int) => b + 100
  ret match(r)
    (v: System::Int) => v
    (e: Oops)        => 0 - length(e.message)

fun main(): System::Int
  # 8 -> 4 -> 2 -> +100 = 102; 10 -> 5 -> Oops("odd 5") = len 5 -> -5.
  # Exit codes are 8-bit: keep the encoding under 256.
  ret run(8) + (0 - run(10))
"""

_NONE_UNION = """
namespace Main
import System

fun evenOr(n: System::Int): System::Int|System::None
  ret n % 2 == 0 ? n : None

fun run(n: System::Int): System::Int
  let r = evenOr(n)
    ?> (v: System::Int) => v * 10
  ret match(r)
    (v: System::Int) => v
    ()               => -1
"""


class TestBindUnion(TimedTestCase):
    def test_error_union_threading(self):
        # run(8)=102, run(12)=-6 -> 102*1000 + 6
        self.assertEqual(107, compile_and_run_stdlib(_CHAIN))

    def test_none_union_threading(self):
        src = _NONE_UNION + """
fun main(): System::Int
  # 4 -> 40; 5 -> None -> -1; encode both.
  ret run(4) + (0 - run(5))
"""
        self.assertEqual(41, compile_and_run_stdlib(src))
