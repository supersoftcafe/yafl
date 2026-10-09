"""[tail] self-recursion lowers to a back-edge loop — no trampoline.

Every `[tail]` self-recursive function (sync or async, top-level or nested)
becomes a loop. A sync one is a plain synchronous C function; an async one is a
loop *inside* the async state machine, with the loop-carried vars promoted to
the task heap across suspensions. No worker-queue dispatch / task is generated
for the recursion. A nested `[tail]` function is lowered before closure
conversion (while its self-call is still direct); a capturing one then becomes a
loop inside its closure.

A `[tail]` function whose self-call is not in tail position is a compile error.
A self-call captured in a surviving closure belongs to the closure (a normal
recursive call to this function), not to the tail recursion, so it is not
counted as a tail call and must not trip the non-tail-position error.

Runtime behaviour is checked by compiler/yafl_tests/tail_loop.yafl.
"""
from __future__ import annotations

import os
import tempfile


from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture
from tests.testutil import compile_c


_COUNTDOWN = """\
import System

fun [tail] count(n: System::Int, acc: System::Int): System::Int
  ret n == 0 ? acc : count(n - 1, acc + 1)

fun main(): System::Int
  print(String(count(5, 0)) + "\\n")
  print(String(count(1000000, 0)) + "\\n")
  ret 0
"""

# A self-call that is NOT in tail position (its result is consumed by `+`).
_NON_TAIL = """\
import System

fun [tail] bad(n: System::Int): System::Int
  ret n == 0 ? 0 : 1 + bad(n - 1)

fun main(): System::Int
  ret bad(3)
"""

# A `[tail]` function whose base case binds a closure that captures a self-call.
# The closure escapes the inliner, so a LambdaExpression survives to the tail
# pass; its `countdown(x, x)` must be ignored (it is the closure's call, not a
# tail call), while the real tail self-call still lowers to a loop.

# `[tail]` on a *nested* function is supported: tail lowering runs before
# closure conversion, so the recursion is turned into a constant-stack loop
# while the self-call is still direct. A capturing nested `[tail]` function is
# closure-converted afterwards (its captured state lives on the closure) and the
# loop rides along. Both of these run to a large iteration count without
# overflowing the stack — proof the recursion became a loop, not deep recursion.
#
# `loop` captures the enclosing parameter `s`; each iteration adds length(s)=2,
# so outer("xy") == 2 * 1_000_000.
_CAPTURING_NESTED_TAIL = """\
import System

fun outer(s: System::String): System::Int
  fun [tail] loop(i: System::Int, acc: System::Int): System::Int
    ret i == 0 ? acc : loop(i - 1, acc + System::length(s))
  ret loop(1000000, 0)

fun main(): System::Int
  ret outer("xy") == 2000000 ? 0 : 1
"""


class TestTailLoop(TestCase):
    def test_tail_lowers_to_loop_no_trampoline(self):
        # Generated C: the loop head is present and no trampoline machinery
        # (tailcallback / tailimpl) is emitted anywhere.
        ccode = compile_c(_COUNTDOWN, "t.yafl")
        self.assertTrue(ccode, "compilation produced no output")
        self.assertIn("loophead", ccode, "expected a back-edge loop label")
        self.assertNotIn("tailcallback", ccode, "no [tail] trampoline machinery should remain")
        self.assertNotIn("tailimpl", ccode, "no [tail] trampoline machinery should remain")


    def test_non_tail_self_call_is_an_error(self):
        # `[tail]` asserts a tail-recursive loop; a non-tail self-call must be
        # rejected at compile time rather than silently losing the guarantee.
        ccode = compile_c(_NON_TAIL, "t.yafl")
        self.assertFalse(ccode, "a non-tail self-call under [tail] should fail to compile")


    def test_async_tail_loop_runs_constant_stack(self):
        # An async `[tail]` loop: io.read(1) suspends every iteration with the
        # counter live across the suspend, so the loop runs inside the async
        # state machine with its loop-carried vars promoted to the task heap.
        # A broken edge-aware saved-var promotion (or a skipped loop-head block)
        # would corrupt the count or crash under GC. The iteration count is far
        # beyond what a non-`[tail]` async recursion could survive.
        n = 50000
        with tempfile.NamedTemporaryFile(suffix=".dat", delete=False) as f:
            f.write(b"x" * n)
            path = f.name
        try:
            src = f"""\
import System
import System::IO

fun [tail] _count(io: IO, n: System::Int): (io: IO, v: System::Int)
  let r = io.read(1)
  ret match(r.v)
    (s: System::String) => _count(r.io, n + 1)
    (e: IOError)        => (r.io, n)

fun _done(r: (io: IO, v: System::Int), expected: System::Int): System::Int
  let _closed = r.io.close()
  ret r.v == expected ? 0 : 1

fun main(): System::Int
  ret match(open_read("{path}"))
    (h: IO)      => _done(_count(h, 0), {n})
    (e: IOError) => 255
"""
            rc, out = compile_and_run_stdlib_capture(src, timeout=30)
            self.assertEqual(0, rc, f"async [tail] byte count != {n}; stdout:\n{out}")
        finally:
            os.unlink(path)


    def test_nested_tail_lowers_to_loop(self):
        # The nested `[tail]` compiles to a back-edge loop with no trampoline.
        ccode = compile_c(_CAPTURING_NESTED_TAIL, "t.yafl")
        self.assertTrue(ccode, "nested [tail] should compile")
        self.assertIn("loophead", ccode, "expected a back-edge loop label")
        self.assertNotIn("tailcallback", ccode, "no [tail] trampoline machinery should remain")


# The self-call sits in the FINAL LAMBDA of a pipeline, not directly in the
# function body. `|>` lowers structurally into let-bindings (no closure), so
# the call must still be recognised as tail position and lower to a loop —
# proven by running to 1,000,000 without overflowing the C stack. Two shapes:
# a single stage, and a two-stage pipeline whose middle stage re-tuples.


