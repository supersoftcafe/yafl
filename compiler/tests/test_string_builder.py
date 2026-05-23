"""End-to-end tests for `System::StringBuilder`.

StringBuilder wraps a growable backing `String` plus an `_offset`. It is
`[linear,final]`: each builder is consumed exactly once (so the runtime
can mutate the backing buffer in-place via `string_copy_to_dangerously`
without aliasing risk). `append` and `toString` are both `[terminal]` on
the builder — they consume the old wrapper and (for `append`) hand back
a fresh one referencing the same or a grown buffer.

These tests exercise:
  * empty builder → empty string
  * single append (packed-short and heap-sized values)
  * geometric growth across multiple appends
  * content correctness at offsets that span the resize point
  * linear-type rules for misuse (double-use, leak)
"""
from __future__ import annotations

import io
import contextlib

import compiler as c

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib


class TestStringBuilderRuntime(TestCase):

    def test_empty(self):
        """An untouched builder produces an empty string."""
        src = (
            "import System\n"
            "fun main(): System::Int\n"
            "    let sb = System::StringBuilder()\n"
            "    let s = System::toString(sb)\n"
            "    ret System::length(s)\n"
        )
        self.assertEqual(0, compile_and_run_stdlib(src))

    def test_single_short_append_length(self):
        """One `append` of a packed short value (≤7 bytes) records the
        right length. The first append always triggers a resize off the
        packed `\"\"` starter buffer."""
        src = (
            "import System\n"
            "fun main(): System::Int\n"
            "    let sb = System::StringBuilder()\n"
            "    let sb2 = System::append(sb, \"hello\")\n"
            "    ret System::length(System::toString(sb2))\n"
        )
        self.assertEqual(5, compile_and_run_stdlib(src))

    def test_single_short_append_content_first_byte(self):
        """The first byte of the materialised string is the first byte
        of the appended value."""
        src = (
            "import System\n"
            "fun main(): System::Int\n"
            "    let sb = System::StringBuilder()\n"
            "    let sb2 = System::append(sb, \"hello\")\n"
            "    ret System::byteAt(System::toString(sb2), 0)\n"
        )
        self.assertEqual(ord('h'), compile_and_run_stdlib(src))

    def test_single_short_append_content_last_byte(self):
        """And the last byte is the last byte of the appended value —
        no off-by-one at the trailing edge."""
        src = (
            "import System\n"
            "fun main(): System::Int\n"
            "    let sb = System::StringBuilder()\n"
            "    let sb2 = System::append(sb, \"hello\")\n"
            "    ret System::byteAt(System::toString(sb2), 4)\n"
        )
        self.assertEqual(ord('o'), compile_and_run_stdlib(src))

    def test_single_heap_append_length(self):
        """The same flow with a value too long to be packed — exercises
        the `string_to_cstr` branch in `string_copy_to_dangerously` for
        a heap-allocated `value`."""
        src = (
            "import System\n"
            "fun main(): System::Int\n"
            "    let sb = System::StringBuilder()\n"
            "    let sb2 = System::append(sb, \"abcdefghijklmnop\")\n"
            "    ret System::length(System::toString(sb2))\n"
        )
        self.assertEqual(16, compile_and_run_stdlib(src))

    def test_append_empty_value(self):
        """Appending an empty string is a no-op for length; the existing
        offset and buffer are reused (no resize)."""
        src = (
            "import System\n"
            "fun main(): System::Int\n"
            "    let sb = System::StringBuilder()\n"
            "    let sb2 = System::append(sb, \"\")\n"
            "    ret System::length(System::toString(sb2))\n"
        )
        self.assertEqual(0, compile_and_run_stdlib(src))

    def test_multiple_appends_concatenate(self):
        """Two appends concatenate. `foo` (3) + `bar` (3) = 6 bytes."""
        src = (
            "import System\n"
            "fun main(): System::Int\n"
            "    let sb0 = System::StringBuilder()\n"
            "    let sb1 = System::append(sb0, \"foo\")\n"
            "    let sb2 = System::append(sb1, \"bar\")\n"
            "    ret System::length(System::toString(sb2))\n"
        )
        self.assertEqual(6, compile_and_run_stdlib(src))

    def test_second_append_content_at_join(self):
        """After two appends, byte at the join point is the first byte of
        the second value — proves `string_copy_to_dangerously` writes at
        `_offset`, not at 0."""
        src = (
            "import System\n"
            "fun main(): System::Int\n"
            "    let sb0 = System::StringBuilder()\n"
            "    let sb1 = System::append(sb0, \"foo\")\n"
            "    let sb2 = System::append(sb1, \"bar\")\n"
            "    ret System::byteAt(System::toString(sb2), 3)\n"
        )
        self.assertEqual(ord('b'), compile_and_run_stdlib(src))

    def test_many_appends_force_regrowth(self):
        """A run of appends totaling more than the initial 16-byte
        capacity exercises the resize-while-non-empty path: we grow from
        a populated buffer, which means `string_resize` must copy the
        already-written prefix correctly. 7 × 4-byte appends = 28 bytes."""
        src = (
            "import System\n"
            "fun loop(sb: System::StringBuilder, n: System::Int): System::StringBuilder\n"
            "  ret n == 0 ? sb : loop(System::append(sb, \"abcd\"), n - 1)\n"
            "fun main(): System::Int\n"
            "    let sb = loop(System::StringBuilder(), 7)\n"
            "    ret System::length(System::toString(sb))\n"
        )
        self.assertEqual(28, compile_and_run_stdlib(src))

    def test_regrowth_preserves_content(self):
        """After geometric growth, content from the very first append is
        still intact (byte 0). Catches an over-copy/under-copy bug in
        `string_resize`."""
        src = (
            "import System\n"
            "fun loop(sb: System::StringBuilder, n: System::Int): System::StringBuilder\n"
            "  ret n == 0 ? sb : loop(System::append(sb, \"abcd\"), n - 1)\n"
            "fun main(): System::Int\n"
            "    let sb0 = System::append(System::StringBuilder(), \"X\")\n"
            "    let sb = loop(sb0, 30)\n"
            "    ret System::byteAt(System::toString(sb), 0)\n"
        )
        self.assertEqual(ord('X'), compile_and_run_stdlib(src))

    def test_regrowth_preserves_content_at_tail(self):
        """And the last byte after regrowth is the expected final byte —
        proves the tail wasn't clipped by an off-by-one resize."""
        src = (
            "import System\n"
            "fun loop(sb: System::StringBuilder, n: System::Int): System::StringBuilder\n"
            "  ret n == 0 ? sb : loop(System::append(sb, \"abcd\"), n - 1)\n"
            "fun main(): System::Int\n"
            "    let sb = loop(System::StringBuilder(), 10)\n"
            "    let s = System::toString(sb)\n"
            "    ret System::byteAt(s, System::length(s) - 1)\n"
        )
        # 10 × "abcd" = 40 bytes ending in 'd'
        self.assertEqual(ord('d'), compile_and_run_stdlib(src))


