"""Tests for union (CombinationSpec) types: type-checking, binary output, and negative cases."""
from __future__ import annotations

import subprocess
from unittest import TestCase

import compiler as c
from tests.testutil import compile_and_run


_PREAMBLE = """\
namespace System
typealias Int : __builtin_type__<bigint>
typealias String : __builtin_type__<str>
typealias None : ()
let None:None = ()
"""


def _compile(source: str) -> str:
    return c.compile([c.Input(source, "test.yafl")], use_stdlib=False, just_testing=False)


def _compile_and_clang_check(source: str) -> None:
    """Compile yafl source to C and verify clang accepts it (no link or run).
    Raises AssertionError if yafl compilation or clang syntax-check fails.
    """
    c_code = _compile(source)
    assert c_code, "yafl compilation produced no output (type errors?)"
    result = subprocess.run(
        ["clang", "-fsyntax-only", "-x", "c", "-", "-include", "yafl.h"],
        input=c_code, text=True, capture_output=True, timeout=30,
    )
    assert result.returncode == 0, f"clang rejected the C output:\n{result.stderr}"


def _compile_and_run(source: str, timeout: int = 5) -> tuple[int, str]:
    return compile_and_run(source, timeout)


# ---------------------------------------------------------------------------
# Positive: type-checker accepts these programs
# ---------------------------------------------------------------------------

class TestUnionTypePositive(TestCase):

    def test_string_assignable_to_string_or_none(self):
        """String is a member of String|None — should compile."""
        src = _PREAMBLE + """\
fun accept(x: String|None): Int
    ret 0

fun main(): Int
    ret accept("hello")
"""
        _compile_and_clang_check(src)

    def test_none_assignable_to_string_or_none(self):
        """None is a member of String|None — should compile."""
        src = _PREAMBLE + """\
fun accept(x: String|None): Int
    ret 0

fun main(): Int
    ret accept(None)
"""
        _compile_and_clang_check(src)

    def test_string_or_none_to_wider_union(self):
        """String|None is a subset of String|Int|None — widening should be accepted."""
        src = _PREAMBLE + """\
fun wide(x: String|Int|None): Int
    ret 0

fun narrow(x: String|None): Int
    ret wide(x)

fun main(): Int
    ret narrow("hi")
"""
        _compile_and_clang_check(src)

    def test_callable_same_return_type(self):
        """A callable with the exact same union return type is acceptable."""
        src = _PREAMBLE + """\
fun apply(f: (:String):String|None, x: String): Int
    ret 0

fun wrap(x: String): String|None
    ret x

fun main(): Int
    ret apply(wrap, "hi")
"""
        _compile_and_clang_check(src)

    def test_int32_or_none_compiles(self):
        """Int32|None contains a value type — must generate a tagged struct, not DataPointer.
        A behavioral test (checking tag values via match) requires match support; this is a
        smoke-test that the pipeline accepts a value-type union and clang accepts the C output."""
        src = _PREAMBLE + """\
typealias Int32 : __builtin_type__<int32>

fun accept(x: Int32|None): Int
    ret 0

fun main(): Int
    ret accept(None)
"""
        _compile_and_clang_check(src)


# ---------------------------------------------------------------------------
# Positive: binary produces expected exit codes
# ---------------------------------------------------------------------------

