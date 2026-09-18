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
from tests.testutil import TimedTestCase
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

    def test_disagreeing_call_uses_generalise_to_the_root(self):
        # Used as a Circle and as a Square: x is a Shape (user ruling 09-16),
        # so each call then rejects it — the error is at the calls.
        errs = _errors(_SHAPES + "fun ring(c: Circle): System::Int\n  ret c.r\n"
                       "fun side(q: Square): System::Int\n  ret q.s\n"
                       "fun both(x): System::Int\n  ret ring(x) + side(x)\n"
                       "fun main(): System::Int\n  ret both(Circle(1))\n")
        self.assertIn("Parameters are not assignment compatible", errs)
        self.assertNotIn("could not be inferred", errs)

    def test_unrelated_call_uses_are_an_error(self):
        errs = _errors(_SHAPES + "fun ring(c: Circle): System::Int\n  ret c.r\n"
                       "fun heavy(r: Rock): System::Int\n  ret r.weight()\n"
                       "fun both(x): System::Int\n  ret ring(x) + heavy(x)\n"
                       "fun main(): System::Int\n  ret both(Circle(1))\n")
        self.assertIn("'x'", errs)
        self.assertIn("could not be inferred", errs)

    def test_trait_operators_take_the_expected_type(self):
        # `&` pins on mask32, `+` then pins on `&`'s Int, and a, b take it.
        rc, _out = compile_and_run_stdlib_capture(
            "namespace Test\nimport System\n"
            "let mask32 = 4294967295\n"
            "fun add32(a, b)\n  ret (a + b) & mask32\n"
            "fun rotl32(x, c)\n  ret ((x << c) | (x >> (32 - c))) & mask32\n"
            "fun main(): System::Int\n  ret add32(1, rotl32(2, 3))\n", timeout=120)
        self.assertEqual(17, rc)

    def test_declared_result_pins_a_trait_operator(self):
        rc, _out = compile_and_run_stdlib_capture(
            "namespace Test\nimport System\n"
            "fun addr(a, b): System::Int\n  ret a + b\n"
            "fun main(): System::Int\n  ret addr(3, 4)\n", timeout=120)
        self.assertEqual(7, rc)

    def test_lambda_parameter_infers_from_its_body(self):
        rc, _out = compile_and_run_stdlib_capture(
            "namespace Test\nimport System\n"
            "fun main(): System::Int\n"
            "  let triple = (x) => 3 * x\n"
            "  ret triple(14)\n", timeout=120)
        self.assertEqual(42, rc)

    def test_a_late_pinning_call_still_informs(self):
        # `3 * a` makes a an Int; only then does `both` pin, and b takes
        # the String its second parameter expects.
        rc, _out = compile_and_run_stdlib_capture(
            "namespace Test\nimport System\n"
            "fun both(n: System::Int, s: System::String): System::Int\n"
            "  ret n + length(s)\n"
            "fun both(n: System::Int32, s: System::Int32): System::Int\n"
            "  ret 1\n"
            "fun late(a, b): System::Int\n  ret both(a, b) + 3 * a\n"
            "fun main(): System::Int\n  ret late(2, \"abc\")\n", timeout=120)
        self.assertEqual(11, rc)

    def test_ternary_branches_converge_on_the_root(self):
        # Circle and Square branches give Shape, so the Tri arm is reachable.
        rc, _out = compile_and_run_stdlib_capture(
            _SHAPES + "fun pick(flag: System::Bool)\n"
            "  ret flag ? Circle(1) : Square(2)\n"
            "fun main(): System::Int\n"
            "  ret match(pick(false))\n"
            "    (c: Circle) => c.r\n"
            "    (q: Square) => q.s\n"
            "    (t: Tri)    => t.t\n", timeout=120)
        self.assertEqual(2, rc)

    def test_match_branches_converge_on_the_root(self):
        rc, _out = compile_and_run_stdlib_capture(
            _SHAPES + "fun pick(n: System::Int)\n"
            "  ret match(n)\n"
            "    (0) => Circle(1)\n"
            "    ()  => Square(2)\n"
            "fun main(): System::Int\n"
            "  ret match(pick(0))\n"
            "    (c: Circle) => c.r\n"
            "    (q: Square) => q.s\n"
            "    (t: Tri)    => t.t\n", timeout=120)
        self.assertEqual(1, rc)

    def test_branches_with_no_common_parent_are_the_union(self):
        rc, _out = compile_and_run_stdlib_capture(
            "namespace Test\nimport System\n"
            "fun maybe(flag: System::Bool)\n  ret flag ? 5 : None\n"
            "fun main(): System::Int\n"
            "  ret match(maybe(true))\n"
            "    (n: System::Int) => n\n"
            "    (z: System::None) => 0\n", timeout=120)
        self.assertEqual(5, rc)

    def test_an_unresolved_operator_does_not_latch_a_wider_type(self):
        # `+` resolves passes after `ret` says Int|None; i must still be Int.
        rc, _out = compile_and_run_stdlib_capture(
            "namespace Test\nimport System\n"
            "fun [tail] idxLoop(es: List<String>, name: String, i): Int|None\n"
            "  ret match(head(es))\n"
            "    (s: String) => s == name ? i : idxLoop(drop(es, 1), name, i + 1)\n"
            "    ()          => None\n"
            "fun main(): System::Int\n"
            "  let words: List<String> = prepend(\"a\", prepend(\"bcd\", List()))\n"
            "  ret idxLoop(words, \"bcd\", 0) ?? 99\n", timeout=120)
        self.assertEqual(1, rc)

    def test_a_lambda_argument_takes_the_expected_signature(self):
        # The body alone says String|None for sp; map's signature says String.
        rc, _out = compile_and_run_stdlib_capture(
            "namespace Test\nimport System\n"
            "fun label(s: String|None): Int\n"
            "  ret match(s)\n"
            "    (x: String) => length(x)\n"
            "    ()          => 0\n"
            "fun main(): System::Int\n"
            "  let words: List<String> = prepend(\"ab\", List())\n"
            "  ret fold(map(words, (sp) => label(sp)), 0, (acc, n) => acc + n)\n", timeout=120)
        self.assertEqual(2, rc)

    def test_a_lambda_body_does_not_bind_its_callees_type_parameter(self):
        # area(c) wants a Shape, but map's T comes from the List<Circle>.
        rc, _out = compile_and_run_stdlib_capture(
            _SHAPES + "fun area(sh: Shape): System::Int\n"
            "  ret match(sh)\n"
            "    (c: Circle) => c.r * c.r\n"
            "    (q: Square) => q.s * q.s\n"
            "    (t: Tri)    => t.t\n"
            "fun total(circles: List<Circle>): System::Int\n"
            "  ret fold(map(circles, (c) => area(c)), 0, (acc, n) => acc + n)\n"
            "fun main(): System::Int\n"
            "  let cs: List<Circle> = prepend(Circle(2), prepend(Circle(3), List()))\n"
            "  ret total(cs)\n", timeout=120)
        self.assertEqual(13, rc)

    def test_an_uninferable_return_type_is_an_error(self):
        # Recursion with no base case gives the body nothing to type.
        errs = _errors("namespace Test\nimport System\n"
                       "fun spin(n: System::Int) => spin(n - 1)\n"
                       "fun outer(n: System::Int): System::Int\n"
                       "  fun inner(k: System::Int) => inner(k + 1)\n"
                       "  ret n\n"
                       "fun fine(n: System::Int) => n + 1\n"
                       "fun main(): System::Int\n  ret fine(0)\n")
        self.assertIn("Return type of 'spin' could not be inferred", errs)
        self.assertIn("Return type of 'inner' could not be inferred", errs)
        self.assertNotIn("'fine'", errs)

    def test_an_uninferable_nested_parameter_is_an_error(self):
        errs = _errors("namespace Test\nimport System\n"
                       "fun outer(n: System::Int): System::Int\n"
                       "  fun inner(k): System::Int\n"
                       "    ret 0\n"
                       "  ret inner(n)\n"
                       "fun main(): System::Int\n  ret outer(1)\n")
        self.assertIn("Parameter 'k' of 'inner' has no type and could not be inferred", errs)

    def test_a_generic_slot_does_not_leak_its_placeholder(self):
        errs = _errors("namespace Test\nimport System\n"
                       "fun ident<T>(v: T): T\n  ret v\n"
                       "fun viaGeneric(x)\n  ret ident(x)\n"
                       "fun main(): System::Int\n  ret 0\n")
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


