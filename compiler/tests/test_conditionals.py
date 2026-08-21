"""End-to-end tests for `if` / `else if` / `else`.

`if`, `else if`, and `else` parse as independent sibling statements at the
same indent. `collapse_else_if` (`pyast/statement.py`) folds proper
sequences into a single right-nested `IfStatement` during compile;
orphan `else` / `else if` survive the collapse and their `check()`
reports a compile error.

Branches are pure scopes; lets inside a branch do not escape. Per YAFL's
"only ambiguity is an error" principle, a branch may contain anything.
"""
from __future__ import annotations

import compiler as c
from tests.testutil import BatchedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib


# TestIfRuntime and TestIfElseRuntime are covered by
# test_conditionals_runtime.TestAllConditionalsRuntime.


class TestIfCompileErrors(TestCase):
    """Errors specific to the if-family — surfaced as compile errors."""

    def test_non_bool_condition_rejected(self):
        """`if` requires a Bool condition; an integer expression must be
        rejected at check time."""
        src = (
            "import System\n"
            "fun main(): System::Int\n"
            "    if 42\n"
            "        ret 1\n"
            "    ret 0\n"
        )
        result = c.compile([c.Input(src, "test.yafl")], use_stdlib=True, just_testing=False)
        self.assertEqual("", result)

    def test_orphan_else_rejected(self):
        """An `else` without a preceding `if` is reported by `check()`
        (the collapse pass leaves orphan ElseStatement in place; its
        `check()` always reports the error)."""
        src = (
            "import System\n"
            "fun main(): System::Int\n"
            "    else\n"
            "        ret 1\n"
            "    ret 0\n"
        )
        result = c.compile([c.Input(src, "test.yafl")], use_stdlib=True, just_testing=False)
        self.assertEqual("", result)

    def test_orphan_else_if_rejected(self):
        """Same for an `else if` with no preceding `if`."""
        src = (
            "import System\n"
            "fun main(): System::Int\n"
            "    else if 1 < 2\n"
            "        ret 1\n"
            "    ret 0\n"
        )
        result = c.compile([c.Input(src, "test.yafl")], use_stdlib=True, just_testing=False)
        self.assertEqual("", result)

    def test_else_separated_from_if_rejected(self):
        """A non-if statement between `if` and `else` breaks the chain;
        the `else` is then orphan and rejected by `check()`."""
        src = (
            "import System\n"
            "fun main(): System::Int\n"
            "    if 1 < 2\n"
            "        ret 1\n"
            "    let x: System::Int = 1\n"
            "    else\n"
            "        ret 2\n"
            "    ret 0\n"
        )
        result = c.compile([c.Input(src, "test.yafl")], use_stdlib=True, just_testing=False)
        self.assertEqual("", result)


# A multi-line `match` as a ternary BRANCH: the arm block is indentation-
# delimited, and the `? …` / `: …` continuation lines that follow must
# terminate it cleanly — in either branch position, and nested.
_MATCH_IN_TERNARY = """\
import System

fun pickFalse(x: System::Int|System::None, y: System::Int): System::Int
  ret y == 0
    ? y
    : match(x)
      (i: System::Int)  => i
      (n: System::None) => 0 - 1

fun pickTrue(x: System::Int|System::None, y: System::Int): System::Int
  ret y == 0
    ? match(x)
      (i: System::Int)  => i + 100
      (n: System::None) => 0 - 100
    : y

fun main(): System::Int
  print(String(pickFalse(7, 1)) + "\\n")
  let none: System::Int|System::None = System::None
  print(String(pickFalse(none, 1)) + "\\n")
  print(String(pickTrue(7, 0)) + "\\n")
  print(String(pickFalse(3, 0)) + "\\n")
  ret 0
"""


class TestMatchInTernary(TestCase):
    def test_match_as_ternary_branch(self):
        from tests.testutil import compile_and_run_stdlib_capture
        rc, out = compile_and_run_stdlib_capture(_MATCH_IN_TERNARY, timeout=30)
        self.assertEqual(0, rc, f"match-in-ternary failed; stdout:\n{out}")
        self.assertEqual(["7", "-1", "107", "0"], out.splitlines())
