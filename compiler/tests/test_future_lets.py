"""`[future]` lets: the initialiser is posted to the worker pool at bind time;
the binding's slot holds the deferred stub (the `[lazy]` machinery), and every
read forces — parking on the completion if the worker hasn't finished, memoised
thereafter. When the pool isn't accepting (YAFL_TASK_BACKLOG exceeded) the post
is skipped and the binding degrades to plain lazy: first read evaluates.
Semantics are identical to the same program without the attribute — only the
timing overlaps. Structural tests only (no timing assertions — shared host).
"""
from __future__ import annotations

import io
import contextlib

import compiler as c
from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib

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
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            c_code = c.compile([c.Input(src, "t.yafl")], use_stdlib=True, just_testing=False)
        self.assertIn("future_post", c_code)

    def test_basic_read(self):
        # One future, one read: the value, whoever computed it.
        src = _HDR + """\
fun double(x: System::Int): System::Int
  ret x * 2

fun main(): System::Int
  let [future] a = double(21)
  ret a
"""
        self.assertEqual(42, compile_and_run_stdlib(src))

    def test_memoised_rereads(self):
        # A non-linear future reads many times; every read is the same value.
        src = _HDR + """\
fun double(x: System::Int): System::Int
  ret x * 2

fun main(): System::Int
  let [future] a = double(7)
  ret a + a + a
"""
        self.assertEqual(42, compile_and_run_stdlib(src))

    def test_concurrent_forcers(self):
        # The future's stub is captured by both __parallel__ branches: two
        # tasks force the same stub concurrently (the waiter-chain path).
        src = _HDR + """\
fun double(x: System::Int): System::Int
  ret x * 2

fun main(): System::Int
  let [future] a = double(10)
  let (x, y) = __parallel__(() => a + 1, () => a + 2)
  ret x + y
"""
        self.assertEqual(43, compile_and_run_stdlib(src))

    def test_future_of_union(self):
        # The payload is an inferred-friendly union; the read narrows by match.
        src = _HDR + """\
fun pick(b: System::Bool): System::Int | System::None
  ret b ? 5 : None

fun main(): System::Int
  let [future] a = pick(true)
  ret match(a)
    (i: System::Int)  => i
    (n: System::None) => 0
"""
        self.assertEqual(5, compile_and_run_stdlib(src))

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

    def test_linear_payload_single_read(self):
        # A future of a linear value: the thunk runs exactly once (claim
        # protocol), so the capture is consumed once; the BINDING becomes
        # linear — its single read is the consumption.
        src = _HDR + """\
class [linear,final] Tok(v: System::Int)
  fun [terminal] consume(): System::Int
    ret this.v

fun main(): System::Int
  let [future] r = Tok(9)
  ret r.consume()
"""
        self.assertEqual(9, compile_and_run_stdlib(src))

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