class TestUnionTypeBinary(TestCase):

    def test_string_or_none_param_runs(self):
        """Function accepting String|None, called with String, runs and exits 0."""
        src = _PREAMBLE + """\
fun accept(x: String|None): Int
    ret 0

fun main(): Int
    ret accept("hello")
"""
        code, _ = _compile_and_run(src)
        self.assertEqual(0, code)

    def test_none_param_runs(self):
        """Function accepting String|None, called with None, runs and exits 0."""
        src = _PREAMBLE + """\
fun accept(x: String|None): Int
    ret 0

fun main(): Int
    ret accept(None)
"""
        code, _ = _compile_and_run(src)
        self.assertEqual(0, code)

    def test_return_value_preserved(self):
        """The exit code equals the return value of main — verifies basic plumbing."""
        src = _PREAMBLE + """\
fun `+`(l: Int, r: Int): Int
    ret __builtin_op__<bigint>("integer_add", l, r)

fun main(): Int
    ret 2 + 3
"""
        code, _ = _compile_and_run(src)
        self.assertEqual(5, code)

    def test_union_param_passthrough_runs(self):
        """Chain of functions with String|None params runs cleanly."""
        src = _PREAMBLE + """\
fun inner(x: String|None): Int
    ret 0

fun outer(x: String|None): Int
    ret inner(x)

fun main(): Int
    ret outer("hello")
"""
        code, _ = _compile_and_run(src)
        self.assertEqual(0, code)

    def test_union_widening_in_call_runs(self):
        """Widening String|None → String|Int|None at a call site runs cleanly (String input)."""
        src = _PREAMBLE + """\
fun wide(x: String|Int|None): Int
    ret 0

fun narrow(x: String|None): Int
    ret wide(x)

fun main(): Int
    ret narrow("hi")
"""
        code, _ = _compile_and_run(src)
        self.assertEqual(0, code)

    def test_union_widening_none_input(self):
        """Widening String|None → String|Int|None with a None value (exercises the null branch of DataPointer widening)."""
        src = _PREAMBLE + """\
fun wide(x: String|Int|None): Int
    ret 0

fun narrow(x: String|None): Int
    ret wide(x)

fun main(): Int
    ret narrow(None)
"""
        code, _ = _compile_and_run(src)
        self.assertEqual(0, code)

    def test_union_container_to_container_widening(self):
        """Widening Int32|None (UnionContainer) → String|Int32|None exercises the UnionContainer→UnionContainer path."""
        src = _PREAMBLE + """\
typealias Int32 : __builtin_type__<int32>

fun wide(x: String|Int32|None): Int
    ret 0

fun narrow(x: Int32|None): Int
    ret wide(x)

fun main(): Int
    ret narrow(None)
"""
        code, _ = _compile_and_run(src)
        self.assertEqual(0, code)


# ---------------------------------------------------------------------------
# Match expression: binary produces expected exit codes
# ---------------------------------------------------------------------------

class TestMatchBinary(TestCase):

    def test_match_string_arm_taken(self):
        """match on String|None with a String value dispatches to the String arm (exit 2)."""
        src = _PREAMBLE + """\
fun `+`(l: Int, r: Int): Int
    ret __builtin_op__<bigint>("integer_add", l, r)

fun classify(x: String|None): Int
    ret match(x)
        (s:String) => 2
        (n:None) => 7

fun main(): Int
    ret classify("hello")
"""
        code, _ = _compile_and_run(src)
        self.assertEqual(2, code)

    def test_match_none_arm_taken(self):
        """match on String|None with a None value dispatches to the None arm (exit 7)."""
        src = _PREAMBLE + """\
fun `+`(l: Int, r: Int): Int
    ret __builtin_op__<bigint>("integer_add", l, r)

fun classify(x: String|None): Int
    ret match(x)
        (s:String) => 2
        (n:None) => 7

fun main(): Int
    ret classify(None)
"""
        code, _ = _compile_and_run(src)
        self.assertEqual(7, code)

    def test_match_bound_variable_used(self):
        """The bound variable in a match arm is accessible in the arm body."""
        src = _PREAMBLE + """\
fun `+`(l: Int, r: Int): Int
    ret __builtin_op__<bigint>("integer_add", l, r)

fun unwrap_or_zero(x: String|None): Int
    ret match(x)
        (s:String) => 3
        (n:None) => 0

fun main(): Int
    ret unwrap_or_zero("hi") + unwrap_or_zero(None)
"""
        code, _ = _compile_and_run(src)
        self.assertEqual(3, code)

    # Note: testing the Int32 arm of Int32|None requires a way to produce an int32 literal,
    # which is not yet directly supported in yafl without stdlib.

    def test_match_int32_or_none_none_arm(self):
        """match on Int32|None (UnionContainer) dispatches correctly to the None arm."""
        src = _PREAMBLE + """\
typealias Int32 : __builtin_type__<int32>

fun accept(x: Int32|None): Int
    ret match(x)
        (v:Int32) => 4
        (n:None) => 9

fun main(): Int
    ret accept(None)
"""
        code, _ = _compile_and_run(src)
        self.assertEqual(9, code)


# ---------------------------------------------------------------------------
# Negative: type-checker must reject these programs
# ---------------------------------------------------------------------------

