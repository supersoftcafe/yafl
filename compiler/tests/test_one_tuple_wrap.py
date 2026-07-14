"""A named 1-tuple and its element are the same TYPE but not the same C
REPRESENTATION (the tuple is a one-field struct). A function declared to
return `(t: E3|W)` whose arms produce bare members must WRAP — and a 1-tuple
value flowing into a bare-element slot must UNWRAP. Both conversions were
missing (clang: assigning the element's struct into the tuple struct), found
in the bootstrap's `checkExpr` before it moved to bare unions.
"""
from tests.testutil import TimedTestCase, compile_and_run_stdlib

_SRC = """
namespace Main
import System

class [final] W(wMsg: System::String)

enum E3
  enum EA(eaN: System::Int)
  enum EU()

fun f(n: System::Int): (t: E3|W)
  ret n > 0 ? EA(n) : W("neg")

fun useBare(v: E3|W): System::Int
  ret match(v)
    (e: E3) => match(e)
      (a: EA) => a.eaN
      ()      => 0
    (w: W)  => -1

fun main(): System::Int
  # wrap on return (both arms), unwrap via .t and via the bare-slot call.
  let good = f(5)
  let bad = f(-1)
  # Exit codes are 8-bit: keep the encoding small.
  ret useBare(good.t) * 10 + match(bad.t)
    (w: W)  => length(w.wMsg)
    (e: E3) => 0
"""


class TestOneTupleWrap(TimedTestCase):
    def test_wrap_and_unwrap(self):
        self.assertEqual(53, compile_and_run_stdlib(_SRC))