class TestStringBuilderIntAppend(TestCase):
    """`append(sb, value: Int)` overload — delegates to `String(int)` and
    feeds the resulting string through the existing string-append path."""

    def test_single_digit_length(self):
        src = (
            "import System\n"
            "fun main(): System::Int\n"
            "    let sb = System::StringBuilder()\n"
            "    let sb2 = System::append(sb, 7)\n"
            "    ret System::length(System::toString(sb2))\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_single_digit_content(self):
        """`7` renders as ASCII '7' (0x37 = 55)."""
        src = (
            "import System\n"
            "fun main(): System::Int\n"
            "    let sb = System::StringBuilder()\n"
            "    let sb2 = System::append(sb, 7)\n"
            "    ret System::byteAt(System::toString(sb2), 0)\n"
        )
        self.assertEqual(ord('7'), compile_and_run_stdlib(src))

    def test_multi_digit_length(self):
        src = (
            "import System\n"
            "fun main(): System::Int\n"
            "    let sb = System::StringBuilder()\n"
            "    let sb2 = System::append(sb, 12345)\n"
            "    ret System::length(System::toString(sb2))\n"
        )
        self.assertEqual(5, compile_and_run_stdlib(src))

    def test_negative_length(self):
        """`-7` is two bytes: the leading minus plus one digit."""
        src = (
            "import System\n"
            "fun main(): System::Int\n"
            "    let sb = System::StringBuilder()\n"
            "    let sb2 = System::append(sb, -7)\n"
            "    ret System::length(System::toString(sb2))\n"
        )
        self.assertEqual(2, compile_and_run_stdlib(src))

    def test_negative_starts_with_minus(self):
        """First byte of a negative int is '-' (0x2D = 45)."""
        src = (
            "import System\n"
            "fun main(): System::Int\n"
            "    let sb = System::StringBuilder()\n"
            "    let sb2 = System::append(sb, -42)\n"
            "    ret System::byteAt(System::toString(sb2), 0)\n"
        )
        self.assertEqual(ord('-'), compile_and_run_stdlib(src))

    def test_zero_renders_as_single_digit(self):
        src = (
            "import System\n"
            "fun main(): System::Int\n"
            "    let sb = System::StringBuilder()\n"
            "    let sb2 = System::append(sb, 0)\n"
            "    ret System::length(System::toString(sb2))\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_mixed_string_then_int(self):
        """Overload dispatch picks the right append based on value type
        at each call site. `\"x=\"` (2) + `123` (3) = 5 bytes."""
        src = (
            "import System\n"
            "fun main(): System::Int\n"
            "    let sb0 = System::StringBuilder()\n"
            "    let sb1 = System::append(sb0, \"x=\")\n"
            "    let sb2 = System::append(sb1, 123)\n"
            "    ret System::length(System::toString(sb2))\n"
        )
        self.assertEqual(5, compile_and_run_stdlib(src))


class TestStringBuilderLinearity(TestCase):
    """The linear+terminal annotations are load-bearing — verify both
    misuse patterns are rejected."""

    def _reject(self, body: str, needle: str):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = c.compile([c.Input(body, "test.yafl")],
                             use_stdlib=True, just_testing=False)
        self.assertEqual("", code, "expected compile error, got C output")
        self.assertIn(needle, buf.getvalue().lower())

    def test_double_use_rejected(self):
        """Using the same builder twice violates linearity."""
        src = (
            "import System\n"
            "fun main(): System::Int\n"
            "    let sb = System::StringBuilder()\n"
            "    let s1 = System::toString(sb)\n"
            "    let s2 = System::toString(sb)\n"
            "    ret System::length(s1)\n"
        )
        self._reject(src, "times")

    def test_leak_rejected(self):
        """A builder that's allocated and never consumed must be rejected."""
        src = (
            "import System\n"
            "fun main(): System::Int\n"
            "    let sb = System::StringBuilder()\n"
            "    ret 0\n"
        )
        self._reject(src, "never used")
