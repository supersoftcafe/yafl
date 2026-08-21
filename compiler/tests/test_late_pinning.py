"""Late pinning: publication into a PROMOTED memoize cache stays traced.

[pinnable] replaced [mutable] on the memoize trie (stdlib/memoize.yafl): the
nodes are ordinary immutable objects again, so their pages age into the old
generation — and a publication landing AFTER that installs a young reference
on a page minor cycles skip. Two mechanisms keep that sound, and this file is
the suite's regression net over both:

  * the runtime half — gc_note_late_write's Dekker handshake with the
    promotion decision (yafllib has the deterministic window test,
    test_gc_late_pin_race; here the whole stack runs end-to-end);
  * the compiler half — lowering/pinnable_reads wraps reads of a [pinnable]
    object's fields in object_resolve, so a stale pre-relocation pointer
    cannot read pre-write bytes.

The run test is bench/memo_promote.yafl scaled to suite size: a 64m heap
makes the promotion volume ~2 MiB, so a couple of hundred thousand dropped
allocations age the cache in well under a second. Phases: fill, settle until
the cache promotes, insert a second disjoint range (the writes that land on
OLD pages), settle again, then read BOTH ranges back against the function.
YAFL_GC_POISON turns a silent use-after-free into a loud abort.
"""
from __future__ import annotations

import compiler as c
from tests.testutil import BatchedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture

_PROMOTE = """\
namespace Promote

import System

fun payload(k: System::Int): System::Int
  let a = (k * 2654435761) % 1000000007
  ret (a + k * 40503) % 1000000007

let keys:    System::Int = 4000
let settle:  System::Int = 250000
let modulus: System::Int = 1000000007

# Allocation with no insertion: drives collection cycles so the cache ages.
fun cell(k: System::Int): System::Int
  let c = prepend<System::Int>(k, prepend<System::Int>(k + 1, List<System::Int>()))
  ret match(head<System::Int>(c))
    (v: System::Int)  => v
    (e: System::None) => 0

fun settleFor(rounds: System::Int): System::Int
  fun [tail] loop(i: System::Int, acc: System::Int): System::Int
    ret i >= rounds ? acc : loop(i + 1, (acc + cell(i)) % modulus)
  ret loop(0, 0)

fun fillRange(memo: (:System::Int): System::Int, from: System::Int,
              upto: System::Int): System::Int
  fun [tail] loop(i: System::Int, acc: System::Int): System::Int
    ret i >= upto ? acc : loop(i + 1, (acc + memo(i)) % modulus)
  ret loop(from, 0)

fun verifyRange(memo: (:System::Int): System::Int, from: System::Int,
                upto: System::Int): System::Int
  fun [tail] loop(i: System::Int, bad: System::Int): System::Int
    ret i >= upto
      ? bad
      : loop(i + 1, memo(i) == payload(i) ? bad : bad + 1)
  ret loop(from, 0)

fun main(): System::Int
  let memo = memoize<System::Int, System::Int>(payload)
  let phase1 = fillRange(memo, 0, keys)
  let phase2 = settleFor(settle)
  let phase3 = fillRange(memo, keys, keys * 2)
  let phase4 = settleFor(settle)
  let bad = verifyRange(memo, 0, keys) + verifyRange(memo, keys, keys * 2)
  println("wrong " + String(bad) + " mix "
          + String((phase1 + phase2 + phase3 + phase4) % modulus))
  ret bad == 0 ? 0 : 1
"""


class TestLatePinning(TestCase):
    _TIMEOUT = 300

    def test_promoted_cache_publication_survives(self):
        rc, out = compile_and_run_stdlib_capture(
            _PROMOTE, timeout=120, optimization_level=1,
            env={"YAFL_HEAP_SIZE": "64m", "YAFL_GC_POISON": "1"})
        self.assertEqual(rc, 0, f"memo_promote run failed:\n{out}")
        self.assertIn("wrong 0 ", out)

    def test_resolve_barrier_emitted_exactly_for_pinnable(self):
        # The pass is keyed on the object registry, so a program that
        # monomorphises the [pinnable] trie must read through object_resolve
        # — and one with no pinnable class must not mention it at all.
        with_memo = c.compile([c.Input(_PROMOTE, "file.yafl")], use_stdlib=True,
                              just_testing=False, optimization_level=1)
        self.assertIn("object_resolve(", with_memo)
        plain = """\
import System

fun main(): System::Int
  ret match(head<System::Int>(prepend<System::Int>(3, List<System::Int>())))
    (v: System::Int)  => v - 3
    (e: System::None) => 1
"""
        without = c.compile([c.Input(plain, "file.yafl")], use_stdlib=True,
                            just_testing=False, optimization_level=1)
        self.assertNotIn("object_resolve(", without)