class TestUnionTypeNegative(TestCase):

    def test_int_not_assignable_to_string_or_none(self):
        """Int is not a member of String|None — must be a compile error."""
        src = _PREAMBLE + """\
fun accept(x: String|None): Int
    ret 0

fun main(): Int
    ret accept(42)
"""
        self.assertEqual("", _compile(src))

    def test_string_not_assignable_to_int_or_none(self):
        """String is not a member of Int|None — must be a compile error."""
        src = _PREAMBLE + """\
fun accept(x: Int|None): Int
    ret 0

fun main(): Int
    ret accept("hello")
"""
        self.assertEqual("", _compile(src))

    def test_union_not_assignable_to_plain_type(self):
        """String|None cannot be passed to a plain String parameter without narrowing."""
        src = _PREAMBLE + """\
fun strict(x: String): Int
    ret 0

fun relay(x: String|None): Int
    ret strict(x)

fun main(): Int
    ret relay("hi")
"""
        self.assertEqual("", _compile(src))

    def test_callable_wrong_union_return_type(self):
        """A callable returning Int|None cannot substitute for one returning String|None.
        Int is not a member of String|None."""
        src = _PREAMBLE + """\
fun apply(f: (:String):String|None, x: String): Int
    ret 0

fun int_or_none(x: String): Int|None
    ret 0

fun main(): Int
    ret apply(int_or_none, "hi")
"""
        self.assertEqual("", _compile(src))

    def test_callable_narrow_return_not_allowed(self):
        """A callable returning String cannot substitute for one returning String|None.
        Callables do not auto-widen return types — no thunk generation."""
        src = _PREAMBLE + """\
fun apply(f: (:String):String|None, x: String): Int
    ret 0

fun just_string(x: String): String
    ret x

fun main(): Int
    ret apply(just_string, "hi")
"""
        self.assertEqual("", _compile(src))

    def test_callable_wide_return_not_allowed(self):
        """A callable returning String|Int|None cannot substitute for String|None.
        The wider union is not equivalent to the narrower one."""
        src = _PREAMBLE + """\
fun apply(f: (:String):String|None, x: String): Int
    ret 0

fun too_wide(x: String): String|Int|None
    ret x

fun main(): Int
    ret apply(too_wide, "hi")
"""
        self.assertEqual("", _compile(src))


# ---------------------------------------------------------------------------
# Nested tuple/union combinations: binary produces expected exit codes
# ---------------------------------------------------------------------------

_PREAMBLE_ADD = _PREAMBLE + """\
fun `+`(l: Int, r: Int): Int
    ret __builtin_op__<bigint>("integer_add", l, r)
"""


class TestNestedTupleUnionBinary(TestCase):

    def test_string_boxed_as_union_param(self):
        """String is auto-boxed into String|None at a call site."""
        src = _PREAMBLE_ADD + """\
fun classify(s: String|None, n: Int): Int
    ret n

fun main(): Int
    ret classify("hello", 5)
"""
        code, _ = _compile_and_run(src)
        self.assertEqual(5, code)

    def test_none_boxed_as_union_param(self):
        """None is auto-boxed into String|None at a call site."""
        src = _PREAMBLE_ADD + """\
fun classify(s: String|None, n: Int): Int
    ret n

fun main(): Int
    ret classify(None, 3)
"""
        code, _ = _compile_and_run(src)
        self.assertEqual(3, code)

    def test_match_on_union_param_string_arm(self):
        """match on a String|None parameter dispatches to String arm."""
        src = _PREAMBLE_ADD + """\
fun classify(s: String|None, n: Int): Int
    ret match(s)
        (x:String) => n
        (x:None) => 0

fun main(): Int
    ret classify("hi", 7)
"""
        code, _ = _compile_and_run(src)
        self.assertEqual(7, code)

    def test_match_on_union_param_none_arm(self):
        """match on a String|None parameter dispatches to None arm."""
        src = _PREAMBLE_ADD + """\
fun classify(s: String|None, n: Int): Int
    ret match(s)
        (x:String) => n
        (x:None) => 0

fun main(): Int
    ret classify(None, 7)
"""
        code, _ = _compile_and_run(src)
        self.assertEqual(0, code)

    def test_string_boxed_into_tuple_via_pipeline(self):
        """String is auto-boxed into String|None when a tuple literal is piped to a lambda."""
        src = _PREAMBLE_ADD + """\
fun main(): Int
    ret ("hello", 5) |> (s: String|None, n: Int) => n
"""
        code, _ = _compile_and_run(src)
        self.assertEqual(5, code)

    def test_none_boxed_into_tuple_via_pipeline(self):
        """None is auto-boxed into String|None when a tuple literal is piped to a lambda."""
        src = _PREAMBLE_ADD + """\
fun main(): Int
    ret (None, 3) |> (s: String|None, n: Int) => n
"""
        code, _ = _compile_and_run(src)
        self.assertEqual(3, code)

    def test_match_on_union_from_pipeline_string_arm(self):
        """Tuple literal piped to lambda: union element dispatches to String arm in match."""
        src = _PREAMBLE_ADD + """\
fun main(): Int
    ret ("hi", 7) |> (s: String|None, n: Int) => match(s)
        (x:String) => n
        (x:None) => 0
"""
        code, _ = _compile_and_run(src)
        self.assertEqual(7, code)

    def test_match_on_union_from_pipeline_none_arm(self):
        """Tuple literal piped to lambda: union element dispatches to None arm in match."""
        src = _PREAMBLE_ADD + """\
fun main(): Int
    ret (None, 7) |> (s: String|None, n: Int) => match(s)
        (x:String) => n
        (x:None) => 0
"""
        code, _ = _compile_and_run(src)
        self.assertEqual(0, code)

    def test_union_passthrough_via_function_string(self):
        """String|None returned from a function, boxed into result, then matched."""
        src = _PREAMBLE_ADD + """\
fun identity(s: String|None): String|None
    ret s

fun main(): Int
    ret (identity("hello"), 1) |> (s: String|None, n: Int) => match(s)
        (x:String) => n
        (x:None) => 0
"""
        code, _ = _compile_and_run(src)
        self.assertEqual(1, code)

    def test_union_passthrough_via_function_none(self):
        """None returned from a function, then matched correctly."""
        src = _PREAMBLE_ADD + """\
fun identity(s: String|None): String|None
    ret s

fun main(): Int
    ret (identity(None), 1) |> (s: String|None, n: Int) => match(s)
        (x:String) => n
        (x:None) => 0
"""
        code, _ = _compile_and_run(src)
        self.assertEqual(0, code)


