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

# EVERYTHING, one file at a time: convergence resolves names against exactly
# the statement set it is given, so both sides see the same single file and
# must leave the same names unresolved — the diff is meaningful whether or
# not the file stands alone. The whole stdlib, every example, and the
# bootstrap's OWN sources (the self-host ring: the port must converge itself
# exactly as Python does).
_CORPUS = sorted((_REPO / "compiler" / "stdlib").glob("*.yafl")) \
    + sorted((_REPO / "examples").glob("*.yafl")) \
    + sorted((_REPO / "bootstrap").rglob("*.yafl")) \
    + sorted((Path(__file__).parent / "corpus_converge").glob("*.yafl"))
# corpus_converge/: one small self-contained file per feature the port has
# historically missed (the audit's regression pressure) — each was added RED
# against the port of its day and pinned green by the fix.

_CONVERGE = c.__dict__["__converge"]

# WHOLE-PROGRAM entries: the per-file corpus can never exercise cross-file
# resolution (trait providers in another file, overloads spread over files,
# member classes used from another namespace) — the C contract found three
# such divergences that every single-file stage contract was blind to. Each
# entry concatenates real files into ONE text compiled identically ("x") by
# both sides.
_WHOLE_PROGRAMS = [
    ("stdlib+helloWorld",
     "".join(p.read_text() for p in sorted((_REPO / "compiler" / "stdlib").glob("*.yafl"))
             ) + (_REPO / "examples" / "helloWorld.yafl").read_text()),
    # __parallel__ coverage: its type is the tuple of the callables' results,
    # which only grounds when the callees resolve — i.e. whole-program.
    ("stdlib+findstr",
     "".join(p.read_text() for p in sorted((_REPO / "compiler" / "stdlib").glob("*.yafl"))
             ) + (_REPO / "examples" / "findstr.yafl").read_text()),
    # Result-side generic inference through a union: collect<S,E>'s `String|E`
    # unifies against the caller's declared `String|JsonParseError|Never`, and
    # the set-fallback must bind E by STRUCTURAL ground-member removal (the
    # port once matched by uid and deferred forever on the raw
    # `NamedSpec System::String` member, leaving E's placeholder in the C).
    ("stdlib+json_pretty",
     "".join(p.read_text() for p in sorted((_REPO / "compiler" / "stdlib").glob("*.yafl"))
             ) + (_REPO / "examples" / "json_pretty.yafl").read_text()),
]


class TestBootstrapConverge(TestCase):
    # N-scaled: the corpus is ~60 files and each of the two tests converges
    # every file on the Python side too (the parser-sized bootstrap sources
    # dominate).
    _TIMEOUT = 2400

    @classmethod
    def setUpClass(cls):
        from tests.testutil import shared_bootstrap_binary
        cls.binary = shared_bootstrap_binary()

    @classmethod
    def tearDownClass(cls):
        pass  # the shared binary is cache-owned

    def _python_converged(self, text: str):
        result = parse(tokenize(text, "x"))
        self.assertFalse(result.errors, "python parse errors")
        statements, _resolver, passes = _CONVERGE(result.value)
        return statements, passes

    def test_converged_ast_matches_python(self):
        for path in _CORPUS:
            with self.subTest(file=path.name):
                text = path.read_text()
                statements, _passes = self._python_converged(text)
                expected = dump(statements).splitlines()

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

    def test_whole_program_converged_matches_python(self):
        # Cross-file resolution: trait providers, overload sets and member
        # classes that live in OTHER files than their uses. Red until the
        # port resolves whole programs exactly as Python (found via the C
        # contract: penTrait not rewritten by monomorphisation; `append`
        # overload left unresolved; a member `pos` left un-uniquified).
        for name, text in _WHOLE_PROGRAMS:
            with self.subTest(program=name):
                statements, _passes = self._python_converged(text)
                expected = dump(statements).splitlines()
                r = subprocess.run([self.binary, "converge"], input=text,
                                   capture_output=True, timeout=300, text=True,
                                   env=_RUN_ENV)
                self.assertEqual(0, r.returncode, f"{name}: {r.stdout[:300]}")
                got = r.stdout.splitlines()
                for i, (e, gg) in enumerate(zip(expected, got)):
                    self.assertEqual(e, gg, f"{name}: converged AST differs "
                                            f"at line {i + 1}")
                self.assertEqual(len(expected), len(got),
                                 f"{name}: converged AST length differs")

    def test_pass_count_matches_python(self):
        # The port must settle in the SAME number of iterations: a port that
        # reached the same answer in a different number of passes means some
        # compile() is doing more (or less) per pass than Python's, and the
        # two drift apart on a program where the extra pass matters.
        for path in _CORPUS:
            with self.subTest(file=path.name):
                text = path.read_text()
                _statements, py_passes = self._python_converged(text)
                r = subprocess.run([self.binary, "passes"], input=text,
                                   capture_output=True, timeout=120, text=True,
                                   env=_RUN_ENV)
                self.assertEqual(0, r.returncode,
                                 f"{path.name}: {r.stdout[:300]}")
                self.assertEqual(f"{py_passes}\n", r.stdout,
                                 f"{path.name}: pass count differs")
