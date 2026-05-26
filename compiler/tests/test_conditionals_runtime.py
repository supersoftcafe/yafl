"""Consolidated if/else runtime test.

Each if-shape lives in its own helper function. main() runs them all
and prints labelled integer results. Compile-time error checks remain
in test_conditionals.TestIfCompileErrors (they can't share a compile
with anything else since they test compilation failures).
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


_SRC = """\
import System

fun emit(label: System::String, value: System::Int): System::None
  print(label + "=" + String(value) + "\\n")
  ret None

# ─── TestIfRuntime ──────────────────────────────────────────────────────

fun guard_taken(): System::Int
  if 0 < 1
    ret 5
  ret 7

fun guard_not_taken(): System::Int
  if 0 > 1
    ret 5
  ret 7

fun multi_statement_body(): System::Int
  let a: System::Int = 5
  if a < 10
    let b: System::Int = a + 1
    ret b
  ret 99

fun max(a: System::Int, b: System::Int): System::Int
  if a < b
    ret b
  ret a

fun early_return_inlined(): System::Int
  ret max(7, 3) + max(2, 10)

# ─── TestIfElseRuntime ──────────────────────────────────────────────────

fun if_else_true(): System::Int
  if 1 < 2
    ret 10
  else
    ret 20
  ret 99

fun if_else_false(): System::Int
  if 1 > 2
    ret 10
  else
    ret 20
  ret 99

fun chain_first(): System::Int
  if 1 < 2
    ret 10
  else if 3 < 4
    ret 20
  else
    ret 30
  ret 99

fun chain_else_if(): System::Int
  if 1 > 2
    ret 10
  else if 3 < 4
    ret 20
  else
    ret 30
  ret 99

fun chain_else(): System::Int
  if 1 > 2
    ret 10
  else if 3 > 4
    ret 20
  else
    ret 30
  ret 99

fun chain_no_else_falls_through(): System::Int
  if 1 > 2
    ret 10
  else if 3 > 4
    ret 20
  ret 99

fun nested_if_else(): System::Int
  if 1 < 2
    if 5 > 100
      ret 1
    else
      ret 42
  else
    ret 99
  ret 0

fun main(): System::Int
  emit("guard_taken",                  guard_taken())
  emit("guard_not_taken",              guard_not_taken())
  emit("multi_statement_body",         multi_statement_body())
  emit("early_return_inlined",         early_return_inlined())
  emit("if_else_true",                 if_else_true())
  emit("if_else_false",                if_else_false())
  emit("chain_first",                  chain_first())
  emit("chain_else_if",                chain_else_if())
  emit("chain_else",                   chain_else())
  emit("chain_no_else_falls_through",  chain_no_else_falls_through())
  emit("nested_if_else",               nested_if_else())
  ret 0
"""


_EXPECTED_LINES = [
    "guard_taken=5",
    "guard_not_taken=7",
    "multi_statement_body=6",
    "early_return_inlined=17",
    "if_else_true=10",
    "if_else_false=20",
    "chain_first=10",
    "chain_else_if=20",
    "chain_else=30",
    "chain_no_else_falls_through=99",
    "nested_if_else=42",
]


class TestAllConditionalsRuntime(TestCase):
    def test_all_conditional_shapes(self):
        rc, stdout = compile_and_run_stdlib_capture(_SRC, timeout=15)
        self.assertEqual(0, rc, f"program exited with {rc}; stdout:\n{stdout}")
        self.assertEqual(_EXPECTED_LINES, stdout.splitlines())
