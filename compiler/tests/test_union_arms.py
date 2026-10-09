"""Union-typed match arms (2026-06-11).

A match arm may itself be typed as a union, narrowing the subject to a
subset of its members: `match x (w: Word|None) => ... (e: IOError) => ...`
over `Word|None|IOError`. This is strictly correct code — exactly what a
generic `T|E` produces when T is itself a union — and must both compile
and dispatch correctly at runtime.

Previously both match generators mishandled these arms: the pointer
generator silently dropped them, and the tagged generator looked up a
discriminator for the union type itself (absent — discriminator ids are
global per LEAF type) so every member tested against tag 0 and the match
aborted at runtime.

The narrowed value bound by the arm must be usable: for a pointer-shaped
narrow union it is the subject pointer (NULL for the unit member); for a
struct-shaped narrow union it is rebuilt from the wide slots with the
member's global tag carried over unchanged.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


class TestUnionTypedArms(TestCase):
    def test_union_arm_dispatches_both_members(self):
        # The reported idiom, verbatim shape: both members of the
        # `(w: Word|None)` arm must route to it, and the bound variable
        # must carry the correctly narrowed value into a nested match.
        rc, out = compile_and_run_stdlib_capture("""
import System
import System::IO

class Word(text: String)

fun readWord(ok: Bool): (Word|None)|IOError
  ret ok ? Word("hi") : None

fun nameOf(v: Word|None): String
  ret match(v)
    (w: Word) => w.text
    (n: None) => "none"

fun classify(x: (Word|None)|IOError): String
  ret match(x)
    (w: Word|None) => nameOf(w)
    (e: IOError)   => "err"

fun main(): System::Int
  ret compare(classify(readWord(true)), "hi") == 0
      && compare(classify(readWord(false)), "none") == 0 ? 0 : 9
""", timeout=120)
        self.assertEqual(0, rc)

    def test_union_arm_pointer_narrow(self):
        # All-class union: pointer-distinguishable subject, pointer-shaped
        # narrow arm. The bound value is the subject pointer; a rematch on
        # it must still discriminate the members.
        rc, out = compile_and_run_stdlib_capture("""
import System

class Cat(name: String)
class Dog(name: String)

fun pick(n: Int): Cat|Dog|None
  ret n == 0 ? Cat("c") : n == 1 ? Dog("d") : None

fun classify(x: Cat|Dog|None): System::Int
  ret match(x)
    (p: Cat|Dog) =>
        match(p)
          (c: Cat) => 1
          (d: Dog) => 2
    (n: None) => 0

fun main(): System::Int
  ret classify(pick(0)) == 1 && classify(pick(1)) == 2 && classify(pick(2)) == 0
    ? 0 : 9
""", timeout=120)
        self.assertEqual(0, rc)

    def test_union_arm_tagged_narrow(self):
        # Bool forces a tagged-struct representation for both the wide
        # union and the narrow arm type: the arm value is REBUILT from the
        # wide slots, and its global tags must survive into a rematch.
        rc, out = compile_and_run_stdlib_capture("""
import System

fun pick(n: Int): Bool|String|None
  ret n == 0 ? "yes" : n == 1 ? true : None

fun classify(x: Bool|String|None): System::Int
  ret match(x)
    (v: Bool|String) =>
        match(v)
          (b: Bool)   => 1
          (s: String) => 2
    (n: None) => 0

fun main(): System::Int
  ret classify(pick(0)) == 2 && classify(pick(1)) == 1 && classify(pick(2)) == 0
    ? 0 : 9
""", timeout=120)
        self.assertEqual(0, rc)
