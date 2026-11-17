"""Converging libraries in LAYERS (#136) must change nothing.

A layer converges on the root of the layers beneath it (`ResolverRoot(own,
base)`), which already hold their converged statements and are never
rebuilt. Every root answer is the base's followed by this layer's own — the
order one root over the combined statements gives, because the libraries
come first. So converging the stdlib, then the program on top of it, must
leave exactly the statements that converging both together leaves.

A difference here is history leaking into the result: the layered run
settles the stdlib before the program sees it, so anything that latches the
FIRST view it is given (rather than the converged one) shows up. Two did:
an enum type's arguments stopped resolving once the enum had, and a union
kept whichever member order it was first built in.

The port layers through its driver (yaflc), where the generated C is the
contract.
"""
from __future__ import annotations

from pathlib import Path

import compiler as c
import pyast.resolver as g
from tests.astdump import dump
from tests.testutil import stdlib_files, stdlib_unit_name
from tests.testutil import TimedTestCase as TestCase

_REPO = Path(__file__).parent.parent.parent

_CONVERGE = c.__dict__["__converge"]
_PARSE = c.__dict__["__tokenize_and_parse"]

# Real programs over the whole stdlib: each reaches across the layer
# boundary for names, overloads, trait providers and member classes.
_PROGRAMS = ["helloWorld", "findstr", "json_pretty", "raytracer", "ylisp", "yspell"]

# A parameter whose uses disagree: merged, its uses resolve together and the
# error stands; layered, one use resolved a pass ahead of the other and the
# parameter kept the type that one alone gave (fixed in inferred_params).
_DISAGREEING_USES = """namespace Test
import System

enum Shape
  enum Circle(r: System::Int)
  enum Square(s: System::Int)

class [final] Rock()
  fun weight(): System::Int
    ret 1

fun ring(c: Circle): System::Int
  ret c.r
fun heavy(r: Rock): System::Int
  ret r.weight()
fun both(x): System::Int
  ret ring(x) + heavy(x)
fun main(): System::Int
  ret both(Circle(1))
"""

# Calls whose argument types are still unresolved names in the program's first
# pass, while the stdlib's candidates are already typed: layered, `==` once
# committed to an overload that (Int, Int32) then failed, and `depth` kept the
# type arguments it inferred from an unresolved argument (fixed in
# NamedExpression.compile).
_NO_OVERLOAD_FITS = """namespace Main
import System
fun isSpace(c: System::Int): System::Bool
  ret c == ' '
fun main(): System::Int
  ret isSpace(32) ? 0 : 1
"""

_POLYMORPHIC_RECURSION = """namespace Main
import System

class [final] Wrap<T>(v: T)

fun depth<T>(x: T, n: System::Int): System::Int
  ret n == 0 ? 0 : depth(Wrap<T>(x), n - 1) + 1

fun main(): System::Int
  ret depth(1, 3)
"""


def _parsed(inputs: list[c.Input]):
    statements, errors = _PARSE(inputs)
    assert not errors, errors
    return statements


class TestLayeredConverge(TestCase):
    # Each program converges the stdlib twice: once beneath it, once merged.
    _TIMEOUT = 1200

    @classmethod
    def setUpClass(cls):
        cls.lib = [c.Input(p.read_text(), stdlib_unit_name(p)) for p in stdlib_files()]
        cls.lib_converged, _, _ = _CONVERGE(_parsed(cls.lib))
        cls.base = g.ResolverRoot(cls.lib_converged)

    def test_layered_matches_merged(self):
        sources = {name: (_REPO / "examples" / f"{name}.yafl").read_text() for name in _PROGRAMS}
        sources["disagreeing_uses"] = _DISAGREEING_USES
        sources["no_overload_fits"] = _NO_OVERLOAD_FITS
        sources["polymorphic_recursion"] = _POLYMORPHIC_RECURSION
        for name, text in sources.items():
            with self.subTest(program=name):
                program = c.Input(text, "prog.yafl")
                merged, _, _ = _CONVERGE(_parsed(self.lib + [program]))
                app, _, _ = _CONVERGE(_parsed([program]), self.base)
                # The dump first, for a readable first difference; then the
                # trees themselves, because the dump does not print every
                # field (an enum type's arguments, for one).
                self.assertEqual(dump(merged).splitlines(),
                                 (dump(self.lib_converged) + dump(app)).splitlines())
                self.assertTrue(merged == self.lib_converged + app,
                                f"{name}: trees differ in a field the dump omits")
