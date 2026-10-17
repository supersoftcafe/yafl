"""bootstrap/ — the ported parser must build the SAME pyast tree as Python.

The strongest front-end contract available: for every .yafl source in the
repository, the bootstrap's AST dump (tests/astdump.py's format, produced by
bootstrap/astdump.yafl) must equal the Python parser's byte for byte —
node kinds, hashed unique names, line/column refs, types as spelled, and
every parse-time transform (pipeline beta-reduction and `_` placeholders,
the andNot fold, `&&`/`||`/`is` desugaring, negation folding into literals,
paren-tuple collapse, namespace qualification, class constructors and array
accessors, enum leaf constructors).
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from parsing.tokenizer import tokenize
from parsing.parser import parse
from tests.astdump import dump

from tests.testutil import stdlib_files, TimedTestCase as TestCase
from tests.testutil import _RUN_ENV, _CLANG_BUILD_FLAGS, _STATIC_LINK

_REPO = Path(__file__).parent.parent.parent
_BOOTSTRAP = _REPO / "bootstrap"
_CORPUS = stdlib_files() \
        + sorted((_REPO / "examples").glob("*.yafl")) \
        + sorted(_BOOTSTRAP.rglob("*.yafl"))


class TestBootstrapAst(TestCase):
    _TIMEOUT = 600

    @classmethod
    def setUpClass(cls):
        from tests.testutil import shared_bootstrap_binary
        cls.binary = shared_bootstrap_binary()

    @classmethod
    def tearDownClass(cls):
        pass  # the shared binary is cache-owned

    def test_ast_matches_python_parser(self):
        self.assertGreater(len(_CORPUS), 30)
        for path in _CORPUS:
            with self.subTest(file=path.name):
                text = path.read_text()
                result = parse(tokenize(text, "x"))
                self.assertFalse(result.errors, f"{path.name}: python parse errors")
                expected = dump(result.value)
                r = subprocess.run([self.binary, "--stage", "ast"], input=text, capture_output=True,
                                   timeout=90, text=True, env=_RUN_ENV)
                self.assertEqual(0, r.returncode, f"{path.name}: bootstrap exited {r.returncode}")
                if r.stdout != expected:
                    el, gl = expected.splitlines(), r.stdout.splitlines()
                    i = next((k for k, (a, b) in enumerate(zip(el, gl)) if a != b),
                             min(len(el), len(gl)))
                    self.fail(f"{path.name}: AST differs at line {i}:\n"
                              f"  python    {el[i] if i < len(el) else '<eof>'!r}\n"
                              f"  bootstrap {gl[i] if i < len(gl) else '<eof>'!r}")

    def test_statements_sit_where_their_expression_starts(self):
        # `ret`, a bare expression, `if` and `else if` sit where their
        # expression starts. A bracketed group leading a binary expression
        # used to split the compilers: Python's parse dropped the `(` (the
        # statement sat inside the bracket) while the port, like the `==`
        # node itself, placed it at the bracket. A leading unary op stays at
        # its own token, folded literal or not; `else if` is dumped too.
        text = (
            "fun f(a: System::Int, b: System::Int): System::Int\n"
            "  if (a) == b\n"
            "    ret (a) + b\n"
            "  else if (b) == a\n"
            "    ret -1\n"
            "  else\n"
            "    ret 0\n"
            "  if a == (b)\n"
            "    ret !(a == b) ? 1 : 2\n"
            "  (a) + b\n"
            "  print((a) + b)\n"
            "  ret (a) |> (x) => x + b\n")
        result = parse(tokenize(text, "x"))
        self.assertFalse(result.errors)
        expected = dump(result.value)
        r = subprocess.run([self.binary, "--stage", "ast"], input=text, capture_output=True,
                           timeout=90, text=True, env=_RUN_ENV)
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertEqual(expected.splitlines(), r.stdout.splitlines())
        # And the positions are the bracket's, not the first token inside it.
        starts = [l.strip() for l in expected.splitlines()
                  if l.strip().split("|")[0] in ("If", "ElseIf", "Ret", "Action")]
        self.assertEqual(["If|2:6|", "Ret|3:9|0", "ElseIf|4:11|", "Ret|5:9|0", "Ret|7:9|0",
                          "If|8:6|", "Ret|9:9|0", "Action|10:3|", "Action|11:3|"], starts)
