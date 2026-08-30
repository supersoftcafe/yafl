"""`match(a, b)` — dispatch on several subjects at once.

An arm has one pattern per subject and ALL must match; a failing pattern falls
through to the next arm. That is a SEQUENCE of staged checks per arm, not a
decision tree: `_Emitter.arm` already ANDs stages and falls through on any
failure, which is first-match-wins across positions for free.

What each test pins, and why:

  * cross-position fall-through — an arm matching position 0 but FAILING
    position 1 must fall to a later arm whose position-0 pattern DIFFERS.
    Nesting on position 0 would enter the first arm's group and find nothing;
    this is the case that decides the whole design.
  * per-position bindings — every position binds its own name, and the
    INLINER must rename all of them: renaming only position 0 gave each
    inlined copy the same stack var ("y@arm…: defined 4 times").
  * both option representations — `Sp|None` is a DataPointer union but
    `Int32|None` is a TAGGED STRUCT. Guards AND binds differ per repr (a
    pointer binds at the arm's type, a tagged combination REASSEMBLES the
    variant from union slots, the enum reprs bind at the subject type), so
    the repr decides, not the caller.
  * arity — the grammar cannot check it, since it does not know the subject
    count; the check phase does.
"""
import contextlib
import io

import compiler as c
from tests.testutil import TimedTestCase, compile_and_run_stdlib


def _errors(src: str) -> str:
    """Diagnostics only — the same helper test_match_extensions uses."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        c.compile([c.Input(src, "test.yafl")], use_stdlib=True, just_testing=True)
    return buf.getvalue()

_SHAPES = """
namespace Main
import System

enum Sh
  enum Bx(bv: System::Int)
  enum Dt()
  enum Tri(tv: System::Int)
"""


class TestMultiSubjectMatch(TimedTestCase):
    def test_two_enum_subjects(self):
        src = _SHAPES + """
fun cmp(a: Sh, b: Sh): System::Int
  ret match(a, b)
    (x: Bx, y: Bx) => x.bv + y.bv
    (x: Bx, y: Dt) => x.bv
    (x: Dt, y: Bx) => y.bv
    ()             => 0

fun main(): System::Int
  ret cmp(Bx(3), Bx(4)) + cmp(Bx(5), Dt()) + cmp(Dt(), Bx(6)) + cmp(Dt(), Dt())
"""
        self.assertEqual(18, compile_and_run_stdlib(src))

    def test_falls_through_across_positions(self):
        # Row 1 matches position 0 for (Bx, Dt) but fails position 1, so it
        # must fall to row 2 — whose position-0 pattern is DIFFERENT. A nested
        # dispatch on position 0 gets this wrong.
        src = _SHAPES + """
fun pick(a: Sh, b: Sh): System::Int
  ret match(a, b)
    (x: Bx,  y: Bx) => 1
    (x: Sh,  y: Dt) => 2
    (x: Tri, y: Sh) => 3
    ()              => 4

fun main(): System::Int
  ret pick(Bx(0), Bx(0)) + pick(Bx(0), Dt()) + pick(Tri(0), Bx(0)) + pick(Dt(), Bx(0))
"""
        self.assertEqual(10, compile_and_run_stdlib(src))

    def test_guard_falls_through_to_a_later_arm(self):
        src = _SHAPES + """
fun g(a: Sh, b: Sh): System::Int
  ret match(a, b)
    (x: Bx, y: Bx) if x.bv > y.bv => 10
    (x: Bx, y: Bx)                => 20
    ()                            => 30

fun main(): System::Int
  ret g(Bx(5), Bx(1)) + g(Bx(1), Bx(5)) + g(Dt(), Dt())
"""
        self.assertEqual(60, compile_and_run_stdlib(src))

    def test_pointer_union_positions(self):
        # `Sp|None` is a DataPointer union: NULL for the unit member, vtable
        # identity for the rest, and the binding is the narrowed pointer.
        src = """
namespace Main
import System

class [final] Sp(sv: System::Int)

fun eqOpt(a: Sp|System::None, b: Sp|System::None): System::Int
  ret match(a, b)
    (x: Sp, y: Sp)           => x.sv + y.sv
    (x: Sp, y: System::None) => 1
    (x: System::None, y: Sp) => 2
    ()                       => 3

fun main(): System::Int
  ret eqOpt(Sp(4), Sp(5)) + eqOpt(Sp(1), None) + eqOpt(None, Sp(1)) + eqOpt(None, None)
"""
        self.assertEqual(15, compile_and_run_stdlib(src))

    def test_tagged_struct_option_positions(self):
        # The OTHER option representation: `Int32|None` is a tagged struct, so
        # the guard is a $tag comparison and the bind reassembles from slots.
        src = """
namespace Main
import System

fun pick(a: System::Int32|System::None, b: System::Int32|System::None): System::Int32
  ret match(a, b)
    (x: System::Int32, y: System::Int32) => x + y
    (x: System::Int32, y: System::None)  => x
    (x: System::None,  y: System::Int32) => y
    ()                                   => 0i32

fun main(): System::Int
  ret System::Int(pick(3i32, 4i32) + pick(5i32, None) + pick(None, 6i32) + pick(None, None))
"""
        self.assertEqual(18, compile_and_run_stdlib(src))

    def test_arm_arity_is_checked(self):
        errs = _errors(_SHAPES + """
fun bad(a: Sh): System::Int
  ret match(a)
    (x: Bx, y: Bx) => 1
    ()             => 0

fun main(): System::Int
  ret bad(Dt())
""")
        self.assertIn("2 patterns but the match has 1 subject", errs)

    def test_non_exhaustive_over_the_product(self):
        # (Dt, Dt) is uncovered: coverage is over the PRODUCT of the positions.
        errs = _errors(_SHAPES + """
fun p(a: Sh, b: Sh): System::Int
  ret match(a, b)
    (x: Bx, y: Sh) => 1
    (x: Sh, y: Bx) => 2

fun main(): System::Int
  ret p(Dt(), Dt())
""")
        self.assertIn("non-exhaustive", errs)
