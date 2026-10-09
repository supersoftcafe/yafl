"""Tests for union (CombinationSpec) types: type-checking, binary output, and negative cases.

Runtime behaviour is checked by compiler/yafl_tests/union_types.yafl.
"""
from __future__ import annotations

import contextlib
import io
import subprocess
from tests.testutil import TimedTestCase as TestCase

import compiler as c
from tests.testutil import _YAFLLIB_DIR
from tests.testutil import compile_c


_PREAMBLE = """\
namespace System
typealias Int : __builtin_type__<bigint>
typealias String : __builtin_type__<str>
typealias None : ()
let None:None = ()
"""


def _compile(source: str) -> str:
    return c.compile([c.Input(source, "test.yafl")], use_stdlib=False, just_testing=False)


def _compile_capturing_errors(source: str) -> tuple[str, str]:
    """Run compile() and capture stdout (which is where compile() prints errors).
    Returns (result, stdout_text)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        result = c.compile([c.Input(source, "test.yafl")], use_stdlib=False, just_testing=False)
    return result, buf.getvalue()


def _compile_and_clang_check(source: str) -> None:
    """Compile yafl source to C and verify clang accepts it (no link or run).
    Raises AssertionError if yafl compilation or clang syntax-check fails.
    """
    c_code = _compile(source)
    assert c_code, "yafl compilation produced no output (type errors?)"
    result = subprocess.run(
        ["clang", "-fsyntax-only", "-x", "c", "-", "-include", "yafl.h",
         "-I", str(_YAFLLIB_DIR)],
        input=c_code, text=True, capture_output=True, timeout=30,
    )
    assert result.returncode == 0, f"clang rejected the C output:\n{result.stderr}"


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


# ---------------------------------------------------------------------------
# Match expression: binary produces expected exit codes
# ---------------------------------------------------------------------------


class TestMatchMultiClassPointerUnion(TestCase):
    """Multi-class pointer unions use vtable-identity dispatch inside
    __gen_pointer_match. Covers the cases the tag-bit-only dispatch can't:
    two or more user class variants sharing the same heap-object space.

    The classes here have enough fields to avoid simple-class lowering
    (they stay as heap objects with distinct vtables)."""

    _PROLOGUE = _PREAMBLE + """\
class A(a1: Int, a2: Int, a3: Int, a4: Int, a5: Int)
class B(b1: Int, b2: Int, b3: Int, b4: Int, b5: Int)
class C(c1: Int, c2: Int, c3: Int, c4: Int, c5: Int)

"""


    def test_interface_arm_covers_all_implementors(self):
        """An arm whose type is an interface shared by the subject variants
        covers them all; a later arm for one of the implementors is
        flagged unreachable."""
        src = _PREAMBLE + """\
interface Shape
  fun side(): Int

class A(a1: Int, a2: Int, a3: Int, a4: Int, a5: Int) : Shape
  fun side(): Int
    ret a1

class B(b1: Int, b2: Int, b3: Int, b4: Int, b5: Int) : Shape
  fun side(): Int
    ret b1

fun classify(v: A|B|None): Int
  ret match(v)
    (s: Shape) => 1
    (a: A)     => 2
    (n: None)  => 9

fun main(): Int
  ret 0
"""
        result, errors = _compile_capturing_errors(src)
        self.assertEqual("", result)
        self.assertIn("unreachable", errors,
            f"expected 'unreachable' in errors, got: {errors!r}")

    def test_interface_arm_exhausts_implementor_variants(self):
        """Shape + None is exhaustive when the union contains only Shape-
        implementing classes plus None."""
        src = _PREAMBLE + """\
interface Shape
  fun side(): Int

class A(a1: Int, a2: Int, a3: Int, a4: Int, a5: Int) : Shape
  fun side(): Int
    ret a1

class B(b1: Int, b2: Int, b3: Int, b4: Int, b5: Int) : Shape
  fun side(): Int
    ret b1

fun classify(v: A|B|None): Int
  ret match(v)
    (s: Shape) => 1
    (n: None)  => 9

fun main(): Int
  ret 0
"""
        result, errors = _compile_capturing_errors(src)
        self.assertNotEqual("", result,
            f"expected successful compile, got errors: {errors!r}")


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


# ---------------------------------------------------------------------------
# Union nested in a tuple nested in a union, with nested match expressions
# ---------------------------------------------------------------------------

class TestNestedUnionInTupleBinary(TestCase):


    def test_non_exhaustive_errors(self):
        """match that omits a variant and has no else arm is a compile error."""
        src = _PREAMBLE_ADD + """\
