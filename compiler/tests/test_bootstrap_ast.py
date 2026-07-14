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

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import _RUN_ENV, _CLANG_BUILD_FLAGS, _STATIC_LINK

_REPO = Path(__file__).parent.parent.parent
_BOOTSTRAP = _REPO / "bootstrap"
_CORPUS = sorted((_REPO / "compiler" / "stdlib").glob("*.yafl")) \
        + sorted((_REPO / "examples").glob("*.yafl")) \
        + sorted(_BOOTSTRAP.glob("*.yafl"))


class TestBootstrapAst(TestCase):
    _TIMEOUT = 600

    @classmethod
    def setUpClass(cls):
        import compiler as c
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

    def test_ast_matches_python_parser(self):
        self.assertGreater(len(_CORPUS), 30)
        for path in _CORPUS:
            with self.subTest(file=path.name):
                text = path.read_text()
                result = parse(tokenize(text, "x"))
                self.assertFalse(result.errors, f"{path.name}: python parse errors")
                expected = dump(result.value)
                r = subprocess.run([self.binary, "ast"], input=text, capture_output=True,
                                   timeout=90, text=True, env=_RUN_ENV)
                self.assertEqual(0, r.returncode, f"{path.name}: bootstrap exited {r.returncode}")
                if r.stdout != expected:
                    el, gl = expected.splitlines(), r.stdout.splitlines()
                    i = next((k for k, (a, b) in enumerate(zip(el, gl)) if a != b),
                             min(len(el), len(gl)))
                    self.fail(f"{path.name}: AST differs at line {i}:\n"
                              f"  python    {el[i] if i < len(el) else '<eof>'!r}\n"
                              f"  bootstrap {gl[i] if i < len(gl) else '<eof>'!r}")
