"""bootstrap check phase — the ported diagnostics must print BYTE-IDENTICAL
error output to compiler.py's over a corpus of deliberately-broken sources.

The contract covers the post-convergence diagnostic phases in driver order:
uninferable untyped params (with call-site clues), the [future]-global
rejection, every node's check() plus the main-function count, the
warning/error split, and the unresolved-NamedSpec scan. Output is
`sorted(set(errors))` printed one per line — Error and LineRef are both
order=True dataclasses, so the sort key is ((filename, line, offset),
message, severity) and the port must reproduce it exactly.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import compiler as c
import lowering.linearity
import lowering.lambda_globals
import lowering.drops
from parsing.tokenizer import tokenize
from parsing.parser import parse

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import _RUN_ENV, _CLANG_BUILD_FLAGS, _STATIC_LINK

_REPO = Path(__file__).parent.parent.parent
_BOOTSTRAP = _REPO / "bootstrap"
_CORPUS = sorted((Path(__file__).parent / "corpus_check").glob("*.yafl"))

_CONVERGE = c.__dict__["__converge"]
_DIAGNOSE = c.__dict__["__collect_diagnostics"]


class TestBootstrapCheck(TestCase):
    _TIMEOUT = 900

    @classmethod
    def setUpClass(cls):
        from tests.testutil import shared_bootstrap_binary
        cls.binary = shared_bootstrap_binary()

    @classmethod
    def tearDownClass(cls):
        pass  # the shared binary is cache-owned

    def _python_diagnostics(self, text: str) -> str:
        from tests.testutil import cached_reference
        return cached_reference("check", text,
                                lambda: self._python_diagnostics_uncached(text))

    def _python_diagnostics_uncached(self, text: str) -> str:
        result = parse(tokenize(text, "x"))
        self.assertFalse(result.errors, "python parse errors")
        statements, resolver, _passes = _CONVERGE(result.value)
        statements = lowering.lambda_globals.lower_lambda_globals(statements)
        statements, dropped = lowering.drops.insert_drops(statements)
        if dropped:
            statements, resolver, _p2 = _CONVERGE(statements)
        failures, warnings = _DIAGNOSE(statements, resolver)
        if not failures:
            # Mirror the driver: linearity runs only on a clean check phase,
            # and its errors return ALONE.
            linearity_errors = lowering.linearity.check_linearity(statements, resolver)
            if linearity_errors:
                failures = linearity_errors
        printed = failures if failures else warnings
        return "".join(f"{e}\n" for e in sorted(set(printed)))

    def test_diagnostics_match_python(self):
        checked = 0
        for path in _CORPUS:
            with self.subTest(file=path.name):
                text = path.read_text()
                expected = self._python_diagnostics(text)
                self.assertTrue(expected, f"{path.name}: corpus file is not broken")
                r = subprocess.run([self.binary, "check"], input=text,
                                   capture_output=True, timeout=120, text=True,
                                   env=_RUN_ENV)
                self.assertEqual(expected, r.stdout,
                                 f"{path.name}: diagnostics differ")
                checked += 1
        self.assertGreater(checked, 3)

    def test_clean_sources_stay_clean(self):
        # The converge corpus is all VALID code: both sides must agree it is
        # diagnostic-free (bar the no-main note every library file shares).
        for path in [_REPO / "compiler" / "stdlib" / "traits.yafl",
                     _REPO / "compiler" / "stdlib" / "integer.yafl"]:
            with self.subTest(file=path.name):
                text = path.read_text()
                expected = self._python_diagnostics(text)
                r = subprocess.run([self.binary, "check"], input=text,
                                   capture_output=True, timeout=120, text=True,
                                   env=_RUN_ENV)
                self.assertEqual(expected, r.stdout,
                                 f"{path.name}: diagnostics differ")
