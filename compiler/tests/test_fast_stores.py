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

import compiler as c
from tests.testutil import BatchedTestCase as TestCase


# `both` suspends at a `__parallel__` with two pointer locals live across it,
# so its state object is allocated at `$asynccommon` and then filled with
# `prefix`/`suffix` (trailing array slots) and `my_task` (an inline field).
# No `namespace` declaration: the unit lands in `Main`.
_SRC = """\
import System

fun [impure] work(s: System::String, n: System::Int32): System::String
  ret n <= 0i32 ? s : work(s + "x", n - 1i32)

fun [impure] both(a: System::String, b: System::String): System::String
  let prefix = work(a, 2i32)
  let suffix = work(b, 2i32)
  let (l, r) = __parallel__(() => work(a, 3i32), () => work(b, 3i32))
  ret prefix + l + r + suffix

fun main(): System::Int
  ret length(both("p", "q")) > 0 ? 0 : 1
"""

# One compile per -O level for the whole class: each is a full stdlib build.
_EMITTED: dict[int, str] = {}


def _emit(level: int) -> str:
    if level not in _EMITTED:
        _EMITTED[level] = c.compile([c.Input(_SRC, "file.yafl")], use_stdlib=True,
                                    just_testing=False, optimization_level=level)
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


def _barriers_on(body: str, pointer: str) -> list[str]:
    """Every GC_WRITE_BARRIER in `body` taken through the local `pointer`."""
    return [ln.strip() for ln in body.splitlines()
            if "GC_WRITE_BARRIER" in ln and f"){pointer})->" in ln]


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
        so the second store must keep its barrier — one, not two."""
        body = _body(_emit(2), "Main__both")
        my_task = [ln for ln in _barriers_on(body, "_sv_state") if "->my_task" in ln]
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
        """`task_init(_sv_par_task)` takes the fresh object as an argument, so
        the callee may retain it and the call is a safe point. The closure
        stores after it keep their barriers."""
        fork = [blk for blk in _emit(2).split("\n}\n") if "_sv_par_task" in blk]
        self.assertTrue(fork, "no parallel fork block in the emitted C")
        self.assertTrue(any(_barriers_on(blk, "_sv_par_task") for blk in fork),
                        "a store after a call that took the pointer lost its barrier")

    def test_o0_is_unchanged(self):
        """The pass is gated at -O1; -O0 keeps today's codegen exactly."""
        body = _body(_emit(0), "Main__both")
        saves = [ln for ln in _barriers_on(body, "_sv_state") if "->array" in ln]
        self.assertNotEqual([], saves, body)
