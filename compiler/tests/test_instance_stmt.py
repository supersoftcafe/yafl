"""The `instance` statement: first-class trait instances.

    instance [ambient]<T> Interface<Pattern> where Constraint<T>
      fun member(...): ...

Replaces the witness-class + `let [trait]` two-step (and the `typealias
[where]` ambience twin). Anonymous; desugars during building into a
synthesized witness class + instance record. Semantics (user rulings
2026-07-29):
- ambience is OPT-IN via [ambient]: a plain instance discharges where-clause
  constraints only; an ambient one additionally makes its members callable
  unqualified in importing scopes, WITHOUT constraining anything (an
  ambient where is availability, a fn where is a constraint).
- a GENERIC ambient instance's own type params bind from the use site
  (argument or expected type), like a generic function candidate's own
  params; the instance's own `where` filters candidacy.
- no coherence rule: multiple overlapping instances are legal to declare;
  ambiguity is an error at USE, same as same-signature open functions.
"""
from __future__ import annotations

import contextlib
import io

import compiler as c
from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


def _errors(src: str) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        c.compile([c.Input(src, "test.yafl")], use_stdlib=True, just_testing=True)
    return buf.getvalue()

# Concrete ambient instance: member callable unqualified, no witness class,
# no trait let, no where alias.
_CONCRETE_AMBIENT = """namespace Test
import System

class Point(x: Int, y: Int)

instance [ambient] Show<Point>
  fun show(value: Point): String
    ret format("({1},{2})", value.x, value.y)

fun main(): Int
  ret show(Point(3, 4)) == "(3,4)" ? 0 : 1
"""

# Generic ambient instance: the instance's own T binds from the argument.
_GENERIC_AMBIENT = """namespace Test
import System

interface Sized<T>
  fun sizeOf(v: T): Int

instance [ambient]<T> Sized<List<T>>
  fun sizeOf(v: List<T>): Int
    ret chainLength(chain(v))

fun main(): Int
  let l = prepend(4, prepend(5, List<Int>()))
  ret sizeOf(l) == 2 ? 0 : 1
"""

# Discharge-only (no [ambient]): visible to a fn's where clause, but its
# members are NOT callable unqualified.
_DISCHARGE_ONLY = """namespace Test
import System

interface Tagged<T>
  fun tagOf(v: T): Int

class Box(v: Int)

instance Tagged<Box>
  fun tagOf(v: Box): Int
    ret v.v

fun viaWhere<T>(x: T): Int where Tagged<T>
  ret tagOf(x)

fun main(): Int
  ret viaWhere(Box(9)) == 9 ? 0 : 1
"""

_NOT_AMBIENT_ERR = """namespace Test
import System

interface Tagged<T>
  fun tagOf(v: T): Int

class Box(v: Int)

instance Tagged<Box>
  fun tagOf(v: Box): Int
    ret v.v

fun main(): Int
  ret tagOf(Box(9))
"""

# The instance's own where filters candidacy: List<T> is only Showable
# when T is (Show<T> discharges for the bound T).
_CONSTRAINED_AMBIENT = """namespace Test
import System

instance [ambient]<T> Show<List<T>> where Show<T>
  fun show(value: List<T>): String
    ret fold(value, "", (acc: String, x: T) => acc + show(x))

fun main(): Int
  let l = prepend(1, prepend(2, List<Int>()))
  ret show(l) == "12" ? 0 : 1
"""

# Two instances may both exist; a use only ONE can serve is fine.
# (Ambiguity-at-use is exercised the day resolution can produce it — the
# declaration side must at least not reject the pair.)
_TWO_INSTANCES_OK = """namespace Test
import System

interface Tagged<T>
  fun tagOf(v: T): Int

class Box(v: Int)
class Crate(v: Int)

instance [ambient] Tagged<Box>
  fun tagOf(v: Box): Int
    ret v.v

instance [ambient] Tagged<Crate>
  fun tagOf(v: Crate): Int
    ret 0 - v.v

fun main(): Int
  ret tagOf(Box(5)) == 5 && tagOf(Crate(5)) == 0 - 5 ? 0 : 1
"""


# Ambience applies at CONCRETE use sites only (user ruling): inside a generic
# body a caller placeholder never matches an ambient instance — availability
# there comes solely from the function's own where clause.
_AMBIENT_NOT_FOR_GENERIC = """namespace Test
import System

interface Sized<T>
  fun sizeOf(v: T): Int

instance [ambient]<T> Sized<List<T>>
  fun sizeOf(v: List<T>): Int
    ret chainLength(chain(v))

fun measure<T>(l: List<T>): Int
  ret sizeOf(l)

fun main(): Int
  ret measure(prepend(1, List<Int>()))
"""

_GENERIC_VIA_WHERE = """namespace Test
import System

interface Sized<T>
  fun sizeOf(v: T): Int

instance<T> Sized<List<T>>
  fun sizeOf(v: List<T>): Int
    ret chainLength(chain(v))

fun measure<T>(l: List<T>): Int where Sized<List<T>>
  ret sizeOf(l)

fun main(): Int
  ret measure(prepend(1, List<Int>())) == 1 ? 0 : 1
"""


class TestInstanceStatement(TestCase):
    _TIMEOUT = 600

    def test_concrete_ambient(self):
        code, _out = compile_and_run_stdlib_capture(_CONCRETE_AMBIENT)
        self.assertEqual(code, 0)

    def test_generic_ambient_binds_from_argument(self):
        code, _out = compile_and_run_stdlib_capture(_GENERIC_AMBIENT)
        self.assertEqual(code, 0)

    def test_discharge_only(self):
        code, _out = compile_and_run_stdlib_capture(_DISCHARGE_ONLY)
        self.assertEqual(code, 0)

    def test_non_ambient_member_not_in_scope(self):
        errs = _errors(_NOT_AMBIENT_ERR)
        self.assertIn("tagOf", errs)

    def test_constrained_ambient(self):
        code, _out = compile_and_run_stdlib_capture(_CONSTRAINED_AMBIENT)
        self.assertEqual(code, 0)

    def test_two_instances_distinct_uses(self):
        code, _out = compile_and_run_stdlib_capture(_TWO_INSTANCES_OK)
        self.assertEqual(code, 0)

    def test_ambient_never_serves_a_caller_placeholder(self):
        errs = _errors(_AMBIENT_NOT_FOR_GENERIC)
        self.assertIn("sizeOf", errs)

    # Regression pin: a compound `where Sized<List<T>>` on a user fn used to
    # die at codegen after mono — the demanded constraint arrives with its
    # ENUM inner type mangled (`Sized<List$generic$bigint>`), and
    # __spec_from_mangled only re-inflated ClassSpecs, so unification never
    # bound the instance's T (stream combinators dodged it: their wrapper
    # heads are classes).
    def test_generic_body_uses_its_own_where(self):
        code, _out = compile_and_run_stdlib_capture(_GENERIC_VIA_WHERE)
        self.assertEqual(code, 0)
