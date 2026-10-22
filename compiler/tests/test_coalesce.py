"""`a ?? b` must wait for a subject whose type is not yet known.

The behaviour of `??` is a [test] in compiler/yafl_tests/coalesce.yafl. This
case depends on the order of convergence passes, which the whole yafl_tests
program does not reproduce, so it compiles a program of its own.
"""
from tests.testutil import TimedTestCase
from tests.testutil import compile_errors


class TestCoalesceWaitsForItsSubject(TimedTestCase):
    def test_subject_is_a_generic_call_on_an_inferred_let(self):
        # While `e` has no type yet, `get` is bound only partly — K from the
        # key, V still its own placeholder — so the subject reads `V|None`.
        # Dissolving on that leaves a match on a placeholder, which the
        # checker rejects as "unreachable arm" once V is known.
        out = compile_errors("""
namespace Main
import System

fun total(d: Dict<String, Int>): Int
  let e = d
  ret (get(e, "a") ?? 0) + (get(e, "b") ?? 0)

fun main(): Int
  ret total(put(put(Dict(), "a", 1), "b", 2)) == 3 ? 0 : 1
""")
        self.assertEqual([], [line for line in out.splitlines() if " - warning:" not in line])
