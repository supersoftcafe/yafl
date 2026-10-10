"""End-to-end tests for `if` / `else if` / `else`.

`if`, `else if`, and `else` parse as independent sibling statements at the
same indent. `collapse_else_if` (`pyast/statement.py`) folds proper
sequences into a single right-nested `IfStatement` during compile;
orphan `else` / `else if` survive the collapse and their `check()`
reports a compile error.

Branches are pure scopes; lets inside a branch do not escape. Per YAFL's
"only ambiguity is an error" principle, a branch may contain anything.

Runtime behaviour is checked by compiler/yafl_tests/conditionals.yafl.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_errors


# The runtime shapes are [test]s in compiler/yafl_tests/conditionals.yafl.


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
        self.assertEqual(
            "test.yafl[3:8] - if condition must be Bool\n",
            compile_errors(src))

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
        self.assertEqual(
            "test.yafl[3:5] - `else` without a matching preceding `if`\n",
            compile_errors(src))

    def test_orphan_else_if_rejected(self):
        """Same for an `else if` with no preceding `if`."""
        src = (
            "import System\n"
            "fun main(): System::Int\n"
            "    else if 1 < 2\n"
            "        ret 1\n"
            "    ret 0\n"
        )
        self.assertEqual(
            "test.yafl[3:13] - `else if` without a matching preceding `if`\n",
            compile_errors(src))

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
        self.assertEqual(
            "test.yafl[5:9] - warning: 'x' is never used\n"
            "test.yafl[6:5] - `else` without a matching preceding `if`\n",
            compile_errors(src))
