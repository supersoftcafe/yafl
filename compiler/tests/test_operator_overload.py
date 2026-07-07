"""Join semantics for user-defined operators.

Defining a free-function operator (e.g. `+`) for a user type must JOIN the
`BasicMath` trait operators as an overload — resolved by operand/expected type —
NOT shadow them. Today a user `+` displaces the trait `+` program-wide, so the
built-in `+` stops resolving for Int/Float64 everywhere (even a bare `1 + 2`),
failing with a misattributed "Parameters are not assignment compatible" at the
use site rather than the definition.

This test pins the intended behaviour: with a user `Vec2 +` in scope, BOTH the
user operator and the built-in `Int +` resolve. Surfaced by
examples/raytracer.yafl, which had to fall back to named vadd/vsub because a
`Vec3 +` broke every Float64 `+` in the program.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib

_SRC = """\
namespace Main
import System

class Vec2(x: System::Int, y: System::Int)

# A free-function operator for a user type. Its own body relies on the built-in
# Int `+` (`a.x + b.x`), which must still resolve to the trait operator — not
# bind to this very function.
fun `+`(a: Vec2, b: Vec2): Vec2
  ret Vec2(a.x + b.x, a.y + b.y)

fun main(): System::Int
  let v = Vec2(1, 2) + Vec2(10, 20)   # user `+`     -> (11, 22)
  ret v.x + v.y + (3 + 4)             # built-in `+` -> 11 + 22 + 7 = 40
"""


class TestOperatorOverloadJoin(TestCase):
    def test_user_operator_joins_builtin_operator(self):
        # A user `+` must not evict the trait `+`: the program uses both and
        # should exit 11 + 22 + 7 = 40. FAILS TODAY — a free-function operator
        # displaces the BasicMath trait operator program-wide, so every built-in
        # `+` stops resolving ("Parameters are not assignment compatible").
        self.assertEqual(40, compile_and_run_stdlib(_SRC))
