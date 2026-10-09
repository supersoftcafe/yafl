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

The runtime behaviour is checked by compiler/yafl_tests/never.yafl.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_c, compile_c_result


class TestNeverType(TestCase):
    def test_empty_enum_not_constructible(self):
        # `Empty` has no `()` and no variants → no constructor exists.
        result = compile_c(
            "namespace Test\n"
            "import System\n"
            "enum Empty\n"
            "fun mk(): Empty\n"
            "  ret Empty()\n"
            "fun main(): System::Int\n"
            "  ret 0\n")
        self.assertEqual("", result)  # rejected

    def test_unit_enum_still_constructible(self):
        # The `()` form is a real unit value and must keep compiling.
        result = compile_c(
            "namespace Test\n"
            "import System\n"
            "enum Unit()\n"
            "fun mk(): Unit\n"
            "  ret Unit()\n"
            "fun main(): System::Int\n"
            "  ret 0\n")
        self.assertNotEqual("", result)  # compiles


class TestInhabitedOnlyExhaustiveness(TestCase):
    """Exhaustiveness counts inhabited members only (2026-07-03): an uncovered
    `Never` member owes no arm — dead code by construction — while an explicit
    arm for it stays legal. Narrowing a Never-carrying union therefore needs no
    fabricated unreachable value."""

    def test_inhabited_members_still_required(self):
        # Relaxation applies ONLY to uninhabited members: dropping the String
        # arm must still be non-exhaustive.
        r = compile_c_result(
                "namespace Main\n"
                "import System\n"
                "fun pick(v: System::Int | System::String | System::Never): System::Int\n"
                "  ret match(v)\n"
                "    (i: System::Int) => i\n"
                "fun main(): System::Int\n"
                "  ret pick(1)\n")
        self.assertFalse(r.c)
        self.assertIn("non-exhaustive", r.stdout)
