"""End-to-end tests for the new String operations and primitive Float type.

Each test compiles a tiny yafl program against the stdlib, runs it, and
asserts a specific exit code chosen so common slip-ups produce a different
code rather than a coincidental success.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase

from tests.testutil import compile_and_run_stdlib


class TestStringOps(TestCase):

    def test_length_of_empty(self):
        src = """namespace Main
import System

fun main(): System::Int
  ret length("")
"""
        self.assertEqual(0, compile_and_run_stdlib(src))

    def test_length_short(self):
        src = """namespace Main
import System

fun main(): System::Int
  ret length("hello")
"""
        self.assertEqual(5, compile_and_run_stdlib(src))

    def test_length_long(self):
        # Longer than a packed string (>7 bytes), forcing the heap path.
        src = """namespace Main
import System

fun main(): System::Int
  ret length("hello, world!!")
"""
        self.assertEqual(14, compile_and_run_stdlib(src))

    def test_slice_round_trip(self):
        # slice("abcdef", 1, 4) == "bcd"; length is 3.
        src = """namespace Main
import System

fun main(): System::Int
  ret length(slice("abcdef", 1, 4))
"""
        self.assertEqual(3, compile_and_run_stdlib(src))

    def test_compare_equal(self):
        src = """namespace Main
import System

fun main(): System::Int
  ret compare("abc", "abc") + 7
"""
        self.assertEqual(7, compile_and_run_stdlib(src))

    def test_compare_lt(self):
        # compare("abc", "abd") returns negative; we add 100 to make exit code positive.
        src = """namespace Main
import System

fun main(): System::Int
  ret 100 + compare("abc", "abd")
"""
        rc = compile_and_run_stdlib(src)
        self.assertLess(rc, 100)
        self.assertGreaterEqual(rc, 0)

    def test_string_eq_operator(self):
        src = """namespace Main
import System

fun main(): System::Int
  let a: System::String = "hi"
  let b: System::String = "hi"
  ret a = b ? 0 : 1
"""
        self.assertEqual(0, compile_and_run_stdlib(src))

    def test_string_lt_operator(self):
        src = """namespace Main
import System

fun main(): System::Int
  let a: System::String = "abc"
  let b: System::String = "abd"
  ret a < b ? 0 : 1
"""
        self.assertEqual(0, compile_and_run_stdlib(src))

    def test_at_returns_single_byte(self):
        src = """namespace Main
import System

fun main(): System::Int
  ret length(at("hello", 1))
"""
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_parseInt_valid(self):
        src = """namespace Main
import System

fun main(): System::Int
  ret match(parseInt("42"))
    (n: System::Int) => n
    (x: System::None) => 99
"""
        self.assertEqual(42, compile_and_run_stdlib(src))

    def test_parseInt_negative(self):
        src = """namespace Main
import System

fun main(): System::Int
  ret match(parseInt("-7"))
    (n: System::Int) => 100 + n
    (x: System::None) => 99
"""
        self.assertEqual(93, compile_and_run_stdlib(src))

    def test_parseInt_invalid(self):
        src = """namespace Main
import System

fun main(): System::Int
  ret match(parseInt("notanumber"))
    (n: System::Int) => 1
    (x: System::None) => 0
"""
        self.assertEqual(0, compile_and_run_stdlib(src))


class TestFloatOps(TestCase):

    def test_literal_round_trip(self):
        # Float -> Int truncation
        src = """namespace Main
import System

fun main(): System::Int
  let f: System::Float = 3.5
  ret Int(f)
"""
        self.assertEqual(3, compile_and_run_stdlib(src))

    def test_addition(self):
        src = """namespace Main
import System

fun main(): System::Int
  let a: System::Float = 1.5
  let b: System::Float = 2.25
  ret Int(a + b)
"""
        self.assertEqual(3, compile_and_run_stdlib(src))

    def test_int_to_float_to_int_round_trip(self):
        src = """namespace Main
import System

fun main(): System::Int
  let f: System::Float = Float(42)
  ret Int(f)
"""
        self.assertEqual(42, compile_and_run_stdlib(src))

    def test_float_division(self):
        src = """namespace Main
import System

fun main(): System::Int
  let a: System::Float = 7.0
  let b: System::Float = 2.0
  ret Int(a / b)
"""
        self.assertEqual(3, compile_and_run_stdlib(src))

    def test_float_comparison(self):
        src = """namespace Main
import System

fun main(): System::Int
  let a: System::Float = 1.5
  let b: System::Float = 2.5
  ret a < b ? 0 : 1
"""
        self.assertEqual(0, compile_and_run_stdlib(src))

    def test_isNaN_on_real(self):
        src = """namespace Main
import System

fun main(): System::Int
  let a: System::Float = 1.0
  ret isNaN(a) ? 1 : 0
"""
        self.assertEqual(0, compile_and_run_stdlib(src))

    def test_parseFloat_valid(self):
        src = """namespace Main
import System

fun main(): System::Int
  ret match(parseFloat("2.5"))
    (f: System::Float) => Int(f * 10.0)
    (x: System::None) => 99
"""
        self.assertEqual(25, compile_and_run_stdlib(src))

    def test_parseFloat_invalid(self):
        src = """namespace Main
import System

fun main(): System::Int
  ret match(parseFloat("not a number"))
    (f: System::Float) => 1
    (x: System::None) => 0
"""
        self.assertEqual(0, compile_and_run_stdlib(src))


class TestConstants(TestCase):

    def test_user_defined_float_const_inlines(self):
        src = """namespace Main
import System
let [const] HALF: System::Float = 0.5
fun main(): System::Int
  let v: System::Float = HALF
  ret Int(v + v)
"""
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_stdlib_PI_is_inlined(self):
        # PI is declared in float.yafl; multiplying it by 10 and truncating
        # should give 31 — proves the constant is reachable and has the
        # expected value.
        src = """namespace Main
import System
fun main(): System::Int
  let r: System::Float = PI * 10.0
  ret Int(r)
"""
        self.assertEqual(31, compile_and_run_stdlib(src))

    def test_stdlib_TAU_equals_two_PI(self):
        # PI and TAU are both inlined literals; PI + PI must be bit-identical
        # to TAU, so equality holds exactly.
        src = """namespace Main
import System
fun main(): System::Int
  ret PI + PI = TAU ? 0 : 1
"""
        self.assertEqual(0, compile_and_run_stdlib(src))

    def test_const_with_non_literal_is_rejected(self):
        # [const] requires a literal value. A function call doesn't qualify.
        src = """namespace Main
import System
fun zero(): System::Float
  ret 0.0
let [const] BAD: System::Float = zero()
fun main(): System::Int
  ret Int(BAD)
"""
        # Compilation must produce no C code (errors are emitted instead).
        import compiler as c
        result = c.compile([c.Input(src, "test.yafl")], use_stdlib=True, just_testing=False)
        self.assertEqual("", result)
