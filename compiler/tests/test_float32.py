"""End-to-end tests for Float32 — IEEE-754 binary32.

No auto-promotion to/from Float (=Float64) or the integer types; explicit
`Float32(_)` / `Float(_)` / `Int(_)` / `Int32(_)` cross the boundary.
These exercise the BasicMath/Show trait instances, NaN handling, both
conversion directions, String rendering, and parseFloat32 round-tripping.

main returns Int (exit code is the low byte) so assertions encode their
result into a small Int via comparison.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib


class TestFloat32Arithmetic(TestCase):

    def test_add(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret truncateToInt(2.5f32 + 3.5f32)\n"
        )
        self.assertEqual(6, compile_and_run_stdlib(src))

    def test_sub(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret truncateToInt(10.5f32 - 4.5f32)\n"
        )
        self.assertEqual(6, compile_and_run_stdlib(src))

    def test_mul(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret truncateToInt(2.5f32 * 4.0f32)\n"
        )
        self.assertEqual(10, compile_and_run_stdlib(src))

    def test_div(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret truncateToInt(15.0f32 / 4.0f32)\n"
        )
        self.assertEqual(3, compile_and_run_stdlib(src))  # 3.75 truncs to 3

    def test_rem(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret truncateToInt(10.0f32 % 3.0f32)\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_unary_neg(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret truncateToInt(-(7.5f32)) + 100\n"
        )
        # -7 (trunc of -7.5) + 100 = 93
        self.assertEqual(93, compile_and_run_stdlib(src))


class TestFloat32Comparison(TestCase):

    def test_lt(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret 1.5f32 < 2.5f32 ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_eq_true(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret 3.0f32 == 3.0f32 ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_eq_false(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret 3.0f32 == 4.0f32 ? 1 : 0\n"
        )
        self.assertEqual(0, compile_and_run_stdlib(src))

    def test_gt(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret 5.0f32 > 3.0f32 ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))


class TestFloat32NaN(TestCase):

    def test_nan_not_eq_nan(self):
        """NaN != NaN under IEEE-754 — confirm the trait dispatches correctly."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  let nan: Float32 = 0.0f32 / 0.0f32\n"
            "  ret nan == nan ? 0 : 1\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_is_nan_true(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  let nan: Float32 = 0.0f32 / 0.0f32\n"
            "  ret isNaN(nan) ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_is_nan_false(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret isNaN(1.5f32) ? 0 : 1\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))


class TestFloat32Conversions(TestCase):
    """Float32 ↔ Int, Int32, Float — no auto-promotion; explicit only."""

    def test_int_to_float32(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret truncateToInt(Float32(42))\n"
        )
        self.assertEqual(42, compile_and_run_stdlib(src))

    def test_int32_to_float32(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  let v: Float32 = Float32(42i32)\n"
            "  ret truncateToInt(v)\n"
        )
        self.assertEqual(42, compile_and_run_stdlib(src))

    def test_float64_to_float32_narrow(self):
        """Float64 → Float32 may lose precision but the order of magnitude survives."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  let v: Float32 = Float32(3.5)\n"
            "  ret truncateToInt(v)\n"
        )
        self.assertEqual(3, compile_and_run_stdlib(src))

    def test_float32_to_float64_widen(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  let v: Float = Float(3.5f32)\n"
            "  ret truncateToInt(v)\n"
        )
        self.assertEqual(3, compile_and_run_stdlib(src))

    def test_float32_to_int_trunc(self):
        """3.7 truncates toward zero → 3."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret truncateToInt(3.7f32)\n"
        )
        self.assertEqual(3, compile_and_run_stdlib(src))

    def test_float32_to_int32_clamp_high(self):
        """A large float32 clamps to INT32_MAX."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret truncateToInt32(1e20f32) == INT32_MAX ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_float32_to_int32_clamp_low(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret truncateToInt32(-1e20f32) == INT32_MIN ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_float32_to_int32_nan_zero(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  let nan: Float32 = 0.0f32 / 0.0f32\n"
            "  ret Int(truncateToInt32(nan))\n"
        )
        self.assertEqual(0, compile_and_run_stdlib(src))


class TestFloat32StringAndShow(TestCase):

    def test_string_starts_with_digit(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret byteAt(String(3.5f32), 0)\n"
        )
        self.assertEqual(ord('3'), compile_and_run_stdlib(src))

    def test_string_negative_starts_minus(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret byteAt(String(-3.5f32), 0)\n"
        )
        self.assertEqual(ord('-'), compile_and_run_stdlib(src))

    def test_show_via_format(self):
        """Show<Float32> dispatches correctly through format."""
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret byteAt(format<Float32>(\"v={1}\", 7.0f32), 0)\n"
        )
        self.assertEqual(ord('v'), compile_and_run_stdlib(src))


class TestParseFloat32(TestCase):

    def test_parse_simple(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret match(parseFloat32(\"2.5\"))\n"
            "    (v: Float32) => truncateToInt(v)\n"
            "    (n: None)    => -1\n"
        )
        self.assertEqual(2, compile_and_run_stdlib(src))

    def test_parse_negative(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret match(parseFloat32(\"-7.0\"))\n"
            "    (v: Float32) => v == -7.0f32 ? 1 : 0\n"
            "    (n: None)    => 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_parse_invalid_is_none(self):
        src = (
            "import System\n"
            "fun main(): Int\n"
            "  ret match(parseFloat32(\"abc\"))\n"
            "    (v: Float32) => 0\n"
            "    (n: None)    => 1\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))


class TestFloat32Hash(TestCase):

    _PRELUDE = (
        "import System\n"
        "fun _h<T>(v: T): Int where BasicEquality<T>\n"
        "  ret hashOf(v)\n"
    )

    def test_hash_is_nonnegative(self):
        src = self._PRELUDE + (
            "fun main(): Int\n"
            "  let h = _h<Float32>(3.14f32)\n"
            "  ret 0 - h < 1 ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_hash_zero_equals_negative_zero(self):
        """+0.0 and -0.0 compare equal under ==; hashes must agree."""
        src = self._PRELUDE + (
            "fun main(): Int\n"
            "  let pos = _h<Float32>(0.0f32)\n"
            "  let neg = _h<Float32>(-0.0f32)\n"
            "  ret pos == neg ? 1 : 0\n"
        )
        self.assertEqual(1, compile_and_run_stdlib(src))
