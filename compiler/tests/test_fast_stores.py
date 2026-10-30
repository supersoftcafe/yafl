"""Fast stores — the write barrier elided on provably-fresh field stores.

`ObjectField.fresh` means "the object was allocated moments ago, straight-line
before this store, and nothing has published it": no SATB shading is owed and
no relocation can have happened, because opening a cycle needs a safe point and
there is none in the window.

Construction codegen sets the flag on the stores it emits itself. Nothing else
did — so the async state object, allocated at every suspension and immediately
filled with that site's live set, paid a barrier on every save.
`lowering/fast_stores.py` proves the same predicate by dataflow and sets the
flag there too.

The tests read the emitted C, because that is where the barrier is visible.
Each one is SCOPED to a single function body: a bare count over the whole
output would be dominated by unrelated stdlib functions and would pass or fail
for the wrong reasons.
"""
from __future__ import annotations

import re

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_c

from codegen.gen import Application
from codegen.ir import Function
from codegen.ops import Move, NewObject, ReturnVoid
from codegen.param import Integer, NewStruct, ObjectField, RuntimeInvoke, StackVar
from codegen.typedecl import DataPointer, Int, Struct, Void
from lowering.fast_stores import mark_fast_stores


# `both` suspends on two `[future]` calls with two POINTER locals live across it,
# so its state object is allocated at `$asynccommon` and then filled with
# `prefix`/`suffix` (trailing array slots) and `my_task` (an inline field).
# The locals are Int — a single pointer word (bigint). A String is a two-word
# value now, saved in an inline field, so it would never reach the array.
# No `namespace` declaration: the unit lands in `Main`.
_SRC = """\
import System

fun [impure] work(s: System::Int, n: System::Int32): System::Int
  ret n <= 0i32 ? s : work(s + 1, n - 1i32)

fun [impure, future] later(s: System::Int): System::Int
  ret work(s, 3i32)

fun [impure] both(a: System::Int, b: System::Int): System::Int
  let prefix = work(a, 2i32)
  let suffix = work(b, 2i32)
  let l = later(a)
  let r = later(b)
  ret prefix + l + r + suffix

fun main(): System::Int
  ret both(1, 2) > 0 ? 0 : 1
"""

# One compile per -O level for the whole class: each is a full stdlib build.
_EMITTED: dict[int, str] = {}


def _emit(level: int) -> str:
    if level not in _EMITTED:
        _EMITTED[level] = compile_c(_SRC, "file.yafl", optimization_level=level)
    return _EMITTED[level]


def _body(emitted: str, name_prefix: str) -> str:
    """The C body of the first DEFINED function whose name starts with
    `name_prefix` — never the forward declaration."""
    pattern = re.compile(r"^[\w \*]*\b" + re.escape(name_prefix) + r"\w*\([^;]*\)\s*$",
                         re.MULTILINE)
    for m in pattern.finditer(emitted):
        if not emitted[m.end():].lstrip().startswith("{"):
            continue
        start = emitted.index("{", m.end())
        return emitted[start:emitted.index("\n}", start)]
    raise AssertionError(f"no definition of {name_prefix}* in the emitted C")


# The barriered stores (yafl.h, "Pointer stores"); a store without a barrier is
# a plain assignment.
_STORE_MACROS = ("GC_STORE_IN(", "GC_STORE_PUBLISH_IN(", "GC_FILL_STORE_IN(")


def _barriers_on(body: str, pointer: str) -> list[str]:
    """Every barriered store in `body` taken through the local `pointer`."""
    return [ln.strip() for ln in body.splitlines()
            if ln.strip().startswith(_STORE_MACROS) and f"){pointer})->" in ln]


