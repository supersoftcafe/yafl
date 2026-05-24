"""End-to-end tests for `System::Set<T>`.

`Set<T>` is a thin wrapper around `Dict<T,()>`. It inherits the AVL-tree
shape and `BasicEquality<T>`-driven hashing of Dict. Functional /
persistent: every operation returns a new Set; the original is unchanged.

These tests exercise add/contains/remove/size for the typical cases
(empty, single, duplicates, missing) across both Int and String keys.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib


class TestSetBasic(TestCase):

    def test_empty_size(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret size<Int>(Set<Int>())\n"
        )
        self.assertEqual(0, compile_and_run_stdlib(src))

    def test_empty_does_not_contain(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret contains<Int>(Set<Int>(), 42) ? 1 : 0\n"
        )
        self.assertEqual(0, compile_and_run_stdlib(src))

    def test_add_then_contains(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  let s = add<Int>(Set<Int>(), 42)\n"
            "  ret contains<Int>(s, 42) ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_add_then_size(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  let s = add<Int>(add<Int>(add<Int>(Set<Int>(), 1), 2), 3)\n"
            "  ret size<Int>(s)\n"
        )
        self.assertEqual(3, compile_and_run_stdlib(src))


class TestSetSemantics(TestCase):

    def test_duplicate_add_is_idempotent_for_size(self):
        """Adding the same value twice doesn't grow the set."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  let s = add<Int>(add<Int>(Set<Int>(), 5), 5)\n"
            "  ret size<Int>(s)\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_remove_present(self):
        """Removing a present value drops it from the set."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  let s = remove<Int>(add<Int>(Set<Int>(), 7), 7)\n"
            "  ret contains<Int>(s, 7) ? 1 : 0\n"
        )
        self.assertEqual(0, compile_and_run_stdlib(src))

    def test_remove_absent_is_noop(self):
        """Removing an absent value leaves the set unchanged."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  let s = remove<Int>(add<Int>(Set<Int>(), 1), 99)\n"
            "  ret size<Int>(s)\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_remove_then_size(self):
        """Remove reduces size by one when the value was present."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  let s0 = add<Int>(add<Int>(add<Int>(Set<Int>(), 1), 2), 3)\n"
            "  let s1 = remove<Int>(s0, 2)\n"
            "  ret size<Int>(s1)\n"
        )
        self.assertEqual(2, compile_and_run_stdlib(src))

    def test_original_set_unchanged_after_remove(self):
        """Persistent semantics — the input to `remove` is untouched."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  let s0 = add<Int>(Set<Int>(), 1)\n"
            "  let s1 = remove<Int>(s0, 1)\n"
            # s0 still contains 1 even though we removed it from s1
            "  ret contains<Int>(s0, 1) ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))


class TestSetStringKeys(TestCase):
    """Verify `BasicEquality<String>` routes through correctly — the
    Set machinery is generic over T, so String keys must work without
    any per-type re-instantiation in user code."""

    def test_add_string(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  let s = add<String>(Set<String>(), \"hello\")\n"
            "  ret contains<String>(s, \"hello\") ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_string_distinguishes_keys(self):
        """Different strings are different keys; size is 2."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  let s = add<String>(add<String>(Set<String>(), \"a\"), \"b\")\n"
            "  ret size<String>(s)\n"
        )
        self.assertEqual(2, compile_and_run_stdlib(src))
