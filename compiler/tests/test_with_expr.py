"""The `with` expression — copy-with-replacements, identity-preserving.

docs/preserving-rewrites-design.md, all rulings applied:

  * `with subject(name = value, …)` — call-shaped, not a call;
  * zero replacements is a CHECK error, not a parse error;
  * subjects are class- and enum-typed (ROOT included: the dynamic leaf is
    preserved, and names must be fields visible at the STATIC type);
  * the lowering returns the ORIGINAL object when every replacement is
    bit-identical to the current field ("SAME"), else a copy whose `$hash`
    slot is zeroed.

Identity preservation is unobservable by design, so the tests observe it
through the sanctioned doors: a `[refeq]` compare skips its compute for the
original-returned case, and `hashOf` must NOT serve a stale cache from a
copy.

Runtime behaviour is checked by compiler/yafl_tests/with_expr.yafl.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_c_result


def _diagnostics(content: str) -> str:
    r = compile_c_result(content, "file.yafl")
    return r.stdout if not r.c else ""


class TestWithValidation(TestCase):
    def test_zero_replacements_is_a_check_error(self):
        src = """\
import System

class [final] P2(px: System::Int)

fun main(): System::Int
  let a = P2(3)
  let b = with a()
  ret 0
"""
        diag = _diagnostics(src)
        self.assertIn("with", diag, diag or "COMPILED CLEAN")

    def test_unknown_field_is_rejected(self):
        src = """\
import System

class [final] P2(px: System::Int)

fun main(): System::Int
  let b = with P2(3)(nope = 1)
  ret 0
"""
        diag = _diagnostics(src)
        self.assertIn("nope", diag, diag or "COMPILED CLEAN")

    def test_subtype_field_invisible_at_root_type(self):
        """glow exists only on Green3; through a Colour3-typed subject it is
        not a visible field and must be rejected."""
        src = """\
import System

enum Colour3(shade: System::Int)
  enum Red3()
  enum Green3(glow: System::Int)

fun dim(c: Colour3): Colour3
  ret with c(glow = 1)

fun main(): System::Int
  ret 0
"""
        diag = _diagnostics(src)
        self.assertIn("glow", diag, diag or "COMPILED CLEAN")
