"""bootstrap/equality.yafl — the ported structural equality must AGREE with
Python's dataclass `__eq__`.

This is the compile fixpoint's termination test (`new_statements ==
statements`), so it has to be exactly as strict as Python's and no stricter:

  * too LAX (a field the port forgot to compare) and the loop stops early,
    silently freezing a half-compiled AST;
  * too STRICT (comparing a `compare=False` cache that never settles) and the
    loop spins until it hits the iteration cap.

The N×N matrix over every corpus file's top-level statements catches the lax
direction — a forgotten field makes two different statements look equal. The
exclusion cases below catch the strict direction, which the matrix cannot see
(only `compile()` produces nodes that differ *only* in excluded metadata).
"""
from __future__ import annotations

import dataclasses
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pyast.typespec as t
import pyast.statement as s
from parsing.tokenizer import tokenize, LineRef
from parsing.parser import parse

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import _RUN_ENV, _CLANG_BUILD_FLAGS, _STATIC_LINK

_REPO = Path(__file__).parent.parent.parent
_BOOTSTRAP = _REPO / "bootstrap"
_CORPUS = sorted((_REPO / "compiler" / "stdlib").glob("*.yafl")) + [
    _REPO / "examples" / "ylisp.yafl",
    _REPO / "examples" / "raytracer.yafl",
    _BOOTSTRAP / "ast" / "nodes.yafl",
    _BOOTSTRAP / "parse" / "parser.yafl",
]


class TestBootstrapEquality(TestCase):
    _TIMEOUT = 400

    @classmethod
    def setUpClass(cls):
        from tests.testutil import shared_bootstrap_binary
        cls.binary = shared_bootstrap_binary()

    @classmethod
    def tearDownClass(cls):
        pass  # the shared binary is cache-owned

    def test_equality_matrix_agrees_with_python(self):
        for path in _CORPUS:
            with self.subTest(file=path.name):
                text = path.read_text()
                result = parse(tokenize(text, "x"))
                self.assertFalse(result.errors, f"{path.name}: python parse errors")
                stmts = result.value
                self.assertGreater(len(stmts), 0)
                expected = ["".join("1" if a == b else "0" for b in stmts) for a in stmts]

                r = subprocess.run([self.binary, "eq"], input=text, capture_output=True,
                                   timeout=90, text=True, env=_RUN_ENV)
                self.assertEqual(0, r.returncode, r.stdout[:200])
                got = r.stdout.splitlines()
                self.assertEqual(len(expected), len(got), f"{path.name}: row count")
                for i, (e, g) in enumerate(zip(expected, got)):
                    self.assertEqual(e, g, f"{path.name} row {i} ({type(stmts[i]).__name__})")

    def test_python_excludes_line_ref_from_spec_equality(self):
        """The port mirrors these exclusions; pin the Python behaviour they
        mirror, so a change to it is caught here rather than as a mysterious
        non-terminating fixpoint later."""
        a = t.NamedSpec(LineRef("f", 1, 1), "Foo", ())
        b = t.NamedSpec(LineRef("g", 9, 9), "Foo", ())
        self.assertEqual(a, b, "specs must compare without their line refs")

    def test_python_excludes_derived_caches_from_node_equality(self):
        import pyast.expression as e
        lr = LineRef("f", 1, 1)
        a = e.NamedExpression(lr, "x")
        b = e.NamedExpression(lr, "x")
        b.resolved_trait_scope = t.ClassSpec(lr, "Some")
        self.assertEqual(a, b, "resolved_trait_scope is a cache, not identity")

    def test_python_compares_expression_line_refs(self):
        import pyast.expression as e
        self.assertNotEqual(e.IntegerExpression(LineRef("f", 1, 1), 1, 0),
                            e.IntegerExpression(LineRef("f", 2, 1), 1, 0),
                            "expressions DO compare their line refs")
