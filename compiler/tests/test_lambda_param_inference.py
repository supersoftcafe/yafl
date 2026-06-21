from tests.testutil import TimedTestCase as TestCase

import compiler as c


# A lambda already receives its expected *return* type from the enclosing call
# site, but its *parameters* are compiled with no expected type — so an untyped
# lambda parameter never acquires a type and codegen fails ("missing type").
# These tests require lambda parameter types to be inferred from the expected
# callable type, removing the need to write `(n: Int) =>`.
#
# Written to FAIL today; pass once LambdaExpression.compile threads the
# expected callable's parameter types into its parameter destructure.


class Test(TestCase):
    def test_typed_lambda_param_baseline(self):
        # Control: an explicitly-typed lambda parameter works today.
        content = ("import System\n"
                   "\n"
                   "fun apply(f: (:System::Int):System::Int, x: System::Int): System::Int\n"
                   "    ret f(x)\n"
                   "\n"
                   "fun main(): System::Int\n"
                   "    ret apply((n: System::Int) => n, 5)\n")
        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=True, just_testing=False)
        self.assertNotEqual("", result)

    def test_untyped_lambda_param_from_callee(self):
        # `n` must take Int from the parameter's declared callable type.
        content = ("import System\n"
                   "\n"
                   "fun apply(f: (:System::Int):System::Int, x: System::Int): System::Int\n"
                   "    ret f(x)\n"
                   "\n"
                   "fun main(): System::Int\n"
                   "    ret apply((n) => n, 5)\n")
        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=True, just_testing=False)
        self.assertNotEqual("", result)

    def test_untyped_lambda_param_in_generic_map(self):
        # The everyday case: `map(l, (x) => x + 1)`. With map<Int,Int> fixed,
        # the expected callable is `(Int): Int`, so `x` must infer as Int.
        content = ("import System\n"
                   "\n"
                   "fun main(): System::Int\n"
                   "    let l = prepend<System::Int>(1, List<System::Int>())\n"
                   "    let m = map<System::Int, System::Int>(l, (x) => x + 1)\n"
                   "    ret 0\n")
        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=True, just_testing=False)
        self.assertNotEqual("", result)

    def test_untyped_multi_param_lambda_in_fold(self):
        # Two untyped params: `fold(l, 0, (acc, x) => acc + x)`. Both `acc`
        # and `x` are inferred from the expected `(Int, Int): Int` callable.
        content = ("import System\n"
                   "\n"
                   "fun main(): System::Int\n"
                   "    let l = prepend<System::Int>(1, List<System::Int>())\n"
                   "    let s = fold<System::Int, System::Int>(l, 0, (acc, x) => acc + x)\n"
                   "    ret s\n")
        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=True, just_testing=False)
        self.assertNotEqual("", result)
