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
  let d = System::Dict<(:(:System::Int): System::Int, :System::Int), System::Int>()
  # the constraint is only DEMANDED by a keyed operation, not by construction
  let d2 = System::put(d, ((x: System::Int) => x, 1), 5)
  ret 0
"""
        emitted, diagnostics = _errors(src)
        self.assertEqual("", emitted, "expected the compile to be refused")
        self.assertIn("BasicEquality", diagnostics, diagnostics)


