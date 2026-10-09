"""Function-typed global `let`s (the item-4 bug). A global whose value is a
`fun_t` reaches the lazy-init machinery unless it is a direct lambda (which
lowering/lambda_globals.py turns into a plain `fun`). Two root fixes make the
lazy path correct for callable values:

  - lazy_thunks handles a FuncPointer value type (mangle + StructField on the
    fun_t's `.o` word, which the task ABI tags);
  - lower_lazy_lets wraps EVERY deferred-init RHS in a nullary thunk,
    uniformly — it no longer special-cases a lambda value. The old
    lambda-skip used a value-lambda directly as the init closure (called with
    no arguments → garbage fun_t → the caller's segfault) and would even have
    called a nullary lambda and memoised its result instead of the function.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture

_LEN = "fun impl(s: System::String): System::Int\n  ret System::length(s)\n"


class TestFunctionTypedGlobals(TestCase):
    def test_alias_of_named_function(self):
        rc, _ = compile_and_run_stdlib_capture(
            "namespace Main\nimport System\n" + _LEN +
            "let h: (:System::String): System::Int = impl\n"
            "fun main(): System::Int\n  ret h(\"abc\") + h(\"de\")\n")
        self.assertEqual(5, rc)

    def test_ternary_of_functions(self):
        rc, _ = compile_and_run_stdlib_capture(
            "namespace Main\nimport System\n"
            "fun f1(s: System::String): System::Int\n  ret System::length(s)\n"
            "fun f2(s: System::String): System::Int\n  ret System::length(s) * 2\n"
            "let h: (:System::String): System::Int = true ? f1 : f2\n"
            "fun main(): System::Int\n  ret h(\"abc\")\n")
        self.assertEqual(3, rc)

    def test_ternary_of_lambdas_at_o0_and_o3(self):
        # Not a direct lambda (lambda_globals skips it) → lazy path. At -O3
        # known_tags folds the constant `true ?` to an unconditional jump; the
        # dropped arm's lambda must be stripped (known_tags strip_unused after
        # folding) so it isn't emitted unused — else clang -Wunused-function.
        src = ("namespace Main\nimport System\n"
               "let h: (:System::String): System::Int = "
               "true ? (s: System::String) => System::length(s) "
               ": (s: System::String) => 0\n"
               "fun main(): System::Int\n  ret h(\"abcd\")\n")
        for level in (0, 3):
            rc, _ = compile_and_run_stdlib_capture(src, optimization_level=level)
            self.assertEqual(4, rc, f"failed at -O{level}")

    def test_nullary_function_value_is_stored_not_called(self):
        # The case the old special-case broke both ways: a nullary function
        # value must be MEMOISED (g is the function), not called at force.
        rc, _ = compile_and_run_stdlib_capture(
            "namespace Main\nimport System\n"
            "let g: (): System::Int = () => 5\n"
            "fun main(): System::Int\n  ret g() + g()\n")
        self.assertEqual(10, rc)
