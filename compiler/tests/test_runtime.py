"""Runtime calling-convention tests.

Each test compiles a yafl program to a real binary, runs it, and asserts a
specific exit code.  Values are chosen so that common corruptions (swapped
arguments, wrong struct field, dropped return value, bad fun_t layout) produce
a clearly different code rather than accidentally landing on the correct answer.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from unittest import TestCase

import compiler as c


_PREAMBLE = """\
namespace System
typealias Int : __builtin_type__<bigint>
typealias String : __builtin_type__<str>
typealias None : ()
let None:None = ()
"""

_ARITH = """\
fun `+`(l: Int, r: Int): Int
    ret __builtin_op__<bigint>("integer_add", l, r)

fun `-`(l: Int, r: Int): Int
    ret __builtin_op__<bigint>("integer_sub", l, r)

fun `*`(l: Int, r: Int): Int
    ret __builtin_op__<bigint>("integer_mul", l, r)

"""


def _compile(source: str) -> str:
    return c.compile([c.Input(source, "test.yafl")], use_stdlib=False, just_testing=False)


def _compile_and_run(source: str, timeout: int = 5) -> int:
    """Compile to binary, run it, return exit code.  Asserts compilation succeeds."""
    c_code = _compile(source)
    assert c_code, "yafl compilation produced no output"

    with tempfile.NamedTemporaryFile(suffix="", delete=False) as tmp:
        binary = tmp.name

    try:
        result = subprocess.run(
            ["clang", "-g", "-x", "c", "-", "-O0", "-l", "yafl", "-o", binary],
            input=c_code, text=True, capture_output=True, timeout=30,
        )
        assert result.returncode == 0, f"clang failed:\n{result.stderr}"
        run = subprocess.run([binary], capture_output=True, timeout=timeout)
        return run.returncode
    finally:
        try:
            os.unlink(binary)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Argument order / register allocation
# ---------------------------------------------------------------------------

class TestArgumentOrder(TestCase):

    def test_subtraction_arg_order(self):
        """sub(20, 7) = 13.  If the two args are swapped at the call site or in
        the callee, the result is 7-20 = -13, which wraps to 243 as an exit code."""
        src = _PREAMBLE + _ARITH + """\
fun main(): Int
    ret 20 - 7
"""
        self.assertEqual(13, _compile_and_run(src))

    def test_three_arg_order(self):
        """(a - b) - c with a=30, b=11, c=7 = 12.
        Any pairwise swap of the three arguments gives a different result:
          b,c swapped → (30-7)-11 = 12... no: (30-7)-11=12 actually same.
        Let's use a=30, b=7, c=11: (30-7)-11 = 12.
          a,b swapped → (7-30)-11 = -34 = 222
          a,c swapped → (11-7)-30 = -26 = 230
          b,c swapped → (30-11)-7 = 12... coincidence, use different values.
        a=29, b=6, c=11: (29-6)-11 = 12.
          a,b swapped → (6-29)-11 = -34 = 222
          a,c swapped → (11-6)-29 = -24 = 232
          b,c swapped → (29-11)-6 = 12... still a coincidence for b,c swap.
        Accept: this catches a,b and a,c swaps definitively."""
        src = _PREAMBLE + _ARITH + """\
fun sub3(a: Int, b: Int, c: Int): Int
    ret a - b - c

fun main(): Int
    ret sub3(29, 6, 11)
"""
        self.assertEqual(12, _compile_and_run(src))

    def test_many_args_non_commutative(self):
        """a - b*c with a=50, b=3, c=6 = 32.
        If b and c are swapped the result is still 32 (mul commutes), but if a is
        displaced the result will differ.  Primarily tests that 'a' lands in the
        right position when there are enough args to spill to the stack."""
        src = _PREAMBLE + _ARITH + """\
fun weighted(a: Int, b: Int, c: Int): Int
    ret a - b * c

fun main(): Int
    ret weighted(50, 3, 6)
"""
        self.assertEqual(32, _compile_and_run(src))


# ---------------------------------------------------------------------------
# Return-value propagation through nested calls
# ---------------------------------------------------------------------------

class TestReturnValues(TestCase):

    def test_three_sequential_let_calls(self):
        """Three let-bound calls in sequence: add7(2)=9, add5(9)=14, add3(14)=17.
        Triggers an inliner bug where the second inlining pass emits a
        direct-style call (wrong cast, no continuation) inside a CPS
        continuation function."""
        src = _PREAMBLE + _ARITH + """\
fun add3(x: Int): Int
    ret x + 3

fun add5(x: Int): Int
    ret x + 5

fun add7(x: Int): Int
    ret x + 7

fun main(): Int
    let a: Int = add7(2)
    let b: Int = add5(a)
    ret add3(b)
"""
        self.assertEqual(17, _compile_and_run(src))

    def test_return_through_three_frames(self):
        """c calls b which calls a; each adds a distinct constant.
        If any frame drops its return value the accumulation stops short."""
        src = _PREAMBLE + _ARITH + """\