fun f(x: String|None): Int
    ret match(x)
        (s: String) => 1

fun main(): Int
    ret f(\"hi\")
"""
        result, errors = _compile_capturing_errors(src)
        self.assertEqual("", result)
        self.assertIn("non-exhaustive", errors,
            f"expected 'non-exhaustive' in errors, got: {errors!r}")

    def test_unreachable_after_else_errors(self):
        """An arm that comes after an else arm is flagged unreachable."""
        src = _PREAMBLE_ADD + """\
fun f(x: String|None): Int
    ret match(x)
        () => 3
        (s: String) => 1

fun main(): Int
    ret f(\"hi\")
"""
        result, errors = _compile_capturing_errors(src)
        self.assertEqual("", result)
        self.assertIn("unreachable", errors,
            f"expected 'unreachable' in errors, got: {errors!r}")
        self.assertIn("follows an else", errors,
            f"expected specific unreachable reason, got: {errors!r}")

    def test_duplicate_variant_arm_errors(self):
        """Covering the same variant twice is flagged unreachable."""
        src = _PREAMBLE_ADD + """\
fun f(x: String|None): Int
    ret match(x)
        (s: String) => 1
        (s: String) => 2
        (n: None)   => 0

fun main(): Int
    ret f(\"hi\")
"""
        result, errors = _compile_capturing_errors(src)
        self.assertEqual("", result)
        self.assertIn("unreachable", errors,
            f"expected 'unreachable' in errors, got: {errors!r}")


    def test_ret_assignment_mismatch(self):
        src = _PREAMBLE + """\
fun returnsUnion():Int|None
  ret None
fun main():Int
  ret returnsUnion()
"""
        code = _compile(src)
        self.assertEqual("", code)

    def test_let_assignment_mismatch(self):
        src = _PREAMBLE + """\
fun returnsUnion():Int|None
  ret None
fun main():Int
  let x: Int = returnsUnion()
  ret x
"""
        code = _compile(src)
        self.assertEqual("", code)

    def test_let_assignment_match(self):
        src = """\
import System
fun returnsUnion():System::Int|System::None
  ret System::None
fun main():System::Int
  ret match(returnsUnion())
    (x: System::Int) => x
    () => -1
"""
        code = compile_c(src)
        self.assertNotEqual("", code)


# ---------------------------------------------------------------------------
# Literal patterns in match arms (Int and String)
# ---------------------------------------------------------------------------

class TestMatchLiteralPatterns(TestCase):

    _PROLOGUE = _PREAMBLE + """\
fun `+`(l: Int, r: Int): Int
    ret __builtin_op__<bigint>("integer_add", l, r)

"""


    def test_missing_else_is_non_exhaustive_error(self):
        """A literal-pattern match with no else arm is a compile error."""
        src = self._PROLOGUE + """\
fun classify(x: Int): Int
    ret match(x)
        (0) => 10
        (1) => 20

fun main(): Int
    ret classify(0)
"""
        result, errors = _compile_capturing_errors(src)
        self.assertEqual("", result)
        self.assertIn("non-exhaustive", errors,
            f"expected 'non-exhaustive' in errors, got: {errors!r}")
        self.assertIn("else arm", errors,
            f"expected 'else arm' hint, got: {errors!r}")

    def test_duplicate_literal_is_unreachable_error(self):
        """Two arms with the same literal value fail to compile."""
        src = self._PROLOGUE + """\
fun classify(x: Int): Int
    ret match(x)
        (0) => 10
        (0) => 20
        (x) => 9

fun main(): Int
    ret classify(0)
"""
        result, errors = _compile_capturing_errors(src)
        self.assertEqual("", result)
        self.assertIn("unreachable", errors,
            f"expected 'unreachable' in errors, got: {errors!r}")
        self.assertIn("literal value already matched", errors,
            f"expected specific reason, got: {errors!r}")


    def test_literal_arm_on_union_without_primitive_variant_rejected(self):
        """Literal arms require at least one primitive variant in the subject."""
        src = self._PROLOGUE + """\
fun f(x: Int32|None): Int
    ret match(x)
        ("hi") => 1
        ()     => 0

fun main(): Int
    ret f(None)
"""
        result, errors = _compile_capturing_errors(src)
        self.assertEqual("", result)
        self.assertIn("primitive", errors,
            f"expected 'primitive' hint, got: {errors!r}")