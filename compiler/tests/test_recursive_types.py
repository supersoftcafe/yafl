"""Regressions found by examples/yspell (2026-06-11).

1. Recursive `class` types (fields referencing the class itself, directly or
   mutually) sent the simple-class flattening fixpoint into infinite expansion
   (RecursionError at -O0, unbounded memory at -O2). Such classes must stay
   ordinary heap classes.

2. Nested unions must flatten: `(Word|None)|IOError` IS `Word|None|IOError` —
   exactly what a generic `T|E` produces when T is itself a union — and a
   match over the flat variant set must be accepted as exhaustive.

3. A match arm whose every path transfers control away (e.g. a [tail] `recur`
   on every path of a nested match) contributes no value; the join must not
   grow a Phi-less predecessor edge (SSAValidationError).
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


class TestRecursiveTypes(TestCase):
    def test_recursive_class_compiles_and_runs(self):
        # Previously diverged in simple_classes' nested-field fixpoint.
        rc, out = compile_and_run_stdlib_capture("""
import System

class Word(text: String, left: Word|None, right: Word|None)

fun [tail] hasWord(t: Word|None, w: String): Bool
  ret match(t)
    (n: Word) =>
        compare(w, n.text) == 0 ? true
          : compare(w, n.text) < 0 ? hasWord(n.left, w) : hasWord(n.right, w)
    (e: None) => false

fun main(): System::Int
  let t = Word("m", Word("a", None, None), Word("z", None, None))
  ret hasWord(t, "a") && hasWord(t, "z") && hasWord(t, "m")
    ? (hasWord(t, "q") ? 1 : 0)
    : 1
""", timeout=120)
        self.assertEqual(0, rc)

    def test_mutually_recursive_classes_compile(self):
        rc, out = compile_and_run_stdlib_capture("""
import System

class Ping(other: Pong|None)
class Pong(other: Ping|None)

fun main(): System::Int
  let a = Ping(Pong(None))
  ret 0
""", timeout=120)
        self.assertEqual(0, rc)

    def test_nested_union_flattens_for_match(self):
        # (Word|None)|IOError must behave as Word|None|IOError.
        rc, out = compile_and_run_stdlib_capture("""
import System
import System::IO

class Word(text: String)

fun load(ok: Bool): (Word|None)|IOError
  ret ok ? Word("hi") : None

fun pick(v: (Word|None)|IOError): System::Int
  ret match(v)
    (w: Word)    => 0
    (n: None)    => 1
    (e: IOError) => 2

fun main(): System::Int
  ret pick(load(true)) == 0 && pick(load(false)) == 1 ? 0 : 9
""", timeout=120)
        self.assertEqual(0, rc)

    def test_all_arms_recur_in_nested_match(self):
        # Inner match whose every arm tail-recurs: the unreachable join must
        # not create a Phi-less predecessor edge into the outer join.
        rc, out = compile_and_run_stdlib_capture("""
import System

fun [tail] countDown(a: List<String>, b: List<String>, n: Int): Int
  ret match(head<String>(a))
    (x: String) =>
        match(head<String>(b))
          (y: String) => countDown(tail<String>(a), b, n + 1)
          (e: None)   => countDown(tail<String>(a), b, n + 1)
    (e: None) => n

fun main(): System::Int
  let l = prepend<String>("a", prepend<String>("b", List<String>()))
  ret countDown(l, l, 0) == 2 ? 0 : 1
""", timeout=120)
        self.assertEqual(0, rc)
