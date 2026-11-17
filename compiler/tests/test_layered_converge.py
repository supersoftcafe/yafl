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
        for name in _PROGRAMS:
            with self.subTest(program=name):
                program = c.Input((_REPO / "examples" / f"{name}.yafl").read_text(),
                                  "prog.yafl")
                merged, _, _ = _CONVERGE(_parsed(self.lib + [program]))
                app, _, _ = _CONVERGE(_parsed([program]), self.base)
                # The dump first, for a readable first difference; then the
                # trees themselves, because the dump does not print every
                # field (an enum type's arguments, for one).
                self.assertEqual(dump(merged).splitlines(),
                                 (dump(self.lib_converged) + dump(app)).splitlines())
                self.assertTrue(merged == self.lib_converged + app,
                                f"{name}: trees differ in a field the dump omits")
