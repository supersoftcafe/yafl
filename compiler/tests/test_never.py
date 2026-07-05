"""The empty type.

An enum declared with no variants AND no constructor parameter list (no `()`)
is an ordinary type with one distinguishing fact: it has no constructor, so no
value of it can ever exist (`Never()` is an error).

It gets no other special treatment. `Never | X` is a normal two-member union,
NOT `X`: it is not assignable to `X`, and a match over it must cover the `Never`
member like any other (with an arm or an `else`). That arm is unreachable at
runtime, but the type system does not exempt it.

The `()` form (`enum Unit()`) is a distinct, constructible unit value and must
keep working — only the no-parens, no-variants form is empty.
"""
from __future__ import annotations

import compiler as c
from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture
from tests.testutil import compile_and_run_stdlib


class TestNeverType(TestCase):
    def test_empty_enum_not_constructible(self):
        # `Empty` has no `()` and no variants → no constructor exists.
        result = c.compile([c.Input(
            "namespace Test\n"
            "import System\n"
            "enum Empty\n"
            "fun mk(): Empty\n"
            "  ret Empty()\n"
            "fun main(): System::Int\n"
            "  ret 0\n",
            "test.yafl")], use_stdlib=True, just_testing=False)
        self.assertEqual("", result)  # rejected

    def test_unit_enum_still_constructible(self):
        # The `()` form is a real unit value and must keep compiling.
        result = c.compile([c.Input(
            "namespace Test\n"
            "import System\n"
            "enum Unit()\n"
            "fun mk(): Unit\n"
            "  ret Unit()\n"
            "fun main(): System::Int\n"
            "  ret 0\n",
            "test.yafl")], use_stdlib=True, just_testing=False)
        self.assertNotEqual("", result)  # compiles

    def test_never_member_needs_no_constructed_value(self):
        # A union may carry an uninhabited member: `pick` returns
        # `Never | IOError | None` while only ever constructing the two inhabited
        # members. The match covers `Never` with an `else` — it is never reached,
        # but the type system requires the union to be covered like any other.
        rc, out = compile_and_run_stdlib_capture("""
import System
import System::IO

fun pick(flag: System::Bool): System::Never | IOError | System::None
  ret flag ? EOFError(0) : None

fun classify(v: System::Never | IOError | System::None): System::Int
  ret match(v)
    (e: IOError)      => 1
    (n: System::None) => 0
    ()                => 2

fun main(): System::Int
  ret classify(pick(true)) == 1 && classify(pick(false)) == 0 ? 0 : 9
""", timeout=120)
        self.assertEqual(0, rc)

    def test_uninhabited_member_does_not_change_representation(self):
        # `Never | X` and a richer error union must lay out X identically: an
        # uninhabited member is never dropped, so a value built as `IOError` and
        # carried through a `Never | IOError | None` channel round-trips. This
        # guards against the representation collapsing when one member happens to
        # be uninhabited.
        rc, out = compile_and_run_stdlib_capture("""
import System
import System::IO

fun box(e: IOError): System::Never | IOError | System::None
  ret e

fun unbox(v: System::Never | IOError | System::None): System::Int
  ret match(v)
    (e: IOError)      => 7
    (n: System::None) => 0
    ()                => 9

fun main(): System::Int
  ret unbox(box(EOFError(0))) == 7 ? 0 : 1
""", timeout=120)
        self.assertEqual(0, rc)


class TestInhabitedOnlyExhaustiveness(TestCase):
    """Exhaustiveness counts inhabited members only (2026-07-03): an uncovered
    `Never` member owes no arm — dead code by construction — while an explicit
    arm for it stays legal. Narrowing a Never-carrying union therefore needs no
    fabricated unreachable value."""

    def test_match_without_never_arm_is_exhaustive(self):
        rc = compile_and_run_stdlib(
            "namespace Main\n"
            "import System\n"
            "fun pick(v: System::Int | System::String | System::Never): System::Int\n"
            "  ret match(v)\n"
            "    (i: System::Int)    => i\n"
            "    (s: System::String) => System::length(s)\n"
            "fun main(): System::Int\n"
            "  ret pick(41) + pick(\"x\")\n")
        self.assertEqual(42, rc)

    def test_inhabited_members_still_required(self):
        # Relaxation applies ONLY to uninhabited members: dropping the String
        # arm must still be non-exhaustive.
        import contextlib, io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = c.compile([c.Input(
                "namespace Main\n"
                "import System\n"
                "fun pick(v: System::Int | System::String | System::Never): System::Int\n"
                "  ret match(v)\n"
                "    (i: System::Int) => i\n"
                "fun main(): System::Int\n"
                "  ret pick(1)\n", "test.yafl")], use_stdlib=True, just_testing=True)
        self.assertFalse(code)
        self.assertIn("non-exhaustive", buf.getvalue())
