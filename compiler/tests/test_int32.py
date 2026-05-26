"""End-to-end tests for Int32 — fixed-width 32-bit integer.

Int32 wraps on overflow (C/Java/Kotlin semantics); there's no implicit
conversion to/from Int — explicit `Int(_)` / `Int32(_)` cross the
boundary. These tests exercise the trait instance (BasicMath, Show),
wrap-around at INT32_MIN/MAX, the bigint↔Int32 truncation, the
Float↔Int32 conversions (clamp on overflow, NaN → 0), and parseInt32.

Each `main` returns System::Int so the assertion is encoded into the
process exit code; tests widen Int32 → Int with `Int(_)` for the result.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib


class TestInt32Arithmetic(TestCase):

    def test_add(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret Int(2i32 + 3i32)\n"
        )
        self.assertEqual(5, compile_and_run_stdlib(src))

    def test_sub(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret Int(10i32 - 7i32)\n"
        )
        self.assertEqual(3, compile_and_run_stdlib(src))

    def test_mul(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret Int(6i32 * 7i32)\n"
        )
        self.assertEqual(42, compile_and_run_stdlib(src))

    def test_div(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret Int(20i32 / 3i32)\n"
        )
        self.assertEqual(6, compile_and_run_stdlib(src))

    def test_rem(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret Int(20i32 % 3i32)\n"
        )
        self.assertEqual(2, compile_and_run_stdlib(src))

    def test_unary_neg(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret Int(-7i32) + 100\n"
        )
        # -7 + 100 = 93
        self.assertEqual(93, compile_and_run_stdlib(src))


class TestInt32Wraparound(TestCase):
    """Wrap-around at INT32_MIN/MAX matches C/Java/Kotlin."""

    def test_add_overflow_wraps_to_min(self):
        """INT32_MAX + 1 == INT32_MIN."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret (INT32_MAX + 1i32) == INT32_MIN ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_sub_underflow_wraps_to_max(self):
        """INT32_MIN - 1 == INT32_MAX."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret (INT32_MIN - 1i32) == INT32_MAX ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_neg_min_stays_min(self):
        """-INT32_MIN wraps back to INT32_MIN (its magnitude is unrepresentable).
        int32_neg uses unsigned arithmetic so this is defined wrap, not UB."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret (-INT32_MIN) == INT32_MIN ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    # INT_MIN / -1 would overflow (true quotient is +2^31) and x86's idiv
    # raises SIGFPE on the overflow trap. The C inlines paper over it by
    # checking `b == -1` and substituting the neg/zero result (Java/Kotlin
    # convention).
    def test_div_min_by_neg_one_wraps(self):
        """INT32_MIN / -1 == INT32_MIN (would overflow; we paper over)."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret (INT32_MIN / -1i32) == INT32_MIN ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_rem_min_by_neg_one_zero(self):
        """INT32_MIN % -1 == 0 (would otherwise SIGFPE)."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret Int(INT32_MIN % -1i32)\n"
        )
        self.assertEqual(0, compile_and_run_stdlib(src))


