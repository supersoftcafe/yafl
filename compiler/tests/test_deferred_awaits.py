"""Deferred awaits (lowering/defer_awaits.py): a call that may suspend is
awaited where its result is used, not where it is made. Its result is kept as
returned; a copy or field read of it is virtual; every use is preceded by an
Await, which parks only on a task still running.

These check the shape of the C: the calls come before the first await. The
behaviour — that the calls really run at the same time — is checked by
compiler/yafl_tests/deferred_awaits.yafl.
"""
from __future__ import annotations

import re

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

    def _hot_path_until_return(self, src: str, function: str) -> str:
        """The hot path of `function` up to its first `return`: the code a
        caller runs before it is handed the result."""
        c_code = compile_c(src)
        definition = re.search(r"^\S.*\b" + function + r"_\w+\(object_t\* this.*\)\n\{\n", c_code, re.MULTILINE)
        body = c_code[definition.end():c_code.index("\n}\n", definition.end())]
        return body[:body.index("return ")]

    def test_a_ternary_of_pending_results_returns_without_awaiting(self):
        src = _HDR + """\
fun [future] square(x: System::Int): System::Int
  ret x * x

fun pick(b: System::Bool): System::Int
  let a = square(3)
  let c = square(4)
  ret b ? a : c

fun main(): System::Int
  ret pick(true) - 9
"""
        head = self._hot_path_until_return(src, "Main__pick")
        self.assertEqual(2, head.count("Main__square_"), head)
        self.assertNotIn("TASK_RUNNING", head)

    def test_an_early_return_of_a_pending_result_returns_without_awaiting(self):
        src = _HDR + """\
fun [future] square(x: System::Int): System::Int
  ret x * x

fun pick(b: System::Bool): System::Int
  let a = square(3)
  let c = square(4)
  if b
    ret a
  ret c

fun main(): System::Int
  ret pick(true) - 9
"""
        head = self._hot_path_until_return(src, "Main__pick")
        self.assertEqual(2, head.count("Main__square_"), head)
        self.assertNotIn("TASK_RUNNING", head)

    def test_a_pending_result_saved_across_a_park_keeps_its_value_traced(self):
        # `g` is still pending when `use` parks on `total`, so it is saved in
        # the state object in its task-carrying shape. G has no pointer at the
        # top level, so that shape is `{value, task}` — but its value holds
        # heap pointers (a String, a Set), and when `compute` finished
        # synchronously they are the live result. The collector must see them:
        # a save that marks only `.task` leaves them to be moved or freed.
        src = _HDR + """\
enum Res
  enum ResOk(items: List<Int>)
  enum ResText(text: String, code: Int)

class [final] G(res: Res, warns: Set<String>)

fun [future] compute(n: Int): G
  ret G(ResText("t", n), add(Set<String>(), "w"))

fun [future] total(n: Int): Int
  ret n + 1

fun use(n: Int): Int
  let g = compute(n)
  let m = total(n) * 2
  ret contains(g.warns, "w") ? m : 0

fun main(): Int
  ret use(2) == 6 ? 0 : 1
"""
        code = compile_c(src)
        saves = [line for line in code.splitlines()
                 if "GC_STORE_MUTABLE_IN" in line and ".task)" in line]
        self.assertTrue(saves, "no {value, task} result is saved across a park")
        for line in saves:
            self.assertIn(".value.", line, line)


class TestConstructionIsAtomic(TestCase):
    def test_a_pending_field_value_is_awaited_before_the_allocation(self):
        """A construction is atomic: the allocation and its initialising stores
        run with no safe point between them, which is what lets those stores
        skip the write barrier. An await placed at the store that reads a
        pending value would split it: the half-built object would sit in the
        heap across the suspension, be marked or even promoted, and then take
        a young value it never records (the self-compile with
        YAFL_LOCAL_GC=0: a PsDestructure built by an inlined `with`, its
        target list reclaimed under it). So the await goes before the
        allocation."""
        from codegen.gen import Application
        from codegen.ir import Function
        from codegen.ops import Await, Call, Move, NewObject, Return
        from codegen.param import GlobalFunction, NewStruct, NullPointer, ObjectField, StackVar
        from codegen.typedecl import DataPointer, Struct
        from lowering.defer_awaits import defer_awaits

        r, x, box = (StackVar(DataPointer(), n) for n in ("r", "x", "box"))
        ops = (Call(GlobalFunction("g"), NewStruct((("this", NullPointer()),)), register=r),
               NewObject("Box", box),
               Move(ObjectField(DataPointer(), box, "Box", "a", None, fresh=True), x),
               Move(ObjectField(DataPointer(), box, "Box", "b", None, fresh=True), r),
               Return(box))
        fn = Function(name="f", params=Struct((("this", DataPointer()), ("x", DataPointer()))),
                      result=DataPointer(),
                      stack_vars=Struct((("r", DataPointer()), ("box", DataPointer()))), ops=ops)
        out = defer_awaits(Application(functions={"f": fn})).functions["f"].ops
        kinds = [type(op).__name__ for op in out]
        self.assertIn("Await", kinds, kinds)
        self.assertLess(kinds.index("Await"), kinds.index("NewObject"), kinds)
        stores = [op for op in out if isinstance(op, Move) and isinstance(op.target, ObjectField)]
        self.assertEqual(kinds.index("NewObject") + 1, out.index(stores[0]), kinds)
        self.assertEqual(out.index(stores[0]) + 1, out.index(stores[1]), kinds)
