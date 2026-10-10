"""A malformed numeric literal is reported at the literal, in the same words
by both compilers, wherever it is written — an optional part of a statement
(a `let`'s value) included.

Python used to decode with `int()` and `float()` and passed their messages
through ("invalid literal for int() with base 10"), and lost the error inside
a `let`; the port never checked a float literal at all, so `1e5e5` compiled.
Both now check the lexeme against one grammar: an integer is digits of its
radix, with underscores; a float is `digits[.digits][e[+-]digits]`, with
underscores, then an optional `f32`/`f64`.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_errors


def _main(body: str) -> str:
    return "import System\nfun main(): System::Int\n" + body


class TestIntegerLiteralErrors(TestCase):
    def test_bad_digit(self):
        self.assertEqual("test.yafl[3:7] - invalid digit in integer literal\n",
                         compile_errors(_main("  ret 12x\n")))

    def test_bad_digit_for_the_radix(self):
        self.assertEqual("test.yafl[3:7] - invalid digit in integer literal\n",
                         compile_errors(_main("  ret 0o9\n")))

    def test_no_digits(self):
        self.assertEqual("test.yafl[3:7] - integer literal has no digits\n",
                         compile_errors(_main("  ret 0x\n")))

    def test_bad_digit_in_a_let(self):
        self.assertEqual("test.yafl[3:11] - invalid digit in integer literal\n",
                         compile_errors(_main("  let f = 12x\n  ret f\n")))


class TestFloatLiteralErrors(TestCase):
    def test_two_exponents(self):
        self.assertEqual("test.yafl[3:21] - invalid float literal\n",
                         compile_errors(_main("  ret truncateToInt(1e5e5)\n")))

    def test_exponent_without_digits(self):
        self.assertEqual("test.yafl[3:21] - invalid float literal\n",
                         compile_errors(_main("  ret truncateToInt(1e)\n")))

    def test_unknown_suffix(self):
        self.assertEqual("test.yafl[3:21] - invalid float literal\n",
                         compile_errors(_main("  ret truncateToInt(1.5f16)\n")))

    def test_bad_float_in_a_let(self):
        self.assertEqual("test.yafl[3:11] - invalid float literal\n",
                         compile_errors(_main("  let f = 1.5x\n  ret truncateToInt(f)\n")))


class TestBuiltinOpErrors(TestCase):
    def test_first_parameter_not_a_string(self):
        # Reported at the offending argument.
        self.assertEqual("test.yafl[3:30] - __builtin_op__ first parameter must be a string\n",
                         compile_errors(_main("  ret __builtin_op__<bigint>(5, 1)\n")))

    def test_no_parameters(self):
        # Reported at the empty argument list.
        self.assertEqual("test.yafl[3:30] - __builtin_op__ first parameter must be a string\n",
                         compile_errors(_main("  ret __builtin_op__<bigint>()\n")))