class TestInt32Comparison(TestCase):

    def test_lt(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret 3i32 < 4i32 ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_eq_true(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret 42i32 == 42i32 ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_eq_false(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret 42i32 == 41i32 ? 1 : 0\n"
        )
        self.assertEqual(0, compile_and_run_stdlib(src))

    def test_gt(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret 5i32 > 3i32 ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_min_lt_max(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret INT32_MIN < INT32_MAX ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))


class TestIntConversion(TestCase):
    """Int ↔ Int32 — widening is exact; narrowing keeps low 32 bits."""

    def test_widen_round_trips_max(self):
        """Int(INT32_MAX) == 2147483647."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret Int(INT32_MAX) == 2147483647 ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_widen_negative(self):
        """Int(-100i32) widens with sign preserved."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret Int(-100i32) == -100 ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_narrow_in_range(self):
        """truncateToInt32(INT32_MAX as Int) round-trips through Int."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret Int(truncateToInt32(2147483647)) == 2147483647 ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_narrow_truncates_high_bits(self):
        """truncateToInt32(2^32) narrows to 0 (low 32 bits)."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret truncateToInt32(4294967296) == 0i32 ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_narrow_wraps_to_neg_one(self):
        """truncateToInt32(4294967295) == -1i32 (low 32 bits of 2^32-1)."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret truncateToInt32(4294967295) == -1i32 ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_narrow_negative_bigint(self):
        """truncateToInt32(-1) == -1i32 — sign preserved at the boundary."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret truncateToInt32(-1) == -1i32 ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))


class TestFloatConversion(TestCase):
    """Float ↔ Int32 — clamp on out-of-range, NaN → 0, trunc toward zero."""

    def test_int32_to_float(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret Int(truncateToInt32(Float(42i32)))\n"
        )
        self.assertEqual(42, compile_and_run_stdlib(src))

    def test_float_to_int32_trunc_positive(self):
        """3.7 → 3 (truncate toward zero, not floor)."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret Int(truncateToInt32(3.7))\n"
        )
        self.assertEqual(3, compile_and_run_stdlib(src))

    def test_float_to_int32_trunc_negative(self):
        """-3.7 → -3 (truncate toward zero, not floor — floor would give -4)."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret (truncateToInt32(-3.7)) == -3i32 ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_float_to_int32_clamp_high(self):
        """1e20 clamps to INT32_MAX."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret truncateToInt32(1e20) == INT32_MAX ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_float_to_int32_clamp_low(self):
        """-1e20 clamps to INT32_MIN."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret truncateToInt32(-1e20) == INT32_MIN ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_float_to_int32_nan_zero(self):
        """NaN → 0 (Kotlin/Java convention)."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret Int(truncateToInt32(0.0/0.0))\n"
        )
        self.assertEqual(0, compile_and_run_stdlib(src))


class TestStringAndShow(TestCase):

    def test_string_positive(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret length(String(42i32))\n"
        )
        self.assertEqual(2, compile_and_run_stdlib(src))

    def test_string_zero(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret byteAt(String(0i32), 0)\n"
        )
        self.assertEqual(ord('0'), compile_and_run_stdlib(src))

    def test_string_negative(self):
        """String(-42i32) begins with '-'."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret byteAt(String(-42i32), 0)\n"
        )
        self.assertEqual(ord('-'), compile_and_run_stdlib(src))

    def test_string_int32_min(self):
        """INT32_MIN renders as "-2147483648" (11 bytes)."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret length(String(INT32_MIN))\n"
        )
        self.assertEqual(11, compile_and_run_stdlib(src))

    def test_show_via_format(self):
        """Show<Int32> kicks in for {N} slots."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret length(format<Int32>(\"v={1}\", 42i32))\n"
        )
        # "v=42" is 4 bytes
        self.assertEqual(4, compile_and_run_stdlib(src))


class TestParseInt32(TestCase):

    def test_parse_in_range(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret match(parseInt32(\"42\"))\n"
            "    (v: Int32) => Int(v)\n"
            "    (n: None)  => -1\n"
        )
        self.assertEqual(42, compile_and_run_stdlib(src))

    def test_parse_negative(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret match(parseInt32(\"-7\"))\n"
            "    (v: Int32) => v == -7i32 ? 1 : 0\n"
            "    (n: None)  => 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_parse_overflow_is_none(self):
        """A value past INT32_MAX → None, not silent wrap."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret match(parseInt32(\"99999999999\"))\n"
            "    (v: Int32) => 0\n"
            "    (n: None)  => 1\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_parse_invalid_is_none(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret match(parseInt32(\"abc\"))\n"
            "    (v: Int32) => 0\n"
            "    (n: None)  => 1\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_parse_max(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret match(parseInt32(\"2147483647\"))\n"
            "    (v: Int32) => v == INT32_MAX ? 1 : 0\n"
            "    (n: None)  => 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_parse_min(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret match(parseInt32(\"-2147483648\"))\n"
            "    (v: Int32) => v == INT32_MIN ? 1 : 0\n"
            "    (n: None)  => 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))


class TestHashOf(TestCase):
    """hashOf<Int32> returns a non-negative Int (matches the BasicEquality
    contract). Widening to bigint sidesteps the -INT32_MIN wrap.

    A tiny generic wrapper threads the `where BasicEquality<T>` constraint —
    a top-level `main` can't carry the where clause directly so dispatch
    routes through this helper, mirroring how Dict/Set internally do."""

    _PRELUDE = (
        "import System\n"
        "fun _h<T>(v: T): Int where BasicEquality<T>\n"
        "  ret hashOf(v)\n"
    )

    def test_hash_positive(self):
        src = self._PRELUDE + (
            "fun main(): Int\n"
            "  ret _h<Int32>(42i32) == 42 ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_hash_min_is_nonnegative(self):
        """hashOf(INT32_MIN) must be >= 0 — the trait contract."""
        src = self._PRELUDE + (
            "fun main(): Int\n"
            "  let h = _h<Int32>(INT32_MIN)\n"
            "  ret 0 - h < 1 ? 1 : 0\n"
        )
        # "0 - h < 1" is true iff h >= 0; rewritten to avoid `>=` after
        # a generic call site, which trips the parser.
        self.assertEqual(1, compile_and_run_stdlib(src))