class TestHintLocality(TimedTestCase):
    def test_a_converted_use_keeps_its_hint(self):
        # `take(v)` wraps v in a conversion once v is an Int; the use still
        # expects Int|None, and the body must still say so.
        from parsing.tokenizer import tokenize
        from parsing.parser import parse
        import pyast.statement as s
        import pyast.expression as e
        from tests.testutil import stdlib_files
        src = ("namespace Test\nimport System\n"
               "fun take(x: System::Int|None): System::Int\n  ret 0\n"
               "fun twice(n: System::Int): System::Int\n  ret n\n"
               "fun use(v): System::Int\n  ret take(v) + twice(v)\n")
        text = "".join(p.read_text() for p in stdlib_files()) + src
        statements, resolver, _ = c.__dict__["__converge"](parse(tokenize(text, "x")).value)
        use = next(st for st in statements
                   if isinstance(st, s.FunctionStatement) and "::use@" in st.name)
        found = []
        def visit(_, thing):
            if isinstance(thing, e.ConvertExpression):
                found.append(thing)
            return thing
        use.body.search_and_replace(None, visit)
        self.assertTrue(found, "the argument to take() should be converted")
        scope = use.body_scope(c.__dict__["__stmt_scope_resolver"](use, resolver))
        hints = use.body.compile(scope, use.return_type)[2]
        v = use.parameters.targets[0].name
        shown = sorted(str(hint.spec.as_unique_id_str()) for hint in hints.get(v, ()))
        self.assertEqual(2, len(shown), shown)
