"""Per-call-site sync: a call whose function value is provably sync is a
plain call — no basic-block split, no resume case, no IfTask.

Sync-ness is a flag on the function-value type (`FuncPointer.sync`) that
follows values through Moves, merges (AND) at Phi, flows from arguments into
parameters, from Returns into call results and from stores into object
fields. Anything the flow cannot see is may-suspend.

One program, one compile (the stdlib compile is the whole cost): each case
owns suffixed functions and `main` calls them all. `suspendy` is a foreign
function without `[sync]` — the source of asyncness. The C is never linked;
every assertion reads the IR captured at the output of `lower_async`. The
`_PAD` tail on each body keeps it over the AST inliner's size threshold, so
the function under test survives to be inspected.
"""
from __future__ import annotations

import functools
from unittest import mock

import compiler as c
import lowering.async_lower
from codegen.gen import Application
from codegen.ir import Function
from codegen.ops import Call, IfTask
from tests.testutil import TimedTestCase as TestCase


_INT = "System::Int"
_FN = f"(:{_INT}): {_INT}"
_PAD = "(x==0?1:x==1?2:x==2?3:x==3?4:x==4?5:6)"

_PROGRAM = f"""namespace Main
import System
fun [foreign("suspendy"),impure] suspendy(x: {_INT}): {_INT}

fun count(n: {_INT}): {_INT}
  ret n == 0 ? 0 : 1 + count(n - 1)

fun [tail] loopA(n: {_INT}, acc: {_INT}, f: {_FN}): {_INT}
  ret n == 0 ? acc : loopA(n - 1, f(acc), f)

fun [tail] loopB(n: {_INT}, acc: {_INT}, f: {_FN}): {_INT}
  ret n == 0 ? acc : loopB(n - 1, f(acc), f)

class BoxA(f: {_FN})
fun applyA(b: BoxA, x: {_INT}): {_INT}
  ret b.f(x) + {_PAD}

class BoxB(f: {_FN})
fun applyB(b: BoxB, x: {_INT}): {_INT}
  ret b.f(x) + {_PAD}

# Five fields: over the flattening limit, so these stay heap objects and
# the closure is read back through an ObjectField.
class HeapC(f: {_FN}, a: {_INT}, b: {_INT}, c: {_INT}, d: {_INT})
fun applyC(h: HeapC, x: {_INT}): {_INT}
  ret h.f(x) + h.a + {_PAD}

class HeapD(f: {_FN}, a: {_INT}, b: {_INT}, c: {_INT}, d: {_INT})
fun applyD(h: HeapD, x: {_INT}): {_INT}
  ret h.f(x) + h.a + {_PAD}

fun twice(f: {_FN}, x: {_INT}): {_INT}
  ret f(f(x)) + {_PAD}
fun use(g: (:{_FN}, :{_INT}): {_INT}): {_INT}
  ret g((x: {_INT}) => suspendy(x), 3)

fun helper(x: {_INT}): {_INT}
  ret x * 2 + {_PAD}
fun mixed(x: {_INT}): {_INT}
  let a = helper(x)
  let b = suspendy(a)
  ret helper(b)
fun pure(x: {_INT}): {_INT}
  let a = helper(x)
  ret helper(a) + 1

fun main(): {_INT}
  ret count(10)
    + loopA(10, 0, (x: {_INT}) => x + 1)
    + loopB(10, 0, (x: {_INT}) => x + 1)
    + loopB(10, 0, (x: {_INT}) => suspendy(x))
    + applyA(BoxA((x: {_INT}) => x + 1), 3)
    + applyB(BoxB((x: {_INT}) => x + 1), 3)
    + applyB(BoxB((x: {_INT}) => suspendy(x)), 4)
    + applyC(HeapC((x: {_INT}) => x + 1, 1, 2, 3, 4), 3)
    + applyD(HeapD((x: {_INT}) => x + 1, 1, 2, 3, 4), 3)
    + applyD(HeapD((x: {_INT}) => suspendy(x), 1, 2, 3, 4), 4)
    + use(twice)
    + mixed(3)
    + pure(3)
"""


@functools.cache
def _lowered() -> Application:
    """The Application `lower_async` produced for `_PROGRAM` at -O0."""
    captured: list[Application] = []
    real = lowering.async_lower.lower_async

    def capture(a: Application) -> Application:
        result = real(a)
        captured.append(result)
        return result

    with mock.patch.object(lowering.async_lower, "lower_async", capture):
        c.compile([c.Input(_PROGRAM, "test.yafl")], use_stdlib=True, optimization_level=0)
    return captured[-1]


def _fn(name: str) -> Function:
    """The hot path of `Main::<name>` (not its `$async` machine)."""
    a = _lowered()
    matches = [f for n, f in a.functions.items()
               if n.startswith(f"Main::{name}@") and "$" not in n]
    assert len(matches) == 1, f"{name}: {sorted(a.functions)}"
    return matches[0]


def _task_checks(fn: Function) -> int:
    return sum(isinstance(op, IfTask) for op in fn.ops)


class TestSyncInference(TestCase):
    def test_non_tail_recursion_is_sync(self):
        # A recursive function reaching no suspension source never suspends.
        self.assertTrue(_fn("count").sync)

    def test_call_through_loop_phi_is_sync(self):
        # `f` reaches the call through the [tail] loop's Phi over the param;
        # the only argument ever passed is a sync lambda.
        self.assertTrue(_fn("loopA").sync)

    def test_one_async_argument_makes_the_param_fall(self):
        self.assertFalse(_fn("loopB").sync)

    def test_struct_slot_closure_is_sync(self):
        # BoxA flattens to a struct: the closure rides as a leaf of it.
        self.assertTrue(_fn("applyA").sync)

    def test_one_async_struct_slot_makes_the_leaf_fall(self):
        self.assertFalse(_fn("applyB").sync)

    def test_object_field_closure_is_sync(self):
        self.assertTrue(_fn("applyC").sync)

    def test_one_async_store_makes_the_field_fall(self):
        self.assertFalse(_fn("applyD").sync)

    def test_address_taken_function_param_is_may_suspend(self):
        # `twice` is only ever called through a function value, so the flow
        # cannot see what reaches its `f` — here an async lambda does.
        self.assertFalse(_fn("twice").sync)


class TestSyncCallSites(TestCase):
    def test_sync_callee_gets_no_task_check(self):
        # `mixed` suspends once (suspendy) and calls the sync `helper`
        # twice: only the suspendy call keeps its IfTask.
        mixed = _fn("mixed")
        self.assertFalse(mixed.sync)
        self.assertEqual(1, _task_checks(mixed))

    def test_sync_function_has_no_task_checks(self):
        pure = _fn("pure")
        self.assertTrue(pure.sync)
        self.assertEqual(0, _task_checks(pure))
        self.assertTrue(any(isinstance(op, Call) for op in pure.ops))
