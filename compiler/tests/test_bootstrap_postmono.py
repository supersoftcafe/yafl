"""bootstrap postmono stage — the post-monomorphisation driver segment must
produce the same AST as compiler.py:588-590: the re-entry into the compile
fixpoint (each freshly-instantiated body places its own conversions now that
its types are concrete), then mark_complex_enums, then inline_constants.

Telescopes on the generics contract: same corpus, same error-printing rule,
one stage further. The dump has teeth for this stage's effects: complex enums
print a `!cx` marker (tests/astdump.py + bootstrap/astdump.yafl), inlined
constants appear as re-stamped literals with their const declarations dropped.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import compiler as c
import lowering.complex_enums
import lowering.constants
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

_CORPUS = sorted((_REPO / "compiler" / "stdlib").glob("*.yafl")) \
    + sorted((_REPO / "examples").glob("*.yafl")) \
    + sorted((_REPO / "bootstrap").glob("*.yafl")) \
    + sorted((Path(__file__).parent / "corpus_converge").glob("*.yafl"))

_CONVERGE = c.__dict__["__converge"]


class TestBootstrapPostmono(TestCase):
    _TIMEOUT = 2400

    @classmethod
    def setUpClass(cls):
        sys.setrecursionlimit(20000)
        inputs = [c.Input(p.read_text(), p.name) for p in sorted(_BOOTSTRAP.glob("*.yafl"))]
        c_code = c.compile(inputs, use_stdlib=True, just_testing=False, optimization_level=1)
        assert c_code, "bootstrap compilation failed"
        with tempfile.NamedTemporaryFile(suffix="", delete=False) as tmp:
            cls.binary = tmp.name
        r = subprocess.run(
            ["clang", "-g", "-x", "c", "-", "-O0", *_CLANG_BUILD_FLAGS, *_STATIC_LINK,
             "-o", cls.binary],
            input=c_code, text=True, capture_output=True, timeout=90)
        assert r.returncode == 0, f"clang failed:\n{r.stderr[:2000]}"

    @classmethod
    def tearDownClass(cls):
        try:
            os.unlink(cls.binary)
        except OSError:
            pass

    def _python_postmono(self, text: str) -> str:
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
        statements, _resolver, _p3 = _CONVERGE(statements)
        statements = lowering.complex_enums.mark_complex_enums(statements)
        statements = lowering.constants.inline_constants(statements)
        return dump(statements)

    def test_postmono_ast_matches_python(self):
        for path in _CORPUS:
            with self.subTest(file=path.name):
                text = path.read_text()
                expected = self._python_postmono(text).splitlines()
                r = subprocess.run([self.binary, "postmono"], input=text,
                                   capture_output=True, timeout=240, text=True,
                                   env=_RUN_ENV)
                self.assertEqual(0, r.returncode,
                                 f"{path.name}: {r.stdout[:300]}")
                got = r.stdout.splitlines()
                for i, (e, gg) in enumerate(zip(expected, got)):
                    self.assertEqual(e, gg, f"{path.name}: postmono AST "
                                            f"differs at line {i + 1}")
                self.assertEqual(len(expected), len(got),
                                 f"{path.name}: postmono AST length differs")
