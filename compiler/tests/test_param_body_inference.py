"""Function PARAMETER types inferred from the BODY, never from the callers.

The implementer's "it's obvious, I shouldn't have to write it again": a
parameter's type comes from what the body DOES with it. Every use contributes
evidence, in one of two directions:

  * UPPER bounds — "x must fit here": x passed where a type is declared, or
    `ret x` against a declared return type.
  * LOWER bounds — "x must accept these": the arm types of `match(x)`.

The type is the generalisation of the lower bounds, checked against the upper
bounds. Variants of one enum generalise to the ROOT enum and classes to the
interface they share (deliberately unlike `join` for branch results, which is
set semantics) — a programmer who disagrees writes the type out.

Candidates come from overload resolution, which is ASSIGNABILITY of the call
shape with holes, never arity: `3 * x` filters the `*` overloads by the known
first argument, one survives, and x is read off its second parameter.

Several surviving candidates, or no use that determines the parameter at all,
are the SAME diagnostic: an ambiguity naming what was found.
"""
from __future__ import annotations

import contextlib
import io

import compiler as c
from tests.testutil import BatchedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


def _errors(src: str) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        c.compile([c.Input(src, "test.yafl")], use_stdlib=True, just_testing=True)
    return buf.getvalue()


_SHAPES = """
namespace Test
import System

enum Shape
  enum Circle(r: System::Int)
  enum Square(s: System::Int)
  enum Tri(t: System::Int)

interface Legged
  fun legs(): System::Int

class [final] Dog() : Legged
  fun legs(): System::Int
    ret 4

class [final] Cat() : Legged
  fun legs(): System::Int
    ret 4

class [final] Rock()
  fun weight(): System::Int
    ret 1

class [final] Tree()
  fun weight(): System::Int
    ret 2
"""


