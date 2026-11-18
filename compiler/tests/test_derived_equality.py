"""Derived `BasicEquality` for enums and tuples — see docs/derived-equality-plan.md.

Two properties, in order of how they land:

  * an UNDISCHARGED trait constraint is a compile error at the use site, not a
    ValueError out of codegen (the recorded open bug);
  * a tuple or enum used as a `Dict`/`memoize` key gets its `==`/`hashOf`
    synthesised, so it just works.

The second is the point of the exercise: every pass that needs a compound key
today hand-builds a string fingerprint instead, and those fingerprints are
lossy.

Runtime behaviour is checked by compiler/yafl_tests/derived_equality.yafl.
"""
from __future__ import annotations


from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_c_result


def _errors(content: str) -> tuple[str, str]:
    """(emitted, diagnostics). The compiler PRINTS diagnostics and emits no C
    when it refuses. A crash
    here is a failure of the test's premise: an undischarged constraint must be
    reported, not raised out of codegen."""
    r = compile_c_result(content, "file.yafl")
    return r.c, r.stdout


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
  let d = System::Containers::Dict<(:(:System::Int): System::Int, :System::Int), System::Int>()
  # the constraint is only DEMANDED by a keyed operation, not by construction
  let d2 = System::Containers::put(d, ((x: System::Int) => x, 1), 5)
  ret 0
"""
        emitted, diagnostics = _errors(src)
        self.assertEqual("", emitted, "expected the compile to be refused")
        self.assertIn("BasicEquality", diagnostics, diagnostics)


class TestALevelHasNoInstanceOfItsOwn(TestCase):
    """An enum has one BasicEquality, at its root. A direct `==` on two Pay1s
    takes Payload's, as any call takes a Pay1 where a Payload is wanted; but
    a `where BasicEquality<T>` is exact: bound to Pay1 it asks for an
    instance for Pay1, and there is none (#136)."""

    _HEAD = """\
namespace Main
import System

enum Payload
  enum Pay1(p0: String)
  enum Pay2(pTiny: Int)

fun same<T>(a: T, b: T): Bool where BasicEquality<T>
  ret a == b

"""

    def test_the_root_serves_a_direct_call_and_its_own_binding(self):
        emitted, diagnostics = _errors(self._HEAD + """\
fun main(): Int
  let a: Pay1 = Pay1("x")
  ret (a == a ? 0 : 1) + (same<Payload>(a, a) ? 0 : 2)
""")
        self.assertNotEqual("", emitted, diagnostics)

    def test_a_where_bound_to_a_level_is_refused(self):
        bodies = {
            "explicit": "  ret same<Pay1>(a, a) ? 0 : 1\n",
            "inferred": "  ret same(a, a) ? 0 : 1\n",
            "in a tuple": "  let p: (:Pay1, :Int) = (a, 1)\n  ret p == p ? 0 : 1\n",
        }
        for name, body in bodies.items():
            with self.subTest(name):
                emitted, diagnostics = _errors(self._HEAD + "fun main(): Int\n  let a: Pay1 = Pay1(\"x\")\n" + body)
                self.assertEqual("", emitted, "expected the compile to be refused")
                self.assertIn("BasicEquality", diagnostics, diagnostics)