class TestFastStores(TestCase):
    def test_state_saves_lose_the_barrier(self):
        """The live-set saves into the freshly allocated state object — the
        `->array.a[i]` slots — carry no barrier: nothing has run between the
        allocation and the store."""
        body = _body(_emit(2), "Main__both")
        saves = [ln for ln in _barriers_on(body, "_sv_state") if "->array" in ln]
        self.assertEqual([], saves, body)

    def test_the_store_after_the_task_allocation_keeps_its_barrier(self):
        """`my_task` is written twice: NULL before the task allocation (fresh,
        elided) and the task itself after it. The allocation is a safe point,
        so the second store must keep its barrier — one, not two. The field is
        found by what is stored in it: its name is positional after
        lowering/canonicalise.py."""
        body = _body(_emit(2), "Main__both")
        field = re.search(r"_sv_state\)->(\w+), [^;]*, _sv_task\);", body)
        self.assertIsNotNone(field, body)
        my_task = [ln for ln in _barriers_on(body, "_sv_state")
                   if re.search(rf"->{field.group(1)}\b", ln)]
        self.assertEqual(1, len(my_task), body)

    def test_the_resume_path_keeps_every_barrier(self):
        """The `$async` state machine parks through its state PARAMETER, which
        no allocation in this function produced. Those stores are not fresh and
        must be untouched."""
        machines = [blk for blk in _emit(2).split("\n}\n")
                    if "object_t* _state" in blk and "_state)->" in blk]
        self.assertTrue(machines, "no $async machine in the emitted C")
        self.assertTrue(any(_barriers_on(blk, "_state") for blk in machines),
                        "the resume path lost a barrier it must keep")

    def test_an_escaping_object_keeps_its_barrier(self):
        """A runtime call that takes the fresh object as an argument may retain
        it, and is a safe point: the store after it keeps its barrier, while
        the one before it loses it."""
        box = StackVar(DataPointer(), "$box")
        def store(value: int) -> Move:
            return Move(ObjectField(Int(32), box, "Box", "v", None), Integer(value, 32))
        ops = (NewObject("Box", box),
               store(1),
               Move(StackVar(DataPointer(), "$discard"),
                    RuntimeInvoke("task_init", NewStruct((("task", box),)), DataPointer())),
               store(2),
               ReturnVoid())
        fn = Function(name="f", params=Struct((("this", DataPointer()),)), result=Void(),
                      stack_vars=Struct((("$box", DataPointer()), ("$discard", DataPointer()))),
                      ops=ops)
        marked = mark_fast_stores(Application(functions={"f": fn})).functions["f"].ops
        self.assertEqual([True, False], [op.target.fresh for op in marked
                                         if isinstance(op, Move) and isinstance(op.target, ObjectField)])

    def test_a_construction_store_after_a_safe_point_loses_its_flag(self):
        """Construction codegen marks its own stores fresh, but a later pass can
        put a safe point between the allocation and a store — a deferred await
        does exactly that, suspending mid-construction (the self-compile: a
        PsDestructure built across an await, its list stored barrier-free
        after the object had been marked, then reclaimed under it). This pass is the authority: a fresh flag it cannot prove goes,
        at every -O level, and at -O0 nothing is added."""
        box = StackVar(DataPointer(), "$box")
        def store(value: int, fresh: bool) -> Move:
            return Move(ObjectField(Int(32), box, "Box", "v", None, fresh=fresh), Integer(value, 32))
        ops = (NewObject("Box", box),
               store(1, True),
               store(2, False),
               Move(StackVar(DataPointer(), "$discard"),
                    RuntimeInvoke("task_init", NewStruct((("task", StackVar(DataPointer(), "$other")),)),
                                  DataPointer())),
               store(3, True),
               ReturnVoid())
        fn = Function(name="f", params=Struct((("this", DataPointer()),)), result=Void(),
                      stack_vars=Struct((("$box", DataPointer()), ("$discard", DataPointer()),
                                         ("$other", DataPointer()))),
                      ops=ops)
        def flags(app: Application) -> list[bool]:
            return [op.target.fresh for op in app.functions["f"].ops
                    if isinstance(op, Move) and isinstance(op.target, ObjectField)]
        self.assertEqual([True, True, False],
                         flags(mark_fast_stores(Application(functions={"f": fn}))))
        self.assertEqual([True, False, False],
                         flags(mark_fast_stores(Application(functions={"f": fn}), add=False)))

    def test_o0_is_unchanged(self):
        """The pass is gated at -O1; -O0 keeps today's codegen exactly."""
        body = _body(_emit(0), "Main__both")
        saves = [ln for ln in _barriers_on(body, "_sv_state") if "->array" in ln]
        self.assertNotEqual([], saves, body)


# A construction in a function that suspends: `with` rebuilds the Destr from
# the awaited `map` result, so the allocation follows the await (a
# construction is atomic, lowering/defer_awaits.py) and its stores follow the
# allocation with nothing between them. The new object is live after each
# store, and the liveness async lowering computes is no publication: those
# stores lost their flag in every async function of the self-compile.
_ASYNC_SRC = """\
import System

enum Stmt
  enum Destr(name: System::String, attrs: System::String, ty: System::Int,
             targets: System::List<Stmt>, dflt: System::Int, line: System::String)
  enum Let(n: System::String, t: System::Int)

fun [future] bump(p: Stmt): Stmt => match(p)
  (l: Let)  => with l(t = l.t + 1)
  (o: Stmt) => p

fun bumped(params: Stmt): Stmt => match(params)
  (d: Destr) => with d(targets = System::map(d.targets, (p) => bump(p)))
  (o: Stmt)  => params

fun main(): System::Int
  let s = bumped(Destr("a", "b", 1, System::prepend(Let("x", 1), System::List()), 2, "l"))
  ret match(s)
    (d: Destr) => System::isEmpty(d.targets) ? 1 : 0
    (o: Stmt)  => 1
"""


