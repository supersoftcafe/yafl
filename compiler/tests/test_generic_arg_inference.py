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
        # A bare `0` should take Int32 from the parameter's expected type.
        content = (_INT32 +
                   "fun main(): System::Int\n"
                   "    ret takesI32(0)\n")
        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=True, just_testing=False)
        self.assertNotEqual("", result)

    def test_generic_inference_not_voided_by_width(self):
        # `second(0, 99)`: T must infer from the second argument (Int) even
        # though the first argument's literal meets an Int32 parameter.  Today
        # the width mismatch makes unify_generic drop the T binding.
        content = ("import System\n"
                   "\n"
                   "fun second<T>(i: System::Int32, x: T): T\n"
                   "    ret x\n"
                   "\n"
                   "fun main(): System::Int\n"
                   "    ret second(0, 99)\n")
        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=True, just_testing=False)
        self.assertNotEqual("", result)

    def test_array_index_with_bare_literal(self):
        # The motivating real-world case: index an array with a plain literal.
        # `a[0]` lowers to `[]`(a, 0); the index param is Int32.
        content = ("import System\n"
                   "\n"
                   "fun get0(a: System::Array<System::Int>): System::Int\n"
                   "    ret a[0]\n"
                   "\n"
                   "fun main(): System::Int\n"
                   "    ret 0\n")
        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=True, just_testing=False)
        self.assertNotEqual("", result)