class TestParamBodyInference(TestCase):
    def test_arithmetic_pins_the_parameter(self):
        # Only one `*` takes Int first, so x is read off its second parameter.
        rc, _out = compile_and_run_stdlib_capture(
            "namespace Test\nimport System\n"
            "fun triple(x): System::Int\n  ret 3 * x\n"
            "fun main(): System::Int\n  ret triple(14)\n", timeout=120)
        self.assertEqual(42, rc)

    def test_match_arms_give_the_root_enum(self):
        # Lower bounds Circle and Square generalise to the ROOT, so a Tri is
        # accepted too — the parameter is Shape, not Shape{Circle, Square}.
        rc, _out = compile_and_run_stdlib_capture(
            _SHAPES + "fun sides(s): System::Int\n"
            "  ret match(s)\n"
            "    (c: Circle) => 1\n"
            "    (q: Square) => 4\n"
            "    (t: Tri)    => 3\n"
            "fun main(): System::Int\n  ret sides(Tri(9)) + sides(Circle(1))\n", timeout=120)
        self.assertEqual(4, rc)

    def test_two_classes_give_their_shared_interface(self):
        # Classes may only inherit from pure interfaces, so the "common base"
        # two classes can share IS an interface: Dog and Cat give Legged, NOT
        # the union `Dog|Cat`. The consequence is visible right here — a
        # class-typed subject cannot be matched, so this program is rejected
        # for its match, not for an uninferable parameter. An author who meant
        # the union says so, which is exactly the rule: declare it if you
        # disagree.
        errs = _errors(_SHAPES + "fun legsOf(a): System::Int\n"
                       "  ret match(a)\n"
                       "    (d: Dog) => d.legs()\n"
                       "    (k: Cat) => k.legs()\n"
                       "fun main(): System::Int\n  ret legsOf(Dog())\n")
        self.assertIn("match subject must be a union type", errs)
        self.assertNotIn("could not be inferred", errs)

    def test_two_classes_sharing_no_interface_are_ambiguous(self):
        errs = _errors(_SHAPES + "fun weigh(a): System::Int\n"
                       "  ret match(a)\n"
                       "    (r: Rock) => r.weight()\n"
                       "    (t: Tree) => t.weight()\n"
                       "fun main(): System::Int\n  ret weigh(Rock())\n")
        self.assertIn("'a'", errs)
        self.assertIn("could not be inferred", errs)

    def test_return_type_pins_the_parameter(self):
        rc, _out = compile_and_run_stdlib_capture(
            "namespace Test\nimport System\n"
            "fun echo(x): System::Int\n  ret x\n"
            "fun main(): System::Int\n  ret echo(7)\n", timeout=120)
        self.assertEqual(7, rc)

    def test_a_uniquely_fitting_call_pins_the_parameter(self):
        rc, _out = compile_and_run_stdlib_capture(
            _SHAPES + "fun ring(c: Circle): System::Int\n  ret c.r\n"
            "fun viaCall(x): System::Int\n  ret ring(x)\n"
            "fun main(): System::Int\n  ret viaCall(Circle(5))\n", timeout=120)
        self.assertEqual(5, rc)

    def test_a_named_argument_finds_its_own_slot(self):
        # `second = x` binds by NAME, so x is a Square. Reading the callee's
        # parameter at the ARGUMENT's index would have called it a Circle.
        rc, _out = compile_and_run_stdlib_capture(
            _SHAPES + "fun pair(first: Circle, second: Square): System::Int\n"
            "  ret first.r + second.s\n"
            "fun viaNamed(x): System::Int\n"
            "  ret pair(second = x, first = Circle(1))\n"
            "fun main(): System::Int\n  ret viaNamed(Square(6))\n", timeout=120)
        self.assertEqual(7, rc)

    def test_an_else_arm_stops_the_match_determining_it(self):
        # The else arm proves there is a member the named arms do not cover,
        # and which one is written nowhere — so `Shape` is NOT the answer here.
        # Inferring it from the named arms alone would then reject the author's
        # own else arm as unreachable, which is how `X|None` parameters break.
        errs = _errors(_SHAPES + "fun describe(o): System::Int\n"
                       "  ret match(o)\n"
                       "    (c: Circle) => 1\n"
                       "    ()          => 0\n"
                       "fun main(): System::Int\n  ret describe(Circle(1))\n")
        self.assertIn("'o'", errs)
        self.assertIn("could not be inferred", errs)

    def test_bare_generic_enum_arms_do_not_determine_it(self):
        # `(l: ChainLink)` carries no type argument: arms receive the subject's
        # only once the subject's type is known, which is what is being
        # inferred here. Generalising bare arms would yield a bare `Chain`,
        # which monomorphisation cannot specialise — codegen then looks up a
        # root that no longer exists and crashes with no source location.
        errs = _errors("namespace Test\nimport System\n"
                       "fun walk(c): System::Int\n"
                       "  ret match(c)\n"
                       "    (nil: System::ChainEnd)  => 0\n"
                       "    (l: System::ChainLink)   => 1\n"
                       "fun main(): System::Int\n"
                       "  ret walk(chain(List<System::Int>()))\n")
        self.assertIn("'c'", errs)
        self.assertIn("could not be inferred", errs)

    def test_no_use_determines_it_is_an_error(self):
        errs = _errors("namespace Test\nimport System\n"
                       "fun unused(x): System::Int\n  ret 0\n"
                       "fun main(): System::Int\n  ret unused(1)\n")
        self.assertIn("'x'", errs)
        self.assertIn("could not be inferred", errs)

    def test_contradictory_uses_are_an_error(self):
        errs = _errors(_SHAPES + "fun ring(c: Circle): System::Int\n  ret c.r\n"
                       "fun side(q: Square): System::Int\n  ret q.s\n"
                       "fun both(x): System::Int\n  ret ring(x) + side(x)\n"
                       "fun main(): System::Int\n  ret both(Circle(1))\n")
        self.assertIn("'x'", errs)
        self.assertIn("could not be inferred", errs)

    def test_callable_parameter_needs_one_side_declared(self):
        # The body fixes the parameter tuple but nothing fixes the result:
        # `(:Int): ?` is not a type, so this must be an error.
        errs = _errors("namespace Test\nimport System\n"
                       "fun doSomething(callable)\n  ret callable(3)\n"
                       "fun twice(n: System::Int): System::Int\n  ret n + n\n"
                       "fun main(): System::Int\n  ret doSomething(twice)\n")
        self.assertIn("'callable'", errs)

    def test_callable_parameter_infers_when_the_return_is_declared(self):
        rc, _out = compile_and_run_stdlib_capture(
            "namespace Test\nimport System\n"
            "fun doSomething(callable): System::Int\n  ret callable(3)\n"
            "fun twice(n: System::Int): System::Int\n  ret n + n\n"
            "fun main(): System::Int\n  ret doSomething(twice)\n", timeout=120)
        self.assertEqual(6, rc)

    def test_callers_do_not_supply_parameter_types(self):
        # Callers never supply a parameter's type: a parameter no use inside
        # the body determines is an error however unambiguous the call sites.
        errs = _errors("namespace Test\nimport System\n"
                       "fun addSomeThings(a, b)\n  ret a + b\n"
                       "fun main(): System::Int\n  ret addSomeThings(1, 45)\n")
        self.assertIn("could not be inferred", errs)
