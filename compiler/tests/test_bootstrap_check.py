"""bootstrap check phase — the ported diagnostics must print BYTE-IDENTICAL
error output to compiler.py's over a corpus of deliberately-broken sources.

The contract covers the post-convergence diagnostic phases in driver order:
uninferable untyped params (with the clue read off the BODY), the [future]-global
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
import warning_flags as wf
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

    def _python_diagnostics(self, text: str, warn_flags: tuple[str, ...] = ()) -> str:
        from tests.testutil import cached_reference
        return cached_reference("check", text,
                                lambda: self._python_diagnostics_uncached(text, warn_flags),
                                extra="|".join(warn_flags))

    def _python_diagnostics_uncached(self, text: str, warn_flags: tuple[str, ...] = ()) -> str:
        result = parse(tokenize(text, "x"))
        self.assertFalse(result.errors, "python parse errors")
        # A fixpoint that never settles reports the declarations that flip —
        # the driver prints those and stops, so the contract compares them.
        try:
            statements, resolver, _passes = _CONVERGE(result.value)
            statements = lowering.lambda_globals.lower_lambda_globals(statements)
            statements, dropped = lowering.drops.insert_drops(statements)
            if dropped:
                statements, resolver, _p2 = _CONVERGE(statements)
        except c.ConvergenceError as unsettled:
            return "".join(f"{e}\n" for e in sorted(set(unsettled.errors)))
        enabled_warnings = wf.resolve_enabled_warnings(list(warn_flags))
        failures, warnings = _DIAGNOSE(statements, resolver, enabled_warnings)
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
        for path in [_REPO / "compiler" / "stdlib" / "System" / "traits.yafl",
                     _REPO / "compiler" / "stdlib" / "System" / "integer.yafl"]:
            with self.subTest(file=path.name):
                text = path.read_text()
                expected = self._python_diagnostics(text)
                r = subprocess.run([self.binary, "check"], input=text,
                                   capture_output=True, timeout=120, text=True,
                                   env=_RUN_ENV)
                self.assertEqual(expected, r.stdout,
                                 f"{path.name}: diagnostics differ")

    def test_wflag_matches_python(self):
        # unused-parameter is off by default (the noisy warning this feature
        # exists to gate); -Wunused-parameter turns it on, -Wall turns on
        # every optional warning, -Wno-unused-variable turns off a
        # default-on one. Each checked byte-for-byte against the same
        # -W-aware Python reference used by the corpus contract above.
        text = ("namespace Main\n"
                "import System\n"
                "fun f(a: System::Int, b: System::Int): System::Int\n"
                "  ret a\n"
                "fun main(): System::Int\n"
                "  let x = 5\n"
                "  ret f(1, 2)\n")
        cases = [
            (), ("unused-parameter",), ("all",), ("no-unused-variable",),
        ]
        for flags in cases:
            with self.subTest(flags=flags):
                expected = self._python_diagnostics(text, flags)
                r = subprocess.run(
                    [self.binary, "check", *[f"-W{f}" for f in flags]],
                    input=text, capture_output=True, timeout=120, text=True,
                    env=_RUN_ENV)
                self.assertEqual(expected, r.stdout, f"flags={flags}: diagnostics differ")
        # Sanity: the flag actually changes what's printed, both sides agree.
        self.assertNotIn("parameter 'b' is never used", self._python_diagnostics(text, ()))
        self.assertIn("parameter 'b' is never used", self._python_diagnostics(text, ("unused-parameter",)))

    def test_unknown_wflag_fails_both_sides(self):
        text = "namespace Main\nimport System\nfun main(): System::Int\n  ret 0\n"
        with self.assertRaises(ValueError):
            wf.resolve_enabled_warnings(["bogus"])
        r = subprocess.run([self.binary, "check", "-Wbogus"], input=text,
                           capture_output=True, timeout=120, text=True,
                           env=_RUN_ENV)
        self.assertNotEqual(0, r.returncode)
        self.assertIn("unknown warning", r.stderr)
