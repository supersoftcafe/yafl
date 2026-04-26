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
from pathlib import Path
from unittest import TestCase

import compiler as c

_YAFLLIB_DIR = Path(__file__).parent.parent.parent / "yafllib"
_YAFLLIB_BUILD_DIR = _YAFLLIB_DIR / "build" / "debug-unix"
_CLANG_BUILD_FLAGS = [
    "-I", str(_YAFLLIB_DIR),
    "-L", str(_YAFLLIB_BUILD_DIR),
]
_RUN_ENV = {
    **os.environ,
    "LD_LIBRARY_PATH": os.pathsep.join(filter(None, [
        str(_YAFLLIB_DIR),
        str(_YAFLLIB_BUILD_DIR),
        os.environ.get("LD_LIBRARY_PATH", ""),
    ])),
}


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
            ["clang", "-g", "-x", "c", "-", "-O0", *_CLANG_BUILD_FLAGS, "-l", "yafl", "-o", binary],
            input=c_code, text=True, capture_output=True, timeout=30,
        )
        assert result.returncode == 0, f"clang failed:\n{result.stderr}"
        run = subprocess.run([binary], capture_output=True, timeout=timeout, env=_RUN_ENV)
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


# ---------------------------------------------------------------------------
# CPS saved-variable liveness — variables that must survive across multiple
# non-tail calls (exercises __calculate_saved_vars in lowering/cps.py)
# ---------------------------------------------------------------------------

class TestCpsSavedVars(TestCase):

    def test_var_live_across_two_calls(self):
        """a is bound before two non-tail calls; it must be saved across both.
        a=add3(10)=13, b=add5(20)=25, c=add7(30)=37; result = a - b - c = -49 = 207.
        If 'a' is not correctly saved across the call that computes 'b' or 'c',
        its value is lost and the exit code differs."""
        src = _PREAMBLE + _ARITH + """\
fun add3(x: Int): Int
    ret x + 3

fun add5(x: Int): Int
    ret x + 5

fun add7(x: Int): Int
    ret x + 7

fun main(): Int
    let a: Int = add3(10)
    let b: Int = add5(20)
    let c: Int = add7(30)
    ret a - b - c
"""
        # 13 - 25 - 37 = -49; as unsigned byte: 207
        self.assertEqual(207, _compile_and_run(src))

    def test_multiple_vars_live_across_calls(self):
        """Three variables each bound via a non-tail call; all three must
        remain valid when they are used together in the final expression.
        a=add3(4)=7, b=add5(2)=7, c=add7(1)=8; result = a - b + c = 8."""
        src = _PREAMBLE + _ARITH + """\
fun add3(x: Int): Int
    ret x + 3

fun add5(x: Int): Int
    ret x + 5

fun add7(x: Int): Int
    ret x + 7

fun main(): Int
    let a: Int = add3(4)
    let b: Int = add5(2)
    let c: Int = add7(1)
    ret a - b + c
"""
        # 7 - 7 + 8 = 8
        self.assertEqual(8, _compile_and_run(src))

    def test_four_sequential_calls(self):
        """Four non-tail calls exercise state-machine idx dispatch through four
        resume points (idx 0→1→2→3).  Values chosen so any dropped or
        re-ordered result gives a clearly different exit code.
        w=add3(10)=13, x=add5(20)=25, y=add3(30)=33, z=add5(40)=45.
        13 - 25 + 33 - 45 = -24 → 232 mod 256."""
        src = _PREAMBLE + _ARITH + """\
fun add3(x: Int): Int
    ret x + 3

fun add5(x: Int): Int
    ret x + 5

fun compute(a: Int, b: Int, cc: Int, d: Int): Int
    let w: Int = add3(a)
    let x: Int = add5(b)
    let y: Int = add3(cc)
    let z: Int = add5(d)
    ret w - x + y - z

fun main(): Int
    ret compute(10, 20, 30, 40)
"""
        self.assertEqual(232, _compile_and_run(src))


# ---------------------------------------------------------------------------
# Nested state machines — callee also has non-tail calls of its own
# ---------------------------------------------------------------------------

class TestNestedStateMachines(TestCase):

    def test_nested_two_level(self):
        """inner has its own non-tail call; main calls inner twice (both
        non-tail).  Exercises state-machine callback chaining across two levels.
        inner(5): add3(5)=8, 8+5=13.  inner(3): add3(3)=6, 6+5=11.  13+11=24."""
        src = _PREAMBLE + _ARITH + """\
fun add3(x: Int): Int
    ret x + 3

fun inner(x: Int): Int
    let a: Int = add3(x)
    ret a + 5

fun main(): Int
    let r1: Int = inner(5)
    let r2: Int = inner(3)
    ret r1 + r2
"""
        self.assertEqual(24, _compile_and_run(src))

    def test_nested_three_level(self):
        """Three levels of nesting: shallow → mid → main, each with its own
        non-tail call.  Exercises three independently generated state machines.
        shallow(1): add3(1)=4.  mid(1): shallow(1)+5=9.  main: mid(1)+7=16."""
        src = _PREAMBLE + _ARITH + """\
fun add3(x: Int): Int
    ret x + 3

fun add5(x: Int): Int
    ret x + 5

fun add7(x: Int): Int
    ret x + 7

fun shallow(x: Int): Int
    let a: Int = add3(x)
    ret a

fun mid(x: Int): Int
    let a: Int = shallow(x)
    ret a + 5

fun main(): Int
    let a: Int = mid(1)
    ret a + 7
"""
        self.assertEqual(16, _compile_and_run(src))

    def test_nested_callee_called_multiple_times(self):
        """inner has a state machine; outer calls it three times and combines
        results.  Tests that each call site correctly resumes after inner
        completes without corrupting earlier results.
        inner(2)=5, inner(3)=6, inner(4)=7; 5+6+7=18."""
        src = _PREAMBLE + _ARITH + """\
fun add3(x: Int): Int
    ret x + 3

fun inner(x: Int): Int
    let a: Int = add3(x)
    ret a

fun main(): Int
    let a: Int = inner(2)
    let b: Int = inner(3)
    let cc: Int = inner(4)
    ret a + b + cc
"""
        self.assertEqual(18, _compile_and_run(src))