def _bodies(emitted: str, name_prefix: str) -> list[str]:
    """The C body of every DEFINED function whose name starts with
    `name_prefix` — an async function's launch and its state machine both."""
    pattern = re.compile(r"^[\w \*]*\b" + re.escape(name_prefix) + r"\w*\([^;]*\)\s*$",
                         re.MULTILINE)
    bodies = []
    for m in pattern.finditer(emitted):
        if emitted[m.end():].lstrip().startswith("{"):
            start = emitted.index("{", m.end())
            bodies.append(emitted[start:emitted.index("\n}", start)])
    return bodies


class TestConstructionInAnAsyncFunction(TestCase):
    def test_construction_stores_stay_barrier_free(self):
        """An immutable object is written only while it is fresh, so no store
        into the Destr takes a barrier, in either body. (The state object's
        saves are another matter: it is mutable.)"""
        for level in (0, 2):
            with self.subTest(level=level):
                emitted = compile_c(_ASYNC_SRC, "file.yafl", optimization_level=level)
                bodies = _bodies(emitted, "Main__bumped")
                self.assertTrue(bodies, "no definition of Main__bumped*")
                for body in bodies:
                    self.assertEqual([], [ln.strip() for ln in body.splitlines()
                                          if ln.strip().startswith(_STORE_MACROS)
                                          and "Main__Destr" in ln], body)


# An array-class construction tabulates its storage by calling the init
# function once per element, between the allocation and each store. The init
# call runs safe points, so the store is not fresh: it is a FILL, which owes
# no snapshot barrier (nothing is overwritten) but keeps its publication
# fence. `boxes` returns the array so the fill is not trimmed away.
_TAB_SRC = """\
import System

class Box(v: System::Int)

fun [impure] boxes(n: System::Int32): System::Array<Box>
  ret System::Array<Box>(n, (i: System::Int32) => Box(System::Int(i)))

fun main(): System::Int
  ret boxes(4i32).length > 0i32 ? 0 : 1
"""


class TestTabulateFillKeepsItsBarrier(TestCase):
    def _fill_stores(self, level: int) -> tuple[list[str], str]:
        emitted = compile_c(_TAB_SRC, "file.yafl", optimization_level=level)
        body = _body(emitted, "Main__boxes")
        return [ln.strip() for ln in body.splitlines() if "->array.a[" in ln], body

    def test_fill_store_is_barriered(self):
        for level in (0, 2):
            with self.subTest(level=level):
                stores, body = self._fill_stores(level)
                self.assertTrue(stores, body)
                self.assertTrue(any(ln.startswith(_STORE_MACROS) for ln in stores),
                                f"the tabulate fill store lost its barrier:\n{body}")


# Every barriered store the compilers emit goes through one of yafl.h's store
# macros, which order the fence, the barriers and the store themselves
# ("Pointer stores"). Generated code naming a part directly would bypass that
# order — and on x86 nothing else would notice, as the fence compiles to
# nothing there. The port emits the same C (the self-compile), so this covers
# both compilers.
_SHAPE_SRC = """\
import System

class Box(v: System::Int)

fun [impure] boxes(n: System::Int32): System::Array<Box>
  ret System::Array<Box>(n, (i: System::Int32) => Box(System::Int(i)))

fun [impure] pick(n: System::Int): Box
  let [lazy] b: Box = Box(n + 1)
  ret n > 0 ? b : Box(0)

fun main(): System::Int
  ret boxes(4i32).length > 0i32 && pick(3).v > 0 ? 0 : 1
"""
_BARRIER_PARTS = re.compile(r"\b(GC_WRITE_BARRIER_IN|GC_PUBLISH_IN|GC_MARK_SEEN"
                            r"|GC_PUBLISH_FENCE\w*|gc_root_overwrite|gc_root_publish)\(")


class TestStoresGoThroughTheStoreMacros(TestCase):
    def test_every_kind_of_store_uses_its_macro(self):
        for level in (0, 2):
            with self.subTest(level=level):
                emitted = compile_c(_SHAPE_SRC, "file.yafl", optimization_level=level)
                self.assertEqual([], [m.group(0) for m in _BARRIER_PARTS.finditer(emitted)])
                # The program reaches each kind generated code makes: a store
                # into a mutable object (a closure's, a state machine's, a lazy
                # stub's value) and an array tabulation (fill). Not
                # GC_STORE_PUBLISH_IN: that is the runtime's, for handing
                # values between threads; a static container (a global's stub)
                # is detected inside the object store macros.
                for macro in ("GC_STORE_IN(", "GC_FILL_STORE_IN("):
                    self.assertIn(macro, emitted)
                self.assertNotIn("GC_STORE_PUBLISH_IN(", emitted)
