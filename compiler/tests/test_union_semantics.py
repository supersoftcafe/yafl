"""Union set semantics (2026-06-11).

`|` builds a flat SET of member types:

1. Nesting is spelling, not structure — `(Word|None)|IOError` IS
   `Word|None|IOError` (exactly what a generic `T|E` produces when T is
   itself a union). Flattening happens once, in type resolution
   (`CombinationSpec._compile`) — never in the constructor, where it would
   also run on representation specs during lowering.

2. A duplicate member is the SAME member — a union is a set, so `Int|Int` is
   `Int` and `(Word|None)|(None|IOError)` is `Word|None|IOError`. Repetition
   carries no meaning: identity (`as_unique_id_str`) and the representation
   (`repr_members`) both fold it to one slot and one tag.

3. Lowering must preserve nominal identity: two same-shaped simple classes
   would flatten to the same structural tuple spec (same unique id, same
   discriminator tag) and become indistinguishable in a union. Such classes
   are excluded from simple-class flattening and stay heap classes
   (`__exclude_union_collisions` in lowering/simple_classes.py).
"""
from __future__ import annotations

import compiler as c
from tests.testutil import BatchedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


class TestUnionSemantics(TestCase):
    def test_nested_union_spellings_are_one_type(self):
        # A value built against the nested spelling flows into the flat
        # spelling with no conversion — they resolve to the same type.
        rc, out = compile_and_run_stdlib_capture("""
import System
import System::IO

class Word(text: String)

fun load(ok: Bool): (Word|None)|IOError
  ret ok ? Word("hi") : None

fun pick(v: Word|None|IOError): System::Int
  ret match(v)
    (w: Word)    => 0
    (n: None)    => 1
    (e: IOError) => 2

fun main(): System::Int
  ret pick(load(true)) == 0 && pick(load(false)) == 1 ? 0 : 9
""", timeout=120)
        self.assertEqual(0, rc)

    def test_generic_union_instantiation_flattens(self):
        # `T|E` with T itself a union — THE case that motivates set
        # semantics. The instantiated `(Word|None)|IOError` must be the
        # same type as `Word|None|IOError`. Flattening here happens during
        # generic substitution (CombinationSpec.search_and_replace).
        rc, out = compile_and_run_stdlib_capture("""
import System
import System::IO

class Word(text: String)

fun wrap<T>(v: T): T|IOError
  ret v

fun pick(v: Word|None|IOError): System::Int
  ret match(v)
    (w: Word)    => 0
    (n: None)    => 1
    (e: IOError) => 2

fun load(ok: Bool): Word|None
  ret ok ? Word("hi") : None

fun main(): System::Int
  ret pick(wrap<Word|None>(load(true))) == 0
      && pick(wrap<Word|None>(load(false))) == 1 ? 0 : 9
""", timeout=120)
        self.assertEqual(0, rc)

    def test_duplicate_union_member_is_one_member(self):
        # `Int|Int` IS `Int` — structurally, not just for dispatch: the repeat
        # folds at flatten, so the declared type is plain Int and the value is
        # directly usable (no match, no boxing, no error). A match would now be
        # rejected exactly as it is for any non-union Int.
        rc, out = compile_and_run_stdlib_capture("""
import System

fun f(ok: System::Bool): System::Int | System::Int
  ret 1

fun main(): System::Int
  ret f(true) - 1
""", timeout=120)
        self.assertEqual(0, rc)

    def test_duplicate_via_nested_spelling_collapses(self):
        # Flattening (Word|None)|(None|IOError) surfaces a duplicate None, which
        # folds: the type IS Word|None|IOError, and a None value flows through.
        rc, out = compile_and_run_stdlib_capture("""
import System
import System::IO

class Word(text: String)

fun f(ok: System::Bool): (Word|None)|(None|IOError)
  ret None

fun pick(v: Word|None|IOError): System::Int
  ret match(v)
    (w: Word)    => 0
    (n: None)    => 1
    (e: IOError) => 2

fun main(): System::Int
  ret pick(f(true)) == 1 ? 0 : 9
""", timeout=120)
        self.assertEqual(0, rc)

    def test_same_shape_classes_keep_nominal_identity(self):
        # Cat and Dog have identical field shapes; in a union they must
        # remain distinguishable (they stay heap classes rather than both
        # flattening to the same structural tuple).
        rc, out = compile_and_run_stdlib_capture("""
import System

class Cat(name: String)
class Dog(name: String)

fun pick(n: Int): Cat|Dog|None
  ret n == 0 ? Cat("c") : n == 1 ? Dog("d") : None

fun classify(x: Cat|Dog|None): System::Int
  ret match(x)
    (c: Cat)  => 0
    (d: Dog)  => 1
    (n: None) => 2

fun main(): System::Int
  ret classify(pick(0)) == 0 && classify(pick(1)) == 1 && classify(pick(2)) == 2
    ? 0 : 9
""", timeout=120)
        self.assertEqual(0, rc)

    def test_early_return_widens_to_block_union(self):
        # An early `ret` of a NARROW value (a single member, and a subset
        # union) flowing into a wider block result union must widen exactly
        # like the trailing fall-through value and the match arms do. A
        # `return` is not special: A|B|C accepts A, and accepts A|C.
        rc, out = compile_and_run_stdlib_capture("""
import System
import System::IO

class Word(text: String)

fun choose(n: System::Int): Word|None|IOError
  if n == 0
    ret Word("hi")             # single member widened at an early ret
  if n == 1
    let sub: Word|None = None
    ret sub                    # subset union widened at an early ret
  ret EOFError(0)              # trailing value (already coerced)

fun pick(v: Word|None|IOError): System::Int
  ret match(v)
    (w: Word)    => 0
    (n: None)    => 1
    (e: IOError) => 2

fun main(): System::Int
  ret pick(choose(0)) == 0 && pick(choose(1)) == 1 && pick(choose(2)) == 2
    ? 0 : 9
""", timeout=120)
        self.assertEqual(0, rc)
