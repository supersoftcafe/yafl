"""End-to-end tests for the `Show<T>` trait and its built-in instances.

`Show<T>` declares `show(value: T): String`. Instances live in each
type's stdlib file (Int/Bool in `integer.yafl`, String in `string.yafl`,
Float in `float.yafl`). `show(...)` is dispatched via the trait dictionary
when called from a `where Show<T>` context.

`Show<String>` is deliberately identity (no quotes) — the format function
wants the natural representation. A debug-quoted variant, if ever needed,
should be a separate `Debug<T>` trait, not an overload of Show.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib


# A tiny generic wrapper threads the `where Show<T>` constraint that
# trait-method calls require — the test programs use this rather than
# repeating the boilerplate at each call site.
_PRELUDE = (
    "import System\n"
    "fun _showLen<T>(v: T): Int where Show<T>\n"
    "  ret length(show(v))\n"
    "fun _showByte<T>(v: T, at: Int): Int where Show<T>\n"
    "  ret byteAt(show(v), at)\n"
)


class TestShowInt(TestCase):

    def test_positive_length(self):
        src = _PRELUDE + (
            "fun main(): Int\n"
            "  ret _showLen<Int>(12345)\n"
        )
        self.assertEqual(5, compile_and_run_stdlib(src))

    def test_zero_length(self):
        """`show(0)` is `\"0\"` — a single digit, not the empty string."""
        src = _PRELUDE + (
            "fun main(): Int\n"
            "  ret _showLen<Int>(0)\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_negative_has_minus(self):
        """`show(-42)` begins with `-`."""
        src = _PRELUDE + (
            "fun main(): Int\n"
            "  ret _showByte<Int>(-42, 0)\n"
        )
        self.assertEqual(ord('-'), compile_and_run_stdlib(src))

    def test_first_digit(self):
        """`show(12345)` begins with `1`."""
        src = _PRELUDE + (
            "fun main(): Int\n"
            "  ret _showByte<Int>(12345, 0)\n"
        )
        self.assertEqual(ord('1'), compile_and_run_stdlib(src))


class TestShowString(TestCase):
    """`Show<String>` is identity — `show(s)` returns `s` unchanged."""

    def test_identity_length(self):
        src = _PRELUDE + (
            "fun main(): Int\n"
            "  ret _showLen<String>(\"hello\")\n"
        )
        self.assertEqual(5, compile_and_run_stdlib(src))

    def test_identity_content(self):
        """No quote characters are added — first byte is `h`, not `\"`."""
        src = _PRELUDE + (
            "fun main(): Int\n"
            "  ret _showByte<String>(\"hello\", 0)\n"
        )
        self.assertEqual(ord('h'), compile_and_run_stdlib(src))

    def test_empty_string(self):
        """Empty string shows as empty — length 0, no escapes inserted."""
        src = _PRELUDE + (
            "fun main(): Int\n"
            "  ret _showLen<String>(\"\")\n"
        )
        self.assertEqual(0, compile_and_run_stdlib(src))


class TestShowBool(TestCase):

    def test_true_length(self):
        """`show(true)` is `\"true\"` — 4 bytes."""
        src = _PRELUDE + (
            "fun main(): Int\n"
            "  ret _showLen<Bool>(1 < 2)\n"
        )
        self.assertEqual(4, compile_and_run_stdlib(src))

    def test_false_length(self):
        """`show(false)` is `\"false\"` — 5 bytes."""
        src = _PRELUDE + (
            "fun main(): Int\n"
            "  ret _showLen<Bool>(1 > 2)\n"
        )
        self.assertEqual(5, compile_and_run_stdlib(src))

    def test_true_first_byte(self):
        src = _PRELUDE + (
            "fun main(): Int\n"
            "  ret _showByte<Bool>(1 < 2, 0)\n"
        )
        self.assertEqual(ord('t'), compile_and_run_stdlib(src))

    def test_false_first_byte(self):
        src = _PRELUDE + (
            "fun main(): Int\n"
            "  ret _showByte<Bool>(1 > 2, 0)\n"
        )
        self.assertEqual(ord('f'), compile_and_run_stdlib(src))


class TestShowFloat(TestCase):
    """The Float instance delegates to `String(f: Float)` (which goes
    through libyafl's `string_from_float`). We don't pin the exact byte
    count — that depends on the underlying formatter — but we do check
    the result is non-empty and digit-led for a simple positive value."""

    def test_positive_nonempty(self):
        src = _PRELUDE + (
            "fun main(): Int\n"
            "  ret _showLen<Float>(3.14) > 0 ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_positive_starts_with_digit(self):
        src = _PRELUDE + (
            "fun main(): Int\n"
            "  ret _showByte<Float>(3.14, 0)\n"
        )
        # '3' is 0x33 = 51
        self.assertEqual(ord('3'), compile_and_run_stdlib(src))
