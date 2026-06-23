"""Probe for the StreamIO design's load-bearing assumption.

The proposed IO stream is encoded as a node holding a *zero-arg closure
that captures a `[lazy]` let*:

    fun node(...):
        let [lazy] step: Step = pull(...)   # deferred
        ret Node(() => step)                  # closure captures the stub

Everything depends on the lambda capturing the **unforced** `Lazy$` stub
(with the `lazy_fetch` happening inside the closure body), not forcing the
let at env-construction time. If capture forced eagerly, an infinite lazy
stream would diverge the instant it is built.

`test_infinite_lazy_stream_terminates` builds exactly that pattern over
pure data (no IO, no generics): taking the 5th element of an infinite
`nats` stream terminates only because capture deferred the let. A
regression that forces at capture time turns `nats(0)` into unbounded
self-recursion -> timeout.

`test_tuple_shaped_lazy_capture` is the regression for the root-cause fix:
capturing a *struct/tuple-shaped* `[lazy]` let in a closure used to
miscompile (the `Lazy$` stub is `object_t*` but the capture site read the
slot as the forced struct type). The capture site now reads the raw stub
pointer (`LazyExpression(stub_only=True)`), so a closure can capture an
unforced `[lazy]` value of *any* shape — tuple or class.
"""
from tests.testutil import TimedTestCase as TestCase, compile_and_run


_PRELUDE = (
    "namespace System\n"
    "typealias Int : __builtin_type__<bigint>\n"
    "typealias Bool : __builtin_type__<bool>\n"
    "fun `+`(left: System::Int, right: System::Int): System::Int\n"
    "    ret __builtin_op__<bigint>(\"integer_add\", left, right)\n"
    "fun `-`(left: System::Int, right: System::Int): System::Int\n"
    "    ret __builtin_op__<bigint>(\"integer_sub\", left, right)\n"
    "fun `>`(left: System::Int, right: System::Int): System::Bool\n"
    "    ret __builtin_op__<bool>(\"integer_test_gt\", left, right)\n"
)

# An infinite stream of naturals encoded as a closure over a `[lazy]` let.
# The lazy cell's value is a `[final] class Step` (pointer-shaped). `nats(n+1)`
# lives inside the lazy initialiser, so building a node does NOT recurse; only
# forcing a node advances by one.
_STREAM = (
    "class [final] Step(head: System::Int, tail: Stream)\n"
    "class [final] Stream(thunk: (): Step)\n"
    "fun nats(n: System::Int): Stream\n"
    "    let [lazy] step: Step = Step(n, nats(n + 1))\n"
    "    ret Stream(() => step)\n"
    "fun nth(s: Stream, i: System::Int): System::Int\n"
    "    let step = s.thunk()\n"
    "    ret i > 0 ? nth(step.tail, i - 1) : step.head\n"
)


class TestLazyStreamCapture(TestCase):

    def test_infinite_lazy_stream_terminates(self):
        """Taking the 5th element of an infinite lazy stream terminates and
        yields 5 — only possible if capturing the `[lazy]` let deferred it."""
        content = _PRELUDE + _STREAM + (
            "fun main(): System::Int\n"
            "    ret nth(nats(0), 5)\n"
        )
        exit_code, _ = compile_and_run(content)
        self.assertEqual(exit_code, 5)

    def test_deeper_index_still_terminates(self):
        """A larger index forces more nodes but each read happens once; the
        successor chain stays lazy throughout."""
        content = _PRELUDE + _STREAM + (
            "fun main(): System::Int\n"
            "    ret nth(nats(10), 7)\n"
        )
        exit_code, _ = compile_and_run(content)
        self.assertEqual(exit_code, 17)

    def test_tuple_shaped_lazy_capture(self):
        """Regression: a `[lazy]` let of a *tuple* captured in a closure now
        compiles and runs. The capture site reads the raw stub pointer rather
        than the forced struct, so any-shaped lazy value can be captured."""
        content = _PRELUDE + (
            "class [final] Stream(thunk: (): (head: System::Int, tail: Stream))\n"
            "fun nats(n: System::Int): Stream\n"
            "    let [lazy] step: (head: System::Int, tail: Stream) = (head=n, tail=nats(n + 1))\n"
            "    ret Stream(() => step)\n"
            "fun nth(s: Stream, i: System::Int): System::Int\n"
            "    let step = s.thunk()\n"
            "    ret i > 0 ? nth(step.tail, i - 1) : step.head\n"
            "fun main(): System::Int\n"
            "    ret nth(nats(0), 5)\n"
        )
        exit_code, _ = compile_and_run(content)
        self.assertEqual(exit_code, 5)
