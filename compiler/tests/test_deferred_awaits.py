"""Deferred awaits (async_lower `__defer_awaits`): a call that may suspend is
awaited where its result is used, not where it is made. Its result is kept as
returned; a copy or field read of it is virtual; every use is preceded by an
Await, which parks only on a task still running.

These check the shape of the C: the calls come before the first await. The
behaviour — that the calls really run at the same time — is checked by
compiler/yafl_tests/deferred_awaits.yafl.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_c

_HDR = "namespace Main\nimport System\n"


def _body(c_code: str, function: str) -> str:
    """The C body of the function whose name starts `function`."""
    start = c_code.index("\n{\n", c_code.index(function + "_", c_code.index("// " + "Main::main")))
    return c_code[start:c_code.index("\n}\n", start)]


class TestDeferredAwaits(TestCase):
    def test_two_calls_start_before_either_is_awaited(self):
        src = _HDR + """\
fun [future] square(x: System::Int): System::Int
  ret x * x

fun main(): System::Int
  let a = square(3)
  let b = square(4)
  ret a + b - 25
"""
        body = _body(compile_c(src), "Main__main")
        first_await = body.index("TASK_RUNNING")
        self.assertEqual(2, body[:first_await].count("Main__square_"), body)

    def test_destructuring_a_pending_tuple_waits_for_nothing(self):
        src = _HDR + """\
fun [future] pair(x: System::Int): (a: System::Int, b: System::Int)
  ret (x, x + 1)

fun [future] square(x: System::Int): System::Int
  ret x * x

fun main(): System::Int
  let (a, b) = pair(3)
  let c = square(4)
  ret a + b + c - 23
"""
        body = _body(compile_c(src), "Main__main")
        first_await = body.index("TASK_RUNNING")
        before = body[:first_await]
        self.assertIn("Main__pair_", before, body)
        self.assertIn("Main__square_", before, body)
