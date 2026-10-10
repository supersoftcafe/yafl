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

Runtime behaviour is checked by compiler/yafl_tests/instance_stmt.yafl.
"""
from __future__ import annotations


from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_errors


def _errors(src: str) -> str:
    return compile_errors(src)

# Concrete ambient instance: member callable unqualified, no witness class,
# no trait let, no where alias.

# Generic ambient instance: the instance's own T binds from the argument.

# Discharge-only (no [ambient]): visible to a fn's where clause, but its
# members are NOT callable unqualified.

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

# Two instances may both exist; a use only ONE can serve is fine.
# (Ambiguity-at-use is exercised the day resolution can produce it — the
# declaration side must at least not reject the pair.)


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


class TestInstanceStatement(TestCase):
    _TIMEOUT = 600


    def test_non_ambient_member_not_in_scope(self):
        errs = _errors(_NOT_AMBIENT_ERR)
        self.assertIn("tagOf", errs)


    def test_ambient_never_serves_a_caller_placeholder(self):
        errs = _errors(_AMBIENT_NOT_FOR_GENERIC)
        self.assertIn("sizeOf", errs)

    # Regression pin: a compound `where Sized<List<T>>` on a user fn used to
    # die at codegen after mono — the demanded constraint arrives with its
    # ENUM inner type mangled (`Sized<List$generic$bigint>`), and
    # __spec_from_mangled only re-inflated ClassSpecs, so unification never
    # bound the instance's T (stream combinators dodged it: their wrapper
    # heads are classes).
