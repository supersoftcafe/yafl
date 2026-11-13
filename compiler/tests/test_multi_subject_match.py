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

The runtime cases are [test]s in compiler/yafl_tests/multi_subject_match.yafl;
the arity and exhaustiveness errors are checked here.
"""

from tests.testutil import TimedTestCase
from tests.testutil import compile_errors


def _errors(src: str) -> str:
    """Diagnostics only — the same helper test_match_extensions uses."""
    return compile_errors(src)

_SHAPES = """
namespace Main
import System

enum Sh
  enum Bx(bv: System::Int)
  enum Dt()
  enum Tri(tv: System::Int)
"""


class TestMultiSubjectMatch(TimedTestCase):
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

    def test_a_parent_pattern_over_sibling_members_is_refused_at_a_position(self):
        # #74: `Thing` over `Car|Boat` matches both members, and each would
        # bind a different value at that position — so it is refused there.
        errs = _errors("""
namespace Main
import System

enum Thing(id: System::Int)
  enum Car(seats: System::Int)
  enum Boat(hulls: System::Int)

fun pair(x: Car|Boat, n: System::Int): System::Int
  ret match(x, n)
    (t: Thing, m: System::Int) => m

fun main(): System::Int
  ret pair(Car(1, 2), 3)
""")
        self.assertIn("this pattern cannot serve a position of a multi-subject match", errs)

    def test_a_generic_subject_is_refused_at_a_position(self):
        # #109: a union with a member held by value as a type parameter has
        # no layout until monomorphisation, so no repr can say whether its
        # position is testable. Refused, never classified (Python crashed on
        # it). A `List<T>` subject is a pointer whatever T is, and stays
        # testable: the stdlib flattens over those.
        errs = _errors("""
namespace Main
import System

fun pick<T>(a: System::Int|System::None, v: T|System::None): T|System::None
  ret match(a, v)
    (i: System::Int, x: T) => x
    ()                     => System::None

fun main(): System::Int
  ret match(pick<System::Int>(1, 7))
    (i: System::Int) => i - 7
    ()               => 1
""")
        self.assertIn("a position of a multi-subject match cannot test a union with a generic member", errs)

    def test_an_unresolved_subject_type_is_reported_not_crashed_on(self):
        # #109: a subject whose type names something that does not exist has
        # no repr either; the failed name is the error, not a crash.
        errs = _errors("""
namespace Main
import System

fun f(a: Missing|System::None, b: System::Int|System::None): System::Int
  ret match(a, b)
    (x: System::None, y: System::Int) => y
    ()                                => 0

fun main(): System::Int
  ret f(System::None, 2)
""")
        self.assertIn("Missing", errs)
