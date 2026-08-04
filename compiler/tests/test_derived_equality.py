"""Derived `BasicEquality` for enums and tuples — see docs/derived-equality-plan.md.

Two properties, in order of how they land:

  * an UNDISCHARGED trait constraint is a compile error at the use site, not a
    ValueError out of codegen (the recorded open bug);
  * a tuple or enum used as a `Dict`/`memoize` key gets its `==`/`hashOf`
    synthesised, so it just works.

The second is the point of the exercise: every pass that needs a compound key
today hand-builds a string fingerprint instead, and those fingerprints are
lossy.
"""
from __future__ import annotations

import unittest

import compiler as c
from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


def _errors(content: str) -> tuple[str, str]:
    """(emitted, diagnostics). `compile` PRINTS diagnostics and returns an
    empty string when it refuses, so the message has to be captured. A crash
    here is a failure of the test's premise: an undischarged constraint must be
    reported, not raised out of codegen."""
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        out = c.compile([c.Input(content, "file.yafl")], use_stdlib=True,
                        just_testing=False, optimization_level=0)
    return (out or ""), buf.getvalue()


_TUPLE_KEY = """\
import System

fun main(): System::Int
  let d = System::Dict<(:System::Int, :System::Int), System::Int>()
  let d2 = System::put(d, (1, 2), 7)
  ret match(System::get(d2, (1, 2)))
    (v: System::Int) => v
    ()               => 0
"""


class TestUndischargedIsADiagnostic(TestCase):
    """A constraint with no instance and no derivation must name itself at the
    use site. Before this, it reached codegen and died with
    `Reference to ResolvedScope.TRAIT ... not implemented yet`."""

    def test_function_component_cannot_derive_and_says_so(self):
        # A function type has no equality and never will, so this stays a clean
        # error even once derivation lands.
        src = """\
import System

fun main(): System::Int
  let d = System::Dict<(:(:System::Int): System::Int, :System::Int), System::Int>()
  # the constraint is only DEMANDED by a keyed operation, not by construction
  let d2 = System::put(d, ((x: System::Int) => x, 1), 5)
  ret 0
"""
        emitted, diagnostics = _errors(src)
        self.assertEqual("", emitted, "expected the compile to be refused")
        self.assertIn("BasicEquality", diagnostics, diagnostics)


# NOT YET IMPLEMENTED — see docs/derived-equality-plan.md. These describe the
# target behaviour and are expected failures until phase 1 lands (the blocker
# is that monomorphisation never instantiates a generic instance whose pattern
# is a tuple). Delete the decorators as each starts passing.
class TestDerivedForCompoundKeys(TestCase):
    def test_tuple_is_usable_as_a_dict_key(self):
        code, out = compile_and_run_stdlib_capture(_TUPLE_KEY, timeout=30)
        self.assertEqual(7, code, out)

    def test_tuple_keys_distinguish_their_components(self):
        """Guards against a derived hash/eq that ignores a field — the exact
        failure mode of the hand-written fingerprints this replaces."""
        src = """\
import System

fun main(): System::Int
  let d0 = System::Dict<(:System::Int, :System::Int), System::Int>()
  let d1 = System::put(d0, (1, 2), 10)
  let d2 = System::put(d1, (2, 1), 20)
  let a = match(System::get(d2, (1, 2)))
    (v: System::Int) => v
    ()               => 0
  let b = match(System::get(d2, (2, 1)))
    (v: System::Int) => v
    ()               => 0
  println(a + b * 100)
  ret 0
"""
        # via println, not the exit status: an exit code is 8-bit and 2010
        # comes back as 218.
        code, out = compile_and_run_stdlib_capture(src, timeout=30)
        self.assertEqual(0, code, out)
        self.assertEqual("2010", out.strip())   # a=10, b=20

    @unittest.expectedFailure
    def test_enum_is_usable_as_a_dict_key(self):
        src = """\
import System

enum Colour
  enum Red()
  enum Green(shade: System::Int)

fun main(): System::Int
  let d0 = System::Dict<Colour, System::Int>()
  let d1 = System::put(d0, Red(), 3)
  let d2 = System::put(d1, Green(7), 4)
  let a = match(System::get(d2, Red()))
    (v: System::Int) => v
    ()               => 0
  let b = match(System::get(d2, Green(7)))
    (v: System::Int) => v
    ()               => 0
  let c = match(System::get(d2, Green(8)))
    (v: System::Int) => v
    ()               => 0
  ret a + b * 10 + c * 100
"""
        code, out = compile_and_run_stdlib_capture(src, timeout=30)
        self.assertEqual(43, code, out)   # a=3, b=4, Green(8) absent

    @unittest.expectedFailure
    def test_recursive_enum_key(self):
        """Needs the recursive instance (phase 2): the derived `==` for a list
        refers to itself for the tail."""
        src = """\
import System

enum Chain2
  enum Nil2()
  enum Cons2(hd: System::Int, tl: Chain2)

fun main(): System::Int
  let d0 = System::Dict<Chain2, System::Int>()
  let d1 = System::put(d0, Cons2(1, Cons2(2, Nil2())), 5)
  ret match(System::get(d1, Cons2(1, Cons2(2, Nil2()))))
    (v: System::Int) => v
    ()               => 0
"""
        code, out = compile_and_run_stdlib_capture(src, timeout=30)
        self.assertEqual(5, code, out)


class TestRecursionCapabilities(TestCase):
    """Phase 2 of the plan turned out to need NO implementation — both of these
    already work. They were untested, so they are pinned here: the derived-
    equality design leans on both, and a regression would be silent."""

    def test_lazy_let_may_reference_itself(self):
        """The enabling rule for a recursive instance: a `[lazy]` let may
        reference itself directly. A lazy expression can cycle; a strict one
        cannot, and rejecting THAT is a separate check, deliberately deferred."""
        src = """\
import System

fun main(): System::Int
  let [lazy] f: (:System::Int): System::Int =
    (n: System::Int) => n <= 0 ? 0 : n + f(n - 1)
  ret f(3)
"""
        code, out = compile_and_run_stdlib_capture(src, timeout=30)
        self.assertEqual(6, code, out)   # 3+2+1+0

    def test_recursive_instance_on_a_recursive_enum(self):
        """An instance whose members call back into the instance being defined,
        for a type that contains itself. The cycle is in the INSTANCE — a
        dictionary of functions — while the values it walks stay acyclic, so
        neither `==` nor `hashOf` diverges."""
        src = """\
import System

enum Chain2
  enum Nil2()
  enum Cons2(hd: System::Int, tl: Chain2)

instance [ambient] System::BasicEquality<Chain2>
  fun `==`(l: Chain2, r: Chain2): System::Bool
    ret match(l)
      (a: Cons2) => match(r)
        (b: Cons2) => a.hd == b.hd && a.tl == b.tl
        ()         => false
      ()         => match(r)
        (b2: Cons2) => false
        ()          => true
  fun hashOf(v: Chain2): System::Int32
    ret match(v)
      (c: Cons2) => (hashOf(c.hd) * 31i32 + hashOf(c.tl)) & 2147483647i32
      ()         => 17i32

fun main(): System::Int
  let d0 = System::Dict<Chain2, System::Int>()
  let d1 = System::put(d0, Cons2(1, Cons2(2, Nil2())), 5)
  ret match(System::get(d1, Cons2(1, Cons2(2, Nil2()))))
    (v: System::Int) => v
    ()               => 0
"""
        code, out = compile_and_run_stdlib_capture(src, timeout=30)
        self.assertEqual(5, code, out)
