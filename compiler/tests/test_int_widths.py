"""End-to-end tests for Int8/Int16/Int64 — the smaller and larger
fixed-width integer types added alongside Int32.

The pattern matches `test_int32.py` (wrap-on-overflow, target-first
conversion naming, lossy narrowings spelled `truncateToInt<N>`).
Tests here focus on the *width-specific* behaviour — overflow boundary
at INT<N>_MIN/MAX, sign-extending widening, and that the traits
dispatch correctly — rather than duplicating every arithmetic case
from test_int32.py.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib


# ─── Int8 ────────────────────────────────────────────────────────────────

class TestInt8(TestCase):

    def test_add(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret Int(40i8 + 2i8)\n"
        )
        self.assertEqual(42, compile_and_run_stdlib(src))

    def test_add_wraps_at_max(self):
        """127 + 1 wraps to -128."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret (INT8_MAX + 1i8) == INT8_MIN ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_neg_min_stays_min(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret (-INT8_MIN) == INT8_MIN ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_div_min_by_neg_one_wraps(self):
        """INT8_MIN / -1 == INT8_MIN (papered over from x86 SIGFPE)."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret (INT8_MIN / -1i8) == INT8_MIN ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_compare(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret INT8_MIN < INT8_MAX ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_widen_to_int(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret Int(100i8)\n"
        )
        self.assertEqual(100, compile_and_run_stdlib(src))

    def test_widen_to_int32(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret Int(Int32(-5i8)) == -5 ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_truncate_from_int(self):
        """truncateToInt8(300) wraps: 300 & 0xff = 44."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret Int(truncateToInt8(300))\n"
        )
        self.assertEqual(44, compile_and_run_stdlib(src))

    def test_truncate_from_int32(self):
        """truncateToInt8(257i32) wraps: 257 & 0xff = 1."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret Int(truncateToInt8(257i32))\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_truncate_from_float(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret truncateToInt8(1000.0) == INT8_MAX ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_string(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret length(String(INT8_MIN))\n"
        )
        # "-128" is 4 bytes
        self.assertEqual(4, compile_and_run_stdlib(src))

    def test_parse_round_trip(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret match(parseInt8(\"42\"))\n"
            "    (v: Int8) => Int(v)\n"
            "    (n: None) => -1\n"
        )
        self.assertEqual(42, compile_and_run_stdlib(src))

    def test_parse_overflow_is_none(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret match(parseInt8(\"500\"))\n"
            "    (v: Int8) => 0\n"
            "    (n: None) => 1\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))


# ─── Int16 ────────────────────────────────────────────────────────────────

class TestInt16(TestCase):

    def test_add(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret Int(1000i16 + 234i16)\n"
        )
        # 1234 fits — but exit code is low byte = 1234 % 256 = 210. Use bool form.
        # Actually 1234 doesn't fit a byte. Use comparison.
        self.assertEqual(1234 & 0xff, compile_and_run_stdlib(src))

    def test_add_wraps_at_max(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret (INT16_MAX + 1i16) == INT16_MIN ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_div_min_by_neg_one_wraps(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret (INT16_MIN / -1i16) == INT16_MIN ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_widen_to_int(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret Int(-1234i16) == -1234 ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_widen_to_int32(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret Int32(INT16_MAX) == 32767i32 ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_truncate_from_int(self):
        """truncateToInt16(70000) wraps: 70000 & 0xffff = 4464."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret Int(truncateToInt16(70000)) == 4464 ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_truncate_from_int32(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret truncateToInt16(65537i32) == 1i16 ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_string_min(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret length(String(INT16_MIN))\n"
        )
        # "-32768" is 6 bytes
        self.assertEqual(6, compile_and_run_stdlib(src))


# ─── Int64 ────────────────────────────────────────────────────────────────

class TestInt64(TestCase):

    def test_add(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret Int(40i64 + 2i64)\n"
        )
        self.assertEqual(42, compile_and_run_stdlib(src))

    def test_add_wraps_at_max(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret (INT64_MAX + 1i64) == INT64_MIN ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_neg_min_stays_min(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret (-INT64_MIN) == INT64_MIN ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_div_min_by_neg_one_wraps(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret (INT64_MIN / -1i64) == INT64_MIN ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_widen_to_int(self):
        """Int64 → Int (bigint) — exact for the full int64 range."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret Int(INT64_MAX) == 9223372036854775807 ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_truncate_from_int(self):
        """truncateToInt64(2^64) wraps to 0."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret truncateToInt64(18446744073709551616) == 0i64 ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_truncate_from_int_keeps_low_bits(self):
        """truncateToInt64 of 2^64+5 keeps the low 64 bits = 5."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret truncateToInt64(18446744073709551621) == 5i64 ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_int64_to_int32_truncate(self):
        """truncateToInt32(INT64_MAX) keeps the low 32 bits = -1."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret truncateToInt32(INT64_MAX) == -1i32 ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_string_min(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret length(String(INT64_MIN))\n"
        )
        # "-9223372036854775808" is 20 bytes
        self.assertEqual(20, compile_and_run_stdlib(src))

    def test_parse_round_trip(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret match(parseInt64(\"9223372036854775807\"))\n"
            "    (v: Int64) => v == INT64_MAX ? 1 : 0\n"
            "    (n: None)  => 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_parse_overflow_is_none(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret match(parseInt64(\"99999999999999999999999\"))\n"
            "    (v: Int64) => 0\n"
            "    (n: None)  => 1\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))


# ─── Cross-width interactions ─────────────────────────────────────────────

class TestCrossWidth(TestCase):
    """Widening (exact) and narrowing (truncateTo*) at the boundaries
    between the four fixed-width int types."""

    def test_widen_chain(self):
        """Int8 → Int16 → Int32 → Int64 — sign preserved at every step."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  let a: Int16 = Int16(-5i8)\n"
            "  let b: Int32 = Int32(a)\n"
            "  let c: Int64 = Int64(b)\n"
            "  ret c == -5i64 ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_narrow_chain(self):
        """truncateToInt8(INT64_MAX) — low 8 bits of 0x7fffffffffffffff = 0xff = -1."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret truncateToInt8(INT64_MAX) == -1i8 ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))


# ─── Show / hashOf ────────────────────────────────────────────────────────

class TestShowAndHash(TestCase):
    _PRELUDE = (
        "import System\n"
        "fun _h<T>(v: T): Int where BasicEquality<T>\n"
        "  ret hashOf(v)\n"
    )

    def test_show_int8_via_format(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret length(format<Int8>(\"v={1}\", -5i8))\n"
        )
        # "v=-5" is 4 bytes
        self.assertEqual(4, compile_and_run_stdlib(src))

    def test_show_int64_via_format(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret length(format<Int64>(\"v={1}\", 42i64))\n"
        )
        self.assertEqual(4, compile_and_run_stdlib(src))

    def test_hash_int8_nonneg(self):
        src = self._PRELUDE + (
            "fun main(): Int\n"
            "  let h = _h<Int8>(INT8_MIN)\n"
            "  ret 0 - h < 1 ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_hash_int64_nonneg(self):
        src = self._PRELUDE + (
            "fun main(): Int\n"
            "  let h = _h<Int64>(INT64_MIN)\n"
            "  ret 0 - h < 1 ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))
