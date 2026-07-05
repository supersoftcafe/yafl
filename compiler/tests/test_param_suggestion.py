"""Whole-program param inference for an UN-annotated, non-generic function.

`fun addSomeThings(a, b) ret a + b` declares no parameter types. They are holes
that nothing inside the function can fill; the only evidence is the call site
`addSomeThings(1, 45)`, whose argument types (`Int`, `Int`) must travel BACK to
the declaration as a suggestion. Once `a:Int, b:Int` is adopted, `+` resolves and
the body gives the return. This is path 3 (the suggestion registry) and goes
beyond generics — `addSomeThings` is monomorphic, just unwritten.

Today this fails with "Failed to resolve `+`": the params stay `None`-typed and no
suggestion mechanism carries the call-site types to the declaration.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


_SRC = """
namespace Test
import System

fun addSomeThings(a, b)
  ret a + b

fun main(): System::Int
  ret addSomeThings(1, 45)
"""


# Annotated control: a declared type wins and flows DOWN to the literals. Already
# works today; kept so the suggestion path can't regress the declared-wins rule.
_SRC_ANNOTATED = """
namespace Test
import System

fun addSomeThings(a: System::Int, b: System::Int): System::Int
  ret a + b

fun main(): System::Int
  ret addSomeThings(1, 45)
"""


class TestParamSuggestion(TestCase):
    def test_untyped_params_inferred_from_call_site(self):
        rc, _out = compile_and_run_stdlib_capture(_SRC, timeout=120)
        self.assertEqual(46, rc)

    def test_annotated_params_still_work(self):
        rc, _out = compile_and_run_stdlib_capture(_SRC_ANNOTATED, timeout=120)
        self.assertEqual(46, rc)
