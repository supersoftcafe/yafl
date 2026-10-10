"""`[future]` lets: the initialiser is posted to the worker pool at bind time;
the binding's slot holds the deferred stub (the `[lazy]` machinery), and every
read forces — parking on the completion if the worker hasn't finished, memoised
thereafter. When the pool isn't accepting (YAFL_TASK_BACKLOG exceeded) the post
is skipped and the binding degrades to plain lazy: first read evaluates.
Semantics are identical to the same program without the attribute — only the
timing overlaps. Structural tests only (no timing assertions — shared host).

Runtime behaviour is checked by compiler/yafl_tests/future_lets.yafl.
"""
from __future__ import annotations


from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib
from tests.testutil import compile_c

_HDR = "namespace Main\nimport System\n"


class TestFutureLets(TestCase):
    def test_future_engages_the_machinery(self):
        # The feature is semantically invisible (that's the point), so a
        # correctness run can't tell "working" from "attribute ignored".
        # Structural proof: the generated C posts the stub to the worker pool.
        src = _HDR + """\
fun double(x: System::Int): System::Int
  ret x * 2

fun main(): System::Int
  let [future] a = double(21)
  ret a
"""
        c_code = compile_c(src, "t.yafl")
        self.assertIn("future_post", c_code)


    def test_degrades_to_lazy_when_pool_full(self):
        # YAFL_TASK_BACKLOG=0 -> thread_work_accepting() is never true -> the
        # post is skipped and the first read evaluates in place. Same answer.
        src = _HDR + """\
fun double(x: System::Int): System::Int
  ret x * 2

fun main(): System::Int
  let [future] a = double(21)
  ret a
"""
        self.assertEqual(42, compile_and_run_stdlib(src, env={"YAFL_TASK_BACKLOG": "0"}))


    def test_linear_payload_unread_is_error(self):
        # A never-read future of a linear value never consumes it — a
        # linearity error, not a silent leak.
        src = _HDR + """\
class [linear,final] Tok(v: System::Int)

fun main(): System::Int
  let [future] r = Tok(9)
  ret 0
"""
        with self.assertRaises(AssertionError):
            compile_and_run_stdlib(src)

    def test_global_future_is_an_error(self):
        # v1 scope: local lets only — a global initialises at startup, before
        # the pool is useful, and would silently degrade to [lazy].
        src = _HDR + """\
fun double(x: System::Int): System::Int
  ret x * 2

let [future] g: System::Int = double(21)

fun main(): System::Int
  ret g
"""
        with self.assertRaises(AssertionError):
            compile_and_run_stdlib(src)

    def test_destructure_future_is_an_error(self):
        src = _HDR + """\
fun main(): System::Int
  let [future] (a, b) = (1, 2)
  ret a + b
"""
        with self.assertRaises(AssertionError):
            compile_and_run_stdlib(src)

    def test_lazy_future_conflict_is_an_error(self):
        src = _HDR + """\
fun main(): System::Int
  let [lazy,future] a = 1 + 2
  ret a
"""
        with self.assertRaises(AssertionError):
            compile_and_run_stdlib(src)

    def test_future_takes_no_arguments(self):
        src = _HDR + """\
fun main(): System::Int
  let [future(2)] a = 1 + 2
  ret a
"""
        with self.assertRaises(AssertionError):
            compile_and_run_stdlib(src)
