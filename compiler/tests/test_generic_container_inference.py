"""Generic argument inference from container-typed arguments alone.

A call like `head(l)` with `l: List<String>` must bind T=String by unifying
the declared `List<T>` parameter against the argument type — the same way
`contains(l, x)` binds T from the bare `x: T` argument. Found by the yaflc
self-hosting prototype: every such call (head, tail, isEmpty, chain, ...)
failed to monomorphise and CRASHED codegen instead of erroring.

The inference itself is a [test] in
compiler/yafl_tests/generic_container_inference.yafl; here, the call that
cannot be inferred must be an error.
"""
from tests.testutil import TimedTestCase
from tests.testutil import compile_errors

class TestUninferableGenericCall(TimedTestCase):
    def test_uninferable_call_is_an_error_not_a_crash(self):
        # T appears nowhere in the arguments and no expected type reaches the
        # call: inference CANNOT ground it. That must be a compile error at
        # the call site — not a checked_cast crash in codegen.
        out = compile_errors("""
namespace Main
import System

fun pick<T>(): T|None
  ret None

fun main(): System::Int
  ret match(pick())
    () => 0
""").lower()
        self.assertIn("pick", out)
        self.assertIn("type argument", out)
