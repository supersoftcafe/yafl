"""bootstrap/tokenizer.yafl — stage 1 of the self-hosted compiler.

The YAFL-written tokenizer must agree with compiler/parsing/tokenizer.py
byte for byte. This harness runs BOTH over every .yafl source in the
repository — the whole stdlib, every example, and the bootstrap sources
themselves — and diffs the token dumps (KIND|indent|line|col|text, one per
token including EOF), with CHARACTER columns on both sides.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from parsing.tokenizer import tokenize

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_to_binary, _RUN_ENV

_REPO = Path(__file__).parent.parent.parent
_BOOTSTRAP = _REPO / "bootstrap"

_CORPUS = sorted((_REPO / "compiler" / "stdlib").glob("*.yafl")) \
        + sorted((_REPO / "examples").glob("*.yafl")) \
        + sorted((_REPO / "bootstrap").glob("*.yafl"))


def _python_dump(text: str) -> str:
    # Both sides count CHARACTER columns — LineRef.offset is character-based
    # and hash6 hashes it, so the port matches it exactly.
    out = [f"{t.kind.name}|{t.indent}|{t.line_ref.line}|{t.line_ref.offset}|{t.value}"
           for t in tokenize(text, "x")]
    return "\n".join(out) + "\n"


class TestBootstrapTokenizer(TestCase):
    _TIMEOUT = 240  # one full compile + a fast pass over ~40 corpus files

    @classmethod
    def setUpClass(cls):
        import compiler as c
        import tempfile
        from tests.testutil import _CLANG_BUILD_FLAGS, _STATIC_LINK
        inputs = [c.Input(p.read_text(), p.name) for p in sorted(_BOOTSTRAP.glob("*.yafl"))]
        c_code = c.compile(inputs, use_stdlib=True, just_testing=False, optimization_level=1)
        assert c_code, "bootstrap compilation failed"
        with tempfile.NamedTemporaryFile(suffix="", delete=False) as tmp:
            cls.binary = tmp.name
        r = subprocess.run(
            ["clang", "-g", "-x", "c", "-", "-O0", *_CLANG_BUILD_FLAGS, *_STATIC_LINK,
             "-o", cls.binary],
            input=c_code, text=True, capture_output=True, timeout=60)
        assert r.returncode == 0, f"clang failed:\n{r.stderr[:2000]}"

    @classmethod
    def tearDownClass(cls):
        try:
            os.unlink(cls.binary)
        except OSError:
            pass

    def test_corpus_matches_python_tokenizer(self):
        self.assertGreater(len(_CORPUS), 20, "corpus went missing?")
        for path in _CORPUS:
            with self.subTest(file=path.name):
                text = path.read_text()
                r = subprocess.run([self.binary, "tokens"], input=text, capture_output=True,
                                   timeout=30, text=True, env=_RUN_ENV)
                self.assertEqual(0, r.returncode, f"{path.name}: tokenizer exited {r.returncode}")
                expected = _python_dump(text)
                if r.stdout != expected:
                    exp_lines = expected.splitlines()
                    got_lines = r.stdout.splitlines()
                    for i, (e, g) in enumerate(zip(exp_lines, got_lines)):
                        if e != g:
                            self.fail(f"{path.name}: first mismatch at token {i}:\n"
                                      f"  expected {e!r}\n  got      {g!r}")
                    self.fail(f"{path.name}: token count differs "
                              f"(expected {len(exp_lines)}, got {len(got_lines)})")

    def test_tricky_lexemes(self):
        # Focused edge cases beyond what the corpus happens to contain.
        tricky = (
            'let a = 0x_FF_u64 + 0b10i8 + 0o77 + 1_000.5_5e-3f32 + 1. + 1e + 1e+\n'
            'let b = "esc \\" quote" + \'\\n\' + re"a\\"b" + `odd name` + ``\n'
            'let c = 1..9 ?? x??y @ $ ~n & ~m\n'
            'if x>=1 && y<=2 || z!=3 << 4 >> 5 :: w\n'
        )
        r = subprocess.run([self.binary, "tokens"], input=tricky, capture_output=True,
                           timeout=30, text=True, env=_RUN_ENV)
        self.assertEqual(0, r.returncode)
        self.assertEqual(_python_dump(tricky), r.stdout)
