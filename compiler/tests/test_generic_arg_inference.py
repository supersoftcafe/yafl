from tests.testutil import TimedTestCase as TestCase

import compiler as c


# These tests pin down the real, currently-failing inference gap uncovered
# while planning strong type inference (project_strong_type_inference).
#
# The original "generic result into an overloaded callee" gap described in
# that memory is already closed by the iterate-to-convergence compile loop
# plus the top-down argument-type threading in CallExpression.compile.  The
# friction that remains is narrower and more fundamental: an unsuffixed
# integer literal is rigidly `bigint`, so it cannot flow into a narrower
# integer slot (e.g. an `Int32` parameter) without an explicit `i32` suffix
# — a type annotation the user should not have to write when the context
# already fixes the type.  This also voids generic inference: a width
# mismatch in one argument position makes `unify_generic` discard the
# placeholder binding from the others.
#
# Written to FAIL today and to pass once integer literals are context-typed
# from their expected type.

_INT32 = ("import System\n"
          "\n"
          "fun takesI32(i: System::Int32): System::Int\n"
          "    ret 0\n"
          "\n")


class Test(TestCase):
    def test_suffixed_literal_baseline(self):
        # Control: the explicit-suffix idiom works today.  Guards the harness.
        content = (_INT32 +
                   "fun main(): System::Int\n"
                   "    ret takesI32(0i32)\n")
        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=True, just_testing=False)
        self.assertNotEqual("", result)

    def test_bare_literal_into_int32_param(self):
        # RULED (2026-07-04): no conversion — a bare `0` is Int and does NOT
        # take Int32 from the parameter. Spell it 0i32.
        content = (_INT32 +
                   "fun main(): System::Int\n"
                   "    ret takesI32(0)\n")
        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=True, just_testing=False)
        self.assertEqual("", result or "")
        content = (_INT32 +
                   "fun main(): System::Int\n"
                   "    ret takesI32(0i32)\n")
        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=True, just_testing=False)
        self.assertNotEqual("", result)

    def test_generic_inference_with_suffixed_width(self):
        # RULED (2026-07-04): `second(0, 99)` is an error — a bare 0 is Int,
        # not Int32. Spelled 0i32, T infers from the second argument.
        content = ("import System\n"
                   "\n"
                   "fun second<T>(i: System::Int32, x: T): T\n"
                   "    ret x\n"
                   "\n"
                   "fun main(): System::Int\n"
                   "    ret second(0i32, 99)\n")
        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=True, just_testing=False)
        self.assertNotEqual("", result)

    def test_array_index_with_bare_literal(self):
        # `a[0]` works because the index API takes Int — 0 IS an Int under
        # strict literals (array.yafl converts internally; the Int32 overload
        # remains for byte-scanning code holding a sized index).
        content = ("import System\n"
                   "\n"
                   "fun get0(a: System::Array<System::Int>): System::Int\n"
                   "    ret a[0]\n"
                   "\n"
                   "fun main(): System::Int\n"
                   "    ret 0\n")
        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=True, just_testing=False)
        self.assertNotEqual("", result)

    # ── Float literals: same context-typing, symmetric with integers ──────

    def test_suffixed_float_baseline(self):
        # Control: the explicit `f32` suffix works today.
        content = ("import System\n"
                   "\n"
                   "fun takesF32(x: System::Float32): System::Int\n"
                   "    ret 0\n"
                   "\n"
                   "fun main(): System::Int\n"
                   "    ret takesF32(1.5f32)\n")
        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=True, just_testing=False)
        self.assertNotEqual("", result)

    def test_bare_float_into_float32_param(self):
        # RULED (2026-07-04): 1.5 is Float64 and does not become Float32;
        # 1.5f32 is. Type what you mean.
        content = ("import System\n"
                   "\n"
                   "fun takesF32(x: System::Float32): System::Int\n"
                   "    ret 0\n"
                   "\n"
                   "fun main(): System::Int\n"
                   "    ret takesF32(1.5)\n")
        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=True, just_testing=False)
        self.assertEqual("", result or "")
        content = content.replace("takesF32(1.5)", "takesF32(1.5f32)")
        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=True, just_testing=False)
        self.assertNotEqual("", result)
