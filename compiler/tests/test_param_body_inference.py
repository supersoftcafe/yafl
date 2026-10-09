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

Runtime behaviour is checked by compiler/yafl_tests/param_body_inference.yafl.
"""
from __future__ import annotations


import compiler as c
from tests.testutil import TimedTestCase as TestCase
from tests.testutil import TimedTestCase
from tests.testutil import compile_errors


def _errors(src: str) -> str:
    return compile_errors(src)


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


class TestIncompleteSearchIsUnsettled(TimedTestCase):
    """A name whose lookup is INCOMPLETE says nothing yet — and must say so.

    The fixpoint can make a lookup incomplete for a pass (statements that
    arrive mid-convergence, like a derived instance, leave trait searches
    blocked until they compile). An uncommitted name already reported that
    as UNSETTLED; a committed (`@`-hashed) one reported NO hints at all, so a
    parameter's inference read the pass as complete, dropped the call's
    evidence and latched the one stale hint left (`i` in `i + 1` flipping
    from Int to the unit type, then never recovering)."""

    def test_committed_name_with_incomplete_search_is_unsettled(self):
        import pyast.hints as h
        import pyast.resolver as g
        from parsing.tokenizer import LineRef
        from pyast.expression.access import NamedExpression

        class Blocked(g.Resolver):
            def find_data(self, name):
                return g.INCOMPLETE

        lr = LineRef("x", 0, 0)
        for name in ("plus", "System::`+`@AbCdEf"):
            with self.subTest(name=name):
                _expr, _glb, hints = NamedExpression(lr, name).compile(Blocked(), None)
                self.assertIn(h.UNSETTLED, hints)

    def test_let_does_not_latch_a_partial_branch_while_unsettled(self):
        # `let x = c ? blocked : 5` on a pass where `blocked` cannot be
        # looked up: the branch's type is only the part that resolved (Int).
        # Storing it would latch it — refinement only ever widens — so the
        # let waits, exactly as a parameter does.
        import pyast.expression as e
        import pyast.hints as h
        import pyast.resolver as g
        import pyast.statement as s
        from parsing.tokenizer import LineRef

        class Blocked(g.Resolver):
            def find_data(self, name):
                return g.INCOMPLETE

        lr = LineRef("x", 0, 0)
        rhs = e.TernaryExpression(lr, e.BoolExpression(lr, True),
                                  e.NamedExpression(lr, "System::blocked@AbCdEf"),
                                  e.IntegerExpression(lr, 5))
        let = s.LetStatement(lr, "x@AbCdEf", None, {}, (), rhs, None)
        compiled, _glb, hints = let.compile(Blocked(), None)
        self.assertIn(h.UNSETTLED, hints)
        self.assertIsNone(compiled.declared_type)


class TestVerdictMergesItsBounds(TimedTestCase):
    """A parameter's upper bound RECEIVES its lower bound: the answer is their
    merge (docs/type-merge-design.md). Matching `ss` on `ListEmpty` /
    `ListFull` bounds it below by List spelled WITHOUT arguments — a shape —
    and `ret ss` against `List<Int>` bounds it above; merged, that is
    `List<Int>`. Before, nothing could say so, and `ss` was typed only on
    passes where one of the bounds happened to be missing."""

    def test_a_shape_below_and_an_instantiation_above(self):
        # Converged, so the resolver knows Box is generic: a bare `Box` is a
        # shape, not a type that fits `Box<Int>` as it stands.
        import pyast.hints as h
        import pyast.statement as st
        import pyast.typespec as t
        from parsing.parser import parse
        from parsing.tokenizer import tokenize
        source = "namespace G\nenum Box<T>\n  enum Full(value: T)\n  enum Empty()\n"
        statements, resolver, _passes = c.__dict__["__converge"](parse(tokenize(source, "vb")).value)
        bare = next(x for x in statements if isinstance(x, st.EnumStatement)).get_type()
        of_int = t.EnumSpec(bare.line_ref, bare.root_name, bare.valid_leaf_names, bare.all_leaf_names,
                            type_params=(t.BuiltinSpec(bare.line_ref, "bigint"),))
        verdict = h.verdict((h.Hint(of_int), h.Hint(bare, lower=True)), resolver)
        self.assertEqual(of_int, verdict.type)

