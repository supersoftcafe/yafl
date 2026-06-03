"""Operators resolve inside global `let` initialisers.

A global let's initialiser resolves like a function body, so trait/interface
methods — operators included — are in scope. This used to fail with "Failed to
resolve `==`" because trait-method resolution was wired into FunctionStatement
only; `__stmt_scope_resolver` now gives a top-level let the same trait scope.
Local lets (compiled via BlockExpression) keep the enclosing function's scope
and are exercised throughout the rest of the suite.
"""
from __future__ import annotations

import compiler as c
from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


class TestGlobalInitOperators(TestCase):
    def test_arithmetic_operators_and_global_ref(self):
        # `*` and `+` resolve, and one global may reference another.
        src = """\
import System

let X: System::Int = 3
let Y: System::Int = X * 2 + 1

fun main(): System::Int
  ret Y
"""
        rc, _ = compile_and_run_stdlib_capture(src)
        self.assertEqual(7, rc)

    def test_comparison_operator_in_global(self):
        # `>` resolves to System::Bool; branch on it in main.
        src = """\
import System

let POSITIVE: System::Bool = 5 > 0

fun main(): System::Int
  ret POSITIVE ? 1 : 0
"""
        rc, _ = compile_and_run_stdlib_capture(src)
        self.assertEqual(1, rc)
