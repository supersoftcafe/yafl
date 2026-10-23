"""`[future]` functions: a call hands the body to a worker and answers later,
with a task, like any async call (lowering/future_functions.py). The body
opens with the runtime's `future_yield`; when the pool isn't accepting
(YAFL_TASK_BACKLOG exceeded) that answers at once and the body runs in place.
Semantics are identical to the same program without the attribute, so these
are structural tests, plus the errors (no timing assertions — shared host).

Runtime behaviour is checked by compiler/yafl_tests/future_functions.yafl.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib
from tests.testutil import compile_c
from tests.testutil import compile_errors

_HDR = "namespace Main\nimport System\n"

_DOUBLE = _HDR + """\
fun [future] double(x: System::Int): System::Int
  ret x * 2

fun main(): System::Int
  ret double(21)
"""


class TestFutureFunctions(TestCase):
    def test_future_engages_the_yield(self):
        # Semantically invisible, so prove engagement structurally: the body
        # opens with the runtime's yield.
        self.assertIn("future_yield(", compile_c(_DOUBLE))

    def test_future_function_is_never_inlined(self):
        # Tiny, and -O3: any inliner would take it. Its body is the unit a
        # worker runs, so it must survive as a function of its own.
        self.assertIn("Main__double_", compile_c(_DOUBLE, optimization_level=3))

    def test_runs_in_place_when_pool_full(self):
        # YAFL_TASK_BACKLOG=0: the pool never accepts, future_yield answers at
        # once and the body runs on the caller's thread. Same answer.
        self.assertEqual(42, compile_and_run_stdlib(_DOUBLE, env={"YAFL_TASK_BACKLOG": "0"}))

    def test_future_takes_no_arguments(self):
        src = _DOUBLE.replace("[future]", "[future(1)]")
        self.assertIn("[future] takes no arguments", compile_errors(src))

    def test_future_foreign_is_an_error(self):
        src = _HDR + """\
fun [future, foreign("abs")] magnitude(x: System::Int32): System::Int32

fun main(): System::Int
  ret System::Int(magnitude(-42i32))
"""
        self.assertIn("[future] cannot be applied to a foreign function", compile_errors(src))

    def test_future_sync_is_an_error(self):
        src = _DOUBLE.replace("[future]", "[future, sync]")
        self.assertIn("[future] and [sync] contradict", compile_errors(src))
