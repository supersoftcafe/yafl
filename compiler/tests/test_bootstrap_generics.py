"""bootstrap/generics.yafl — the ported MONOMORPHISATION must produce the same
lowered AST as lowering/generics.py::convert_generic_to_concrete.

The first lowering contract. Both sides run the driver pipeline up to and
including generics — converge → lambda_globals → drops (one re-convergence when
it inserted) → convert_generic_to_concrete → report_unresolved_generic_calls —
and the dumps of the monomorphised trees are diffed byte for byte. That pins
the instantiation discovery (explicit refs, spec refs, constraint-discharged
witness refs), the specialisation itself (substitution visit set, method/slot
renames, enum-spec rebuilds), the five-way reference redirect, pruning, the
enum-spec refresh, and trait-reference resolution — over the same corpus the
converge contract uses, including the bootstrap's own sources.

When either generics phase reports errors, both sides print sorted(set(errors))
instead, so the polymorphic-recursion and cannot-infer messages are pinned by
the same contract.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import compiler as c
import lowering.drops
import lowering.generics
import lowering.lambda_globals
from parsing.tokenizer import tokenize
from parsing.parser import parse
from tests.astdump import dump

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import _RUN_ENV, _CLANG_BUILD_FLAGS, _STATIC_LINK

_REPO = Path(__file__).parent.parent.parent
_BOOTSTRAP = _REPO / "bootstrap"

# The converge contract's corpus, unchanged: every stdlib file, every example,
# the bootstrap's own sources, and the small feature-pinning files. A file with
# no generics passes through monomorphisation unchanged — those files pin that
# the pass is a no-op where it must be one.
_CORPUS = sorted((_REPO / "compiler" / "stdlib").glob("*.yafl")) \
    + sorted((_REPO / "examples").glob("*.yafl")) \
    + sorted((_REPO / "bootstrap").rglob("*.yafl")) \
    + sorted((Path(__file__).parent / "corpus_converge").glob("*.yafl"))

_CONVERGE = c.__dict__["__converge"]


class TestBootstrapGenerics(TestCase):
    # N-scaled like the converge contract: ~65 files, each monomorphised on
    # the Python side too (the parser-sized bootstrap sources dominate).
    _TIMEOUT = 2400

    @classmethod
    def setUpClass(cls):
        from tests.testutil import shared_bootstrap_binary
        cls.binary = shared_bootstrap_binary()

    @classmethod
    def tearDownClass(cls):
        pass  # the shared binary is cache-owned

    def _python_generics(self, text: str) -> str:
        """Mirror the driver order exactly (compiler.py:543-580), then dump —
        or print sorted(set(errors)) when a generics phase reports any."""
        result = parse(tokenize(text, "x"))
        self.assertFalse(result.errors, "python parse errors")
        statements, _resolver, _passes = _CONVERGE(result.value)
        statements = lowering.lambda_globals.lower_lambda_globals(statements)
        statements, dropped = lowering.drops.insert_drops(statements)
        if dropped:
            statements, _resolver, _p2 = _CONVERGE(statements)
        statements, poly_errors = lowering.generics.convert_generic_to_concrete(statements)
        if poly_errors:
            return "".join(f"{e}\n" for e in sorted(set(poly_errors)))
        unresolved = lowering.generics.report_unresolved_generic_calls(statements)
        if unresolved:
            return "".join(f"{e}\n" for e in sorted(set(unresolved)))
        return dump(statements)

    def test_monomorphised_ast_matches_python(self):
        for path in _CORPUS:
            with self.subTest(file=path.name):
                text = path.read_text()
                expected = self._python_generics(text).splitlines()
                r = subprocess.run([self.binary, "generics"], input=text,
                                   capture_output=True, timeout=240, text=True,
                                   env=_RUN_ENV)
                self.assertEqual(0, r.returncode,
                                 f"{path.name}: {r.stdout[:300]}")
                got = r.stdout.splitlines()
                for i, (e, gg) in enumerate(zip(expected, got)):
                    self.assertEqual(e, gg, f"{path.name}: monomorphised AST "
                                            f"differs at line {i + 1}")
                self.assertEqual(len(expected), len(got),
                                 f"{path.name}: monomorphised AST length differs")
