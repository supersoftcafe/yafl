"""Union set semantics: a member that is a VARIANT of another member's enum
is the same set — `E3 | EU` where EU is a variant of E3 IS `E3`.

A let whose initialiser match had one arm returning `E3|W` and the else arm
returning the variant `EU()` typed as `E3|W|EU`; downstream matches then
reported spurious non-exhaustive/unreachable arms, and (in the bootstrap
compiler's registerFun) codegen lost the arm binder entirely.
"""
from tests.testutil import TimedTestCase, compile_and_run_stdlib

_SRC = """
namespace Main
import System

class [final] W(wMsg: System::String)

enum T2
  enum TA(taN: System::Int)
  enum TB()

enum E3
  enum EA(eaN: System::Int)
  enum EU()

class [final] Decl(dTy: T2|System::None, dLine: System::Int)

fun conv(t: T2, line: System::Int): E3|W
  ret match(t)
    (a: TA) => EA(a.taN + line)
    ()      => W("no")

fun probe(d: Decl): System::Int
  let retTy = match(d.dTy)
    (ty: T2) => conv(ty, d.dLine)
    ()       => EU()
  ret match(retTy)
    (w: W)   => -1
    (a: EA)  => a.eaN
    (u2: EU) => 0

fun main(): System::Int
  # TA(5)+2 -> EA(7) -> 7; None -> EU -> 0; encode both.
  ret probe(Decl(TA(5), 2)) * 10 + probe(Decl(None, 9))
"""


import unittest


class TestUnionVariantSubsume(TimedTestCase):
    # The union now CANONICALISES correctly (E3|W|EU folds to E3|W), but the
    # match still needs per-VARIANT arms through the union subject, and the
    # union reprs cannot dispatch those yet (see the bootstrap task list:
    # "variant arms through union subjects"). The checker stays conservative
    # to guard the codegen hole; this pins the target behaviour.
    @unittest.expectedFailure
    def test_variant_folds_into_its_enum(self):
        self.assertEqual(70, compile_and_run_stdlib(_SRC))
