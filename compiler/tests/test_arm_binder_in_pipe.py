"""A match-arm binder must survive into a PIPE STAGE in the arm's body.

(Regression guard — this was an open bug, now fixed.)

`match(x.field) (t: T) => f(t) |> (u) => g(u)` inside a function whose
PARAMETER TYPE is an enum VARIANT lost the binder at codegen ("Could not find
t@arm..."): the pipeline's beta-reduction moves the arm body into a nested
block, and the binder's rename didn't reach it through the variant-typed
parameter's scope. Found porting the compiler's typespec (uid of a lazy-stub
spec) to YAFL.
"""
from tests.testutil import TimedTestCase, compile_and_run_stdlib_capture

_SRC = """
namespace Main
import System

enum Sp
  enum SA(saName: System::String)
  enum SLazy(slTarget: Sp|System::None)

fun uid(sp: Sp): System::String
  ret match(sp)
    (a: SA)    => a.saName
    (l: SLazy) => uidLazy(l)

fun uidLazy(ls: SLazy): System::String
  ret match(ls.slTarget)
    (t: Sp) => uid(t) |> (u: System::String) => u == "" ? "" : "$lazy$" + u
    ()      => "$lazy$"

fun main(): System::Int
  print(uid(SLazy(SA("q"))) + "|" + uid(SLazy(None)) + "\\n")
  ret 0
"""


class TestArmBinderInPipe(TimedTestCase):
    # WAS an open bug; FIXED (confirmed 2026-07-14 — compiles, runs, and
    # prints the right answer). The trigger needed ALL of: mutual recursion
    # (uid <-> uidLazy), a parameter typed as an enum VARIANT, and the arm
    # binder consumed inside a pipeline stage — so keep this repro exactly as
    # it is. It now stands as the regression guard.
    def test_binder_reaches_pipe_stage(self):
        rc, out = compile_and_run_stdlib_capture(_SRC)
        self.assertEqual(0, rc)
        self.assertEqual("$lazy$q|$lazy$\n", out)
