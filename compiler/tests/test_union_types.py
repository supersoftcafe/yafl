"""Tests for union (CombinationSpec) types: type-checking, binary output, and negative cases."""
from __future__ import annotations

import os
import subprocess
import tempfile
from unittest import TestCase, expectedFailure

import compiler as c


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
    """Compile yafl source to a binary, run it, return (exit_code, clang_stderr).
    Raises AssertionError if compilation to C fails or clang rejects the output.
    """
    c_code = _compile(source)
    assert c_code, "yafl compilation produced no output (type errors?)"

    with tempfile.NamedTemporaryFile(suffix="", delete=False) as tmp:
        binary = tmp.name

    try:
        result = subprocess.run(
            ["clang", "-g", "-x", "c", "-", "-O0", "-l", "yafl", "-o", binary],
            input=c_code, text=True, capture_output=True, timeout=30,
        )
        assert result.returncode == 0, f"clang failed:\n{result.stderr}"

        run = subprocess.run([binary], capture_output=True, timeout=timeout)
        return run.returncode, ""
    finally:
        try:
            os.unlink(binary)
        except OSError:
            pass


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

    @expectedFailure  # union boxing for non-pointer values (None/unit) not yet implemented
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
        """Widening String|None → String|Int|None at a call site runs cleanly."""
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