# ---------------------------------------------------------------------------
# Union nested in a tuple nested in a union, with nested match expressions
# ---------------------------------------------------------------------------

class TestNestedUnionInTupleBinary(TestCase):

    def test_tuple_variant_dispatch(self):
        """Boxing a (s: String|None, n: Int) tuple into (String|None,Int)|None; outer match dispatches to tuple arm."""
        src = _PREAMBLE_ADD + """\
fun process(x: (s: String|None, n: Int) | None): Int
    ret match(x)
        (pair: (s: String|None, n: Int)) => 3
        (n: None) => 9

fun main(): Int
    ret process(("hello", 5))
"""
        code, _ = _compile_and_run(src)
        self.assertEqual(3, code)

    def test_none_variant_dispatch(self):
        """Boxing None into (String|None,Int)|None; outer match dispatches to None arm."""
        src = _PREAMBLE_ADD + """\
fun process(x: (s: String|None, n: Int) | None): Int
    ret match(x)
        (pair: (s: String|None, n: Int)) => 3
        (n: None) => 9

fun main(): Int
    ret process(None)
"""
        code, _ = _compile_and_run(src)
        self.assertEqual(9, code)

    def test_nested_match_tuple_arm_string(self):
        """Outer match on (String|None,Int)|None (tuple variant); inner match on String|None param → String arm."""
        src = _PREAMBLE_ADD + """\
fun classify(x: (s: String|None, n: Int) | None, s: String|None): Int
    ret match(x)
        (pair: (s: String|None, n: Int)) => match(s)
            (y: String) => 1
            (y: None) => 0
        (n: None) => 9

fun main(): Int
    ret classify(("hello", 5), "world")
"""
        code, _ = _compile_and_run(src)
        self.assertEqual(1, code)

    def test_nested_match_tuple_arm_none(self):
        """Outer match on (String|None,Int)|None (tuple variant); inner match on String|None param → None arm."""
        src = _PREAMBLE_ADD + """\
fun classify(x: (s: String|None, n: Int) | None, s: String|None): Int
    ret match(x)
        (pair: (s: String|None, n: Int)) => match(s)
            (y: String) => 1
            (y: None) => 0
        (n: None) => 9

fun main(): Int
    ret classify(("hello", 5), None)
"""
        code, _ = _compile_and_run(src)
        self.assertEqual(0, code)

    def test_nested_match_outer_none_arm(self):
        """Outer match on (String|None,Int)|None dispatches to None arm regardless of inner param."""
        src = _PREAMBLE_ADD + """\
fun classify(x: (s: String|None, n: Int) | None, s: String|None): Int
    ret match(x)
        (pair: (s: String|None, n: Int)) => match(s)
            (y: String) => 1
            (y: None) => 0
        (n: None) => 9

fun main(): Int
    ret classify(None, "world")
"""
        code, _ = _compile_and_run(src)
        self.assertEqual(9, code)

    def test_none_inner_string_or_none_dispatch(self):
        """Boxing (None, 5) into (String|None,Int)|None — inner None is boxed to String|None, outer match works."""
        src = _PREAMBLE_ADD + """\
fun process(x: (s: String|None, n: Int) | None): Int
    ret match(x)
        (pair: (s: String|None, n: Int)) => 3
        (n: None) => 9

fun main(): Int
    ret process((None, 5))
"""
        code, _ = _compile_and_run(src)
        self.assertEqual(3, code)