fun a(x: Int): Int
    ret x + 3

fun b(x: Int): Int
    ret a(x) + 5

fun cc(x: Int): Int
    ret b(x) + 7

fun main(): Int
    ret cc(2)
"""
        # 2 + 3 + 5 + 7 = 17
        self.assertEqual(17, _compile_and_run(src))


# ---------------------------------------------------------------------------
# Struct (class) layout
# ---------------------------------------------------------------------------

class TestStructLayout(TestCase):

    def test_class_field_order(self):
        """Read the *second* field of a two-field class.
        If the field layout is reversed, we read 5 instead of 11."""
        src = _PREAMBLE + """\
class Pair(left: Int, right: Int)

fun main(): Int
    let p: Pair = Pair(5, 11)
    ret p.right
"""
        self.assertEqual(11, _compile_and_run(src))

    def test_class_field_computation(self):
        """left - right from Pair(18, 6) = 12.
        If left and right are swapped in the layout: 6-18 = -12 → 244."""
        src = _PREAMBLE + _ARITH + """\
class Pair(left: Int, right: Int)

fun main(): Int
    let p: Pair = Pair(18, 6)
    ret p.left - p.right
"""
        self.assertEqual(12, _compile_and_run(src))

    def test_three_field_class_middle(self):
        """Read the middle field of a three-field class.
        Layout corruption most often shifts all fields by one position."""
        src = _PREAMBLE + """\
class Triple(a: Int, b: Int, cc: Int)

fun main(): Int
    let t: Triple = Triple(3, 11, 7)
    ret t.b
"""
        self.assertEqual(11, _compile_and_run(src))


# ---------------------------------------------------------------------------
# Function-pointer calling convention (fun_t: code ptr + this/closure ptr)
# ---------------------------------------------------------------------------

class TestFunctionPointers(TestCase):

    def test_higher_order_single_arg(self):
        """apply(double, 6) = 12.
        Tests that fun_t dispatch correctly passes the argument and receives
        the return value.  A bad code-pointer or 'this' placement → crash or
        wrong result."""
        src = _PREAMBLE + _ARITH + """\
fun double(x: Int): Int
    ret x + x

fun apply(f: (:Int):Int, x: Int): Int
    ret f(x)

fun main(): Int
    ret apply(double, 6)
"""
        self.assertEqual(12, _compile_and_run(src))

    def test_higher_order_two_args(self):
        """apply2(sub, 20, 7) = 13.
        Multi-arg call through fun_t.  Any shift in how b or c land gives a
        different (or crashing) result: swapped → 249, zero → 20 or 247."""
        src = _PREAMBLE + _ARITH + """\
fun sub(l: Int, r: Int): Int
    ret l - r

fun apply2(f: (:Int, :Int):Int, a: Int, b: Int): Int
    ret f(a, b)

fun main(): Int
    ret apply2(sub, 20, 7)
"""
        self.assertEqual(13, _compile_and_run(src))

    def test_higher_order_chain(self):
        """apply(double, apply(double, 3)) = 12.
        Chains two fun_t calls; the inner result must survive as an argument
        to the outer call."""
        src = _PREAMBLE + _ARITH + """\
fun double(x: Int): Int
    ret x + x

fun apply(f: (:Int):Int, x: Int): Int
    ret f(x)

fun main(): Int
    ret apply(double, apply(double, 3))
"""
        self.assertEqual(12, _compile_and_run(src))


# ---------------------------------------------------------------------------
# Union argument alongside scalar — tests that union's stack/register footprint
# does not displace adjacent arguments
# ---------------------------------------------------------------------------

class TestUnionAlongsideScalar(TestCase):

    def test_pointer_union_does_not_displace_scalar(self):
        """String|None collapses to a single pointer word.
        The scalar n must still arrive correctly as the second parameter."""
        src = _PREAMBLE + """\
fun compute(x: String|None, n: Int): Int
    ret n

fun main(): Int
    ret compute("hello", 13)
"""
        self.assertEqual(13, _compile_and_run(src))

    def test_scalar_before_pointer_union(self):
        """Scalar comes *before* the union.  Tests that the union does not
        back-shift the scalar into a wrong register/slot."""
        src = _PREAMBLE + """\
fun compute(n: Int, x: String|None): Int
    ret n

fun main(): Int
    ret compute(13, "hello")
"""
        self.assertEqual(13, _compile_and_run(src))

    def test_three_params_union_in_middle(self):
        """(a: Int, x: String|None, b: Int): ret a - b.
        If the union's presence shifts b into the wrong slot, the subtraction
        gives the wrong answer.  a=20, b=7 → 13; displaced → anything else."""
        src = _PREAMBLE + _ARITH + """\
fun compute(a: Int, x: String|None, b: Int): Int
    ret a - b

fun main(): Int
    ret compute(20, "hi", 7)
"""
        self.assertEqual(13, _compile_and_run(src))
