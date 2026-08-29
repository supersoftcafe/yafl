"""`??` ends an option with a default: `a ?? b` is a's value, or b when None.

The elimination half of the option idiom, and the counterpart to `?>`, which
propagates the absent case instead. Written out by hand 262 times in the
compiler as `match(x) (v: T) => v; () => default`.

Three properties this pins, each of which cost a bug to get right:

  * NARROWING — the result is `T`, not `T|None`. This is why `??` is an AST
    node and not parse-time sugar: the desugar needs an arm typed at the
    subject's non-None part, which is not spellable at parse time.
  * ARM CONVERGENCE — when the fallback is itself an option (`a ?? b ?? c`),
    the two arms have different types and each must wrap itself. A match's
    arms converge on the RECEIVER's type; with no receiver the node has to
    supply its own, or generate aborts with "conversion required".
  * BINDER UNIQUENESS — `a ?? b ?? c` folds left-associatively and every node
    in that fold inherits the left operand's line_ref, so a binder keyed on it
    collides and two arms define one SSA value.

And the property that justifies the node over an ordinary `[inline]` function:
the fallback is SHORT-CIRCUIT, because it lands in a match arm.
"""
from tests.testutil import TimedTestCase, compile_and_run_stdlib

_PRELUDE = """
namespace Main
import System

class [final] Box(bv: System::Int)

fun maybe(n: System::Int): Box|System::None
  ret n > 0 ? Box(n) : None
"""


class TestCoalesce(TimedTestCase):
    def test_narrows_to_the_non_none_member(self):
        # The result is Box, not Box|None — `.bv` is only reachable if so.
        src = _PRELUDE + """
fun pick(n: System::Int): Box
  ret maybe(n) ?? Box(0 - 1)

fun main(): System::Int
  # 5 present; 0 absent -> -1, encoded as +1.
  ret pick(5).bv + (0 - pick(0).bv)
"""
        self.assertEqual(6, compile_and_run_stdlib(src))

    def test_chains_left_associatively(self):
        # `a ?? b ?? c` takes the first present value. Exercises arm
        # convergence (hit arm Box, fallback Box|None) and binder uniqueness
        # (both nodes share a line_ref).
        src = _PRELUDE + """
fun firstOf(a: System::Int, b: System::Int): System::Int
  ret (maybe(a) ?? maybe(b) ?? Box(99)).bv

fun main(): System::Int
  # 4 -> a; (0,9) -> b; (0,0) -> the literal fallback.
  ret firstOf(4, 9) + firstOf(0, 9) + firstOf(0, 0)
"""
        self.assertEqual(112, compile_and_run_stdlib(src))

    def test_composes_with_bind(self):
        # `?>` propagates, `??` ends it. They share a precedence level's
        # neighbourhood: `??` is LOOSER, so this groups as `(a ?> f) ?? d`.
        src = _PRELUDE + """
fun chained(n: System::Int): System::Int
  ret (maybe(n) ?> (b: Box) => b.bv) ?? (0 - 7)

fun main(): System::Int
  ret chained(3) + (0 - chained(0))
"""
        self.assertEqual(10, compile_and_run_stdlib(src))

    def test_fallback_is_short_circuit(self):
        # `boom` divides by a RUNTIME zero (a literal would fold). An eager
        # fallback — what an ordinary [inline] function would give — traps
        # here; a match arm is never entered when the subject is present.
        src = _PRELUDE + """
fun boom(z: System::Int): Box
  ret Box(100 / z)

fun main(): System::Int
  let zero = 0
  ret (maybe(7) ?? boom(zero)).bv
"""
        self.assertEqual(7, compile_and_run_stdlib(src))
