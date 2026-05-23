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
from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib


class TestIfRuntime(TestCase):

    def test_guard_taken(self):
        """`if cond <body>` with `cond` true returns 5, not the trailing 7."""
        src = (
            "import System\n"
            "fun main(): System::Int\n"
            "    if 0 < 1\n"
            "        ret 5\n"
            "    ret 7\n"
        )
        self.assertEqual(5, compile_and_run_stdlib(src))

    def test_guard_not_taken(self):
        """`if cond <body>` with `cond` false falls through to the trailing 7."""
        src = (
            "import System\n"
            "fun main(): System::Int\n"
            "    if 0 > 1\n"
            "        ret 5\n"
            "    ret 7\n"
        )
        self.assertEqual(7, compile_and_run_stdlib(src))

    def test_multi_statement_body(self):
        """A branch with branch-local lets — `let b` does not escape. a+1 = 6."""
        src = (
            "import System\n"
            "fun main(): System::Int\n"
            "    let a: System::Int = 5\n"
            "    if a < 10\n"
            "        let b: System::Int = a + 1\n"
            "        ret b\n"
            "    ret 99\n"
        )
        self.assertEqual(6, compile_and_run_stdlib(src))

    def test_early_return_inlined(self):
        """`max(a,b)` is small enough to be inlined. The inliner rewrites
        every `Return` op in the inlinee — including the one inside the
        `if`'s true branch — as `Move(dest, value); Jump(inl_end)`.
        max(7,3) + max(2,10) = 7 + 10 = 17."""
        src = (
            "import System\n"
            "fun max(a: System::Int, b: System::Int): System::Int\n"
            "    if a < b\n"
            "        ret b\n"
            "    ret a\n"
            "fun main(): System::Int\n"
            "    ret max(7, 3) + max(2, 10)\n"
        )
        self.assertEqual(17, compile_and_run_stdlib(src))


class TestIfElseRuntime(TestCase):
    """Tests that `if` / `else` and `if` / `else if` / `else` chains are
    correctly collapsed into nested `IfStatement` during compile."""

    def test_if_else_true(self):
        src = (
            "import System\n"
            "fun main(): System::Int\n"
            "    if 1 < 2\n"
            "        ret 10\n"
            "    else\n"
            "        ret 20\n"
            "    ret 99\n"
        )
        self.assertEqual(10, compile_and_run_stdlib(src))

    def test_if_else_false(self):
        src = (
            "import System\n"
            "fun main(): System::Int\n"
            "    if 1 > 2\n"
            "        ret 10\n"
            "    else\n"
            "        ret 20\n"
            "    ret 99\n"
        )
        self.assertEqual(20, compile_and_run_stdlib(src))

    def test_chain_first(self):
        """First `if` matches; chain short-circuits without trying else-ifs."""
        src = (
            "import System\n"
            "fun main(): System::Int\n"
            "    if 1 < 2\n"
            "        ret 10\n"
            "    else if 3 < 4\n"
            "        ret 20\n"
            "    else\n"
            "        ret 30\n"
            "    ret 99\n"
        )
        self.assertEqual(10, compile_and_run_stdlib(src))

    def test_chain_else_if(self):
        """First clause fails, second (else-if) matches."""
        src = (
            "import System\n"
            "fun main(): System::Int\n"
            "    if 1 > 2\n"
            "        ret 10\n"
            "    else if 3 < 4\n"
            "        ret 20\n"
            "    else\n"
            "        ret 30\n"
            "    ret 99\n"
        )
        self.assertEqual(20, compile_and_run_stdlib(src))

    def test_chain_else(self):
        """All `if`/`else if` clauses fail; `else` is the final fallback."""
        src = (
            "import System\n"
            "fun main(): System::Int\n"
            "    if 1 > 2\n"
            "        ret 10\n"
            "    else if 3 > 4\n"
            "        ret 20\n"
            "    else\n"
            "        ret 30\n"
            "    ret 99\n"
        )
        self.assertEqual(30, compile_and_run_stdlib(src))

    def test_chain_no_else_falls_through(self):
        """No `else`; every clause fails → control reaches the trailing 99."""
        src = (
            "import System\n"
            "fun main(): System::Int\n"
            "    if 1 > 2\n"
            "        ret 10\n"
            "    else if 3 > 4\n"
            "        ret 20\n"
            "    ret 99\n"
        )
        self.assertEqual(99, compile_and_run_stdlib(src))

    def test_nested_if_else(self):
        """Outer if-else's true branch contains a nested if-else.
        outer's `1 < 2` true; inner's `5 > 100` false → inner else returns 42."""
        src = (
            "import System\n"
            "fun main(): System::Int\n"
            "    if 1 < 2\n"
            "        if 5 > 100\n"
            "            ret 1\n"
            "        else\n"
            "            ret 42\n"
            "    else\n"
            "        ret 99\n"
            "    ret 0\n"
        )
        self.assertEqual(42, compile_and_run_stdlib(src))


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
