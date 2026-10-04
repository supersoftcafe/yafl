"""Compiler-directed recycling (lowering/recycle.py) — the opt-in prototype.

Every program here is compiled with the stage ENABLED and run twice more:
once plain, once under YAFL_RECYCLE_POISON (a recycled object is poisoned
instead of reused, so a wrong "dead" verdict faults or aborts instead of
reading a stranger's fields). Each must print exactly what the same program
prints with recycling off. The C text is checked for the expected shape:
reuse tokens on a loop-carried replacement, nothing for published objects.
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile

import compiler as c
import lowering.recycle as recycle
from tests.testutil import BatchedTestCase as TestCase
from tests.testutil import _CLANG_BUILD_FLAGS, static_link_for


def _compile(src: str, level: int, enabled: bool) -> str:
    old = recycle.ENABLED
    recycle.ENABLED = enabled
    try:
        code = c.compile([c.Input(src, "test.yafl")], use_stdlib=True,
                         just_testing=False, optimization_level=level)
    finally:
        recycle.ENABLED = old
    assert code, "yafl compilation produced no output"
    return code


def _run(c_code: str, level: int, env: dict[str, str] | None = None) -> tuple[int, str, str]:
    with tempfile.NamedTemporaryFile(suffix="", delete=False) as tmp:
        binary = tmp.name
    try:
        r = subprocess.run(["clang", "-x", "c", "-", "-O1", *_CLANG_BUILD_FLAGS,
                            *static_link_for(level), "-o", binary],
                           input=c_code, text=True, capture_output=True, timeout=60)
        assert r.returncode == 0, f"clang failed:\n{r.stderr}"
        run = subprocess.run([binary], capture_output=True, timeout=60,
                             env={**os.environ, **(env or {})}, stdin=subprocess.DEVNULL)
        return run.returncode, run.stdout.decode(), run.stderr.decode()
    finally:
        os.unlink(binary)


def _stats(stderr: str) -> dict[str, int]:
    m = re.findall(r"\[GC RECYCLE\] pushed=(\d+) reused=(\d+) flushed_unused=(\d+) poisoned=(\d+)", stderr)
    assert m, f"no [GC RECYCLE] line in:\n{stderr[-2000:]}"
    pushed, reused, unused, poisoned = map(int, m[-1])
    return {"pushed": pushed, "reused": reused, "unused": unused, "poisoned": poisoned}


# A tail loop that replaces one heap object (an interface implementation, so
# never flattened to a value struct) with the next on every step.
_COUNTER = """namespace Main
import System

interface Counter
  fun step(): Counter
  fun value(): System::Int

class [final] Up(cur: System::Int, by: System::Int) : Counter
  fun step(): Counter
    ret Up(cur + by, by)
  fun value(): System::Int
    ret cur

fun [tail] drive(c: Counter, n: System::Int, acc: System::Int): System::Int
  ret n <= 0 ? acc : drive(c.step(), n - 1, acc + c.value())
"""


class TestRecycle(TestCase):
    def _check_same(self, src: str, level: int, expect_frees: bool = True) -> dict[str, int]:
        base = _run(_compile(src, level, enabled=False), level)
        rc_code = _compile(src, level, enabled=True)
        self.assertIn("#define YAFL_RECYCLE 1", rc_code)
        if expect_frees:
            self.assertRegex(rc_code, r"yafl_(reuse|recycle)")
        rec = _run(rc_code, level, {"YAFL_GC_STATS": "1"})
        poi = _run(rc_code, level, {"YAFL_GC_STATS": "1", "YAFL_RECYCLE_POISON": "1",
                                    "YAFL_GC_POISON": "1"})
        self.assertEqual(base[0], 0, base[2][-2000:])
        self.assertEqual((rec[0], rec[1]), (base[0], base[1]), rec[2][-2000:])
        self.assertEqual((poi[0], poi[1]), (base[0], base[1]), poi[2][-2000:])
        stats = _stats(rec[2])
        if expect_frees:
            self.assertGreater(stats["pushed"], 0)
            self.assertGreater(_stats(poi[2])["poisoned"], 0)
        return stats

    def test_off_by_default_emits_nothing(self):
        src = _COUNTER + """
fun main(): System::Int
  System::print(System::String(drive(Up(0, 1), 1000, 0)))
  ret 0
"""
        code = _compile(src, 3, enabled=False)
        self.assertNotIn("YAFL_RECYCLE", code)
        self.assertNotIn("yafl_re", code)

    def test_loop_carried_object_reuses_in_a_register(self):
        # -O3 inlines drive and step into main: the old Up dies a few reads
        # after the new one is built, so its reads hoist above the NewObject
        # and the old object becomes the new one's reuse token.
        src = _COUNTER + """
fun main(): System::Int
  System::print(System::String(drive(Up(0, 1), 200000, 0)))
  ret 0
"""
        code = _compile(src, 3, enabled=True)
        self.assertIn("yafl_reuse(", code)
        stats = self._check_same(src, 3)
        self.assertGreater(stats["reused"], 190000)

    def test_seed_still_used_after_the_loop_is_not_freed(self):
        # The loop is seeded by an object main reads again afterwards: the
        # entry edge must carry ownership FALSE, or the first iteration frees
        # it and the final read sees a recycled (or poisoned) slot.
        src = _COUNTER + """
fun main(): System::Int
  let seed = Up(5, 2)
  let r = drive(seed, 100000, 0)
  System::print(System::String(r) + " " + System::String(seed.value()))
  ret 0
"""
        self._check_same(src, 3)

    def test_published_objects_are_left_alone(self):
        # Each step's object is kept in a growing chain (published into the
        # next link) — none of them may be recycled.
        src = """namespace Main
import System

interface Link
  fun depth(): System::Int

class [final] End() : Link
  fun depth(): System::Int
    ret 0

class [final] Cons(head: System::Int, tail: Link) : Link
  fun depth(): System::Int
    ret 1 + tail.depth()

fun [tail] build(l: Link, n: System::Int): Link
  ret n <= 0 ? l : build(Cons(n, l), n - 1)

fun main(): System::Int
  System::print(System::String(build(End(), 1000).depth()))
  ret 0
"""
        stats = self._check_same(src, 3, expect_frees=False)
        self.assertEqual(stats["pushed"], 0)

    def test_branch_edges_and_lower_levels(self):
        # A loop whose object dies on different branch edges, at every -O
        # level (no inlining at -O1, so the loop is not fused into main).
        src = _COUNTER + """
fun [tail] alternate(c: Counter, n: System::Int, acc: System::Int): System::Int
  ret n <= 0 ? acc : (n % 3 == 0
    ? alternate(c.step().step(), n - 1, acc)
    : alternate(c.step(), n - 1, acc + c.value()))

fun main(): System::Int
  System::print(System::String(alternate(Up(1, 3), 30000, 0)) + " "
                + System::String(drive(Up(0, 1), 30000, 0)))
  ret 0
"""
        for level in (0, 1, 2, 3):
            with self.subTest(level=level):
                self._check_same(src, level, expect_frees=level >= 2)
