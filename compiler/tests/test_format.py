"""End-to-end tests for `System::format` — per-arity printf-style overloads.

The slot syntax is `{N}` where N is the 1-indexed argument number. Each
overload pre-renders its arguments via `Show<T>` and runs a concrete
template scanner that indexes into a `List<String>` of the rendered
values. Indices outside the argument range render as `?`. A `{` not
followed by digits + `}` is emitted as a literal `{`.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib


class TestFormatArity1(TestCase):

    def test_basic_substitution_length(self):
        """`"hello {1}"` + `"world"` → `"hello world"` (11 bytes)."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret length(format<String>(\"hello {1}\", \"world\"))\n"
        )
        self.assertEqual(11, compile_and_run_stdlib(src))

    def test_substitution_at_correct_position(self):
        """In `"a{1}b"` + `"X"` → `"aXb"`, byte 1 is the substituted X."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret byteAt(format<String>(\"a{1}b\", \"X\"), 1)\n"
        )
        self.assertEqual(ord('X'), compile_and_run_stdlib(src))

    def test_int_arg(self):
        """`Show<Int>` instance kicks in; `{1}` with `42` becomes `"42"`."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret length(format<Int>(\"value={1}\", 42))\n"
        )
        # "value=42" is 8 bytes
        self.assertEqual(8, compile_and_run_stdlib(src))

    def test_no_slot_template(self):
        """A template with no `{N}` substitution is emitted as-is."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret length(format<String>(\"no slots here\", \"unused\"))\n"
        )
        self.assertEqual(13, compile_and_run_stdlib(src))

    def test_literal_open_brace(self):
        """A `{` not followed by digits + `}` is emitted as a literal `{`."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret byteAt(format<String>(\"{not a slot}\", \"x\"), 0)\n"
        )
        self.assertEqual(ord('{'), compile_and_run_stdlib(src))

    def test_out_of_range_index(self):
        """`{2}` on an arity-1 call renders as `?` (degrades visibly)."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret byteAt(format<String>(\"{2}\", \"x\"), 0)\n"
        )
        self.assertEqual(ord('?'), compile_and_run_stdlib(src))


class TestFormatArity2(TestCase):

    def test_two_args_in_order(self):
        """`"{1}={2}"` + `("x", 42)` → `"x=42"` (4 bytes)."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret length(format<String, Int>(\"{1}={2}\", \"x\", 42))\n"
        )
        self.assertEqual(4, compile_and_run_stdlib(src))

    def test_two_args_reordered(self):
        """`{2}` first uses the second argument — proves N is positional,
        not auto-incrementing. `"{2}{1}"` + `("A", "B")` → `"BA"`."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret byteAt(format<String, String>(\"{2}{1}\", \"A\", \"B\"), 0)\n"
        )
        self.assertEqual(ord('B'), compile_and_run_stdlib(src))

    def test_repeated_index(self):
        """Same index can appear twice in the template."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret length(format<String, Int>(\"{1}-{1}-{2}\", \"x\", 7))\n"
        )
        # "x-x-7" is 5 bytes
        self.assertEqual(5, compile_and_run_stdlib(src))


class TestFormatArity3and4(TestCase):

    def test_three_args(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret length(format<Int, Int, Int>(\"{1}+{2}={3}\", 1, 2, 3))\n"
        )
        # "1+2=3" is 5 bytes
        self.assertEqual(5, compile_and_run_stdlib(src))

    def test_four_args(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret length(format<Int, Int, Int, Int>(\"{1}{2}{3}{4}\", 1, 2, 3, 4))\n"
        )
        self.assertEqual(4, compile_and_run_stdlib(src))

    def test_mixed_types(self):
        """All four arities exercise different Show instances mixed
        together: String + Bool + Int + Float."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  let s = format<String, Bool, Int, Float>(\"{1} {2} {3} {4}\", \"x\", 1 < 2, 42, 3.0)\n"
            # First two characters: "x " — verify the leading String
            # didn't get quoted (Show<String> is identity).
            "  ret byteAt(s, 0)\n"
        )
        self.assertEqual(ord('x'), compile_and_run_stdlib(src))

    def test_mixed_types_bool_position(self):
        """In the same mixed template, byte 2 is the leading `t` of `true`."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  let s = format<String, Bool, Int, Float>(\"{1} {2} {3} {4}\", \"x\", 1 < 2, 42, 3.0)\n"
            "  ret byteAt(s, 2)\n"
        )
        self.assertEqual(ord('t'), compile_and_run_stdlib(src))
