"""Affine drops: a never-referenced `[linear]` binding auto-releases at scope
exit through its `Drop` instance (lowering/drops.py inserts the call; the
linearity checker then sees ordinary consumption).

The prelude defines a linear `Res` whose Drop instance prints "dropped", so a
test observes exactly when (and how many times) a drop fires. Without a Drop
instance in scope, the old linearity error stands.

Runtime behaviour is checked by compiler/yafl_tests/drop.yafl.
"""
from __future__ import annotations


from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_c_result


_PRELUDE = """namespace Main
import System

class [linear,final] Res(x: System::Int)
  fun [terminal] fin(): System::None
    ret None

instance [ambient] System::Drop<Res>
  fun drop(self: Res): System::None
    System::print("dropped")
    ret self.fin()

fun sink(r: Res): System::Int
  let _ = r.fin()
  ret 4

"""


class TestAffineDrop(TestCase):


    def test_without_instance_the_linearity_error_stands(self):
        # Res2 is linear with NO Drop instance: an unused binding is still the
        # old hard error, not a silent leak.
        src = (_PRELUDE
               + "class [linear,final] Res2(y: System::Int)\n"
               + "fun main(): System::Int\n"
               + "  let q = Res2(3)\n"
               + "  ret 0\n")
        r = compile_c_result(src)
        self.assertFalse(r.c, "an undroppable linear leak must still fail")
        self.assertIn("never used; it must be consumed once", r.stdout)

