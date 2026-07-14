"""bootstrap/converge.yafl — the ported compile FIXPOINT must produce the same
converged AST as compiler.py::__converge.

This is the contract that checks the whole of inference at once. The fixpoint
rewrites every statement until a pass changes nothing; what it leaves behind is
a tree in which every name has resolved to its unique declaration, every written
type has resolved into the thing it names, every inferred type has settled on
its source, and a ConvertExpression sits at every point where a representation
changes. Diffing that tree against Python's therefore checks name resolution,
type resolution, inference (both the refine and the WIDEN paths), and conversion
insertion — simultaneously, over real source.

The same methodology that pinned the parser byte-for-byte (test_bootstrap_ast),
one phase later: same dump, same corpus, but taken AFTER convergence.

`passes` is checked too: the port must settle in the SAME number of iterations.
A port that reached the same answer but took a different number of passes would
mean some compile() is doing more (or less) per pass than Python's, and the two
would drift apart on a program where the extra pass matters.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import compiler as c
from parsing.tokenizer import tokenize
from parsing.parser import parse
from tests.astdump import dump

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import _RUN_ENV, _CLANG_BUILD_FLAGS, _STATIC_LINK

_REPO = Path(__file__).parent.parent.parent
_BOOTSTRAP = _REPO / "bootstrap"

# Start with the SELF-CONTAINED sources: convergence resolves names against the
# statement set it is given, so a file that leans on the stdlib needs the stdlib
# in that set. These stand alone.
_CORPUS = [
    _REPO / "compiler" / "stdlib" / "integer.yafl",
    _REPO / "compiler" / "stdlib" / "args.yafl",
    _REPO / "compiler" / "stdlib" / "traits.yafl",
]

_CONVERGE = c.__dict__["__converge"]


class TestBootstrapConverge(TestCase):
    _TIMEOUT = 600

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

    def _python_converged(self, text: str):
        result = parse(tokenize(text, "x"))
        self.assertFalse(result.errors, "python parse errors")
        statements, _resolver = _CONVERGE(result.value)
        return statements

    def test_converged_ast_matches_python(self):
        for path in _CORPUS:
            with self.subTest(file=path.name):
                text = path.read_text()
                expected = dump(self._python_converged(text)).splitlines()

                r = subprocess.run([self.binary, "converge"], input=text,
                                   capture_output=True, timeout=120, text=True,
                                   env=_RUN_ENV)
                self.assertEqual(0, r.returncode,
                                 f"{path.name}: {r.stdout[:300]}")
                got = r.stdout.splitlines()
                for i, (e, gg) in enumerate(zip(expected, got)):
                    self.assertEqual(e, gg, f"{path.name}: converged AST differs "
                                            f"at line {i + 1}")
                self.assertEqual(len(expected), len(got),
                                 f"{path.name}: converged AST length differs")
