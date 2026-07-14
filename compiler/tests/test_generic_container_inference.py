"""Generic argument inference from container-typed arguments alone.

A call like `head(l)` with `l: List<String>` must bind T=String by unifying
the declared `List<T>` parameter against the argument type — the same way
`contains(l, x)` binds T from the bare `x: T` argument. Found by the yaflc
self-hosting prototype: every such call (head, tail, isEmpty, chain, ...)
failed to monomorphise and CRASHED codegen instead of erroring.
"""
from tests.testutil import TimedTestCase, compile_and_run_stdlib

_SRC = """
namespace Main
import System

class [final] Thing(rank: System::Int)

fun sumRanks(l: List<Thing>, acc: System::Int): System::Int
  ret match(head(l))
    (x: Thing) => sumRanks(tail(l), acc + x.rank)
    ()         => acc

fun main(): System::Int
  let l: List<Thing> = append(append(List<Thing>(), Thing(4)), Thing(5))
  let e = isEmpty(l) ? 100 : 0
  let n = chainLength(chain(l))
  # 4+5 ranks, +0 for non-empty, +2 elements = 11
  ret sumRanks(l, 0) + e + n
"""


class TestGenericContainerInference(TimedTestCase):
    def test_container_only_calls_infer(self):
        self.assertEqual(11, compile_and_run_stdlib(_SRC))

    def test_string_element_type(self):
        self.assertEqual(1, compile_and_run_stdlib("""
namespace Main
import System

fun peek(l: List<String>): System::Int
  ret match(head(l))
    (x: String) => length(x)
    ()          => 0

fun main(): System::Int
  ret peek(append(List<String>(), "x"))
"""))


class TestUninferableGenericCall(TimedTestCase):
    def test_uninferable_call_is_an_error_not_a_crash(self):
        # T appears nowhere in the arguments and no expected type reaches the
        # call: inference CANNOT ground it. That must be a compile error at
        # the call site — not a checked_cast crash in codegen.
        import io, contextlib
        import compiler as c
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            c.compile([c.Input("""
namespace Main
import System

fun pick<T>(): T|None
  ret None

fun main(): System::Int
  ret match(pick())
    () => 0
""", "test.yafl")], use_stdlib=True, just_testing=True)
        out = buf.getvalue().lower()
        self.assertIn("pick", out)
        self.assertIn("type argument", out)
