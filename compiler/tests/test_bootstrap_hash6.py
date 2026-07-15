"""bootstrap/hashes.yafl — LineRef.hash6 ported to YAFL (full MD5 + base64 +
alphanumeric filter). Every `name@hash6` in the ported compiler must equal
the Python compiler's byte for byte, so this diffs the two over hundreds of
(filename, line, col) triples: every declaration site in the corpus plus
randomised cases covering multi-block MD5 inputs and boundary lengths
(55/56/57 bytes — the padding split points).
"""
from __future__ import annotations

import os
import random
import subprocess
import tempfile
from pathlib import Path

from parsing.tokenizer import LineRef

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import _RUN_ENV, _CLANG_BUILD_FLAGS, _STATIC_LINK

_REPO = Path(__file__).parent.parent.parent
_BOOTSTRAP = _REPO / "bootstrap"


class TestBootstrapHash6(TestCase):
    _TIMEOUT = 300

    @classmethod
    def setUpClass(cls):
        from tests.testutil import shared_bootstrap_binary
        cls.binary = shared_bootstrap_binary()

    @classmethod
    def tearDownClass(cls):
        pass  # the shared binary is cache-owned

    def test_hash6_matches_python(self):
        rng = random.Random(20260713)
        cases: list[tuple[str, int, int]] = []
        # Padding boundaries: "f:l:c" total lengths straddling 55/56/57/63/64/119/128.
        for n in (1, 40, 45, 46, 47, 50, 53, 100, 110, 118, 120, 200):
            cases.append(("f" * n, 12, 3))
        # Randomised spread, including long filenames (multi-block MD5).
        for _ in range(300):
            fn = "".join(rng.choice("abcdefghijklmnopqrstuvwxyz_./") for _ in range(rng.randint(1, 90)))
            cases.append((fn + ".yafl", rng.randint(1, 99999), rng.randint(1, 500)))
        stdin = "".join(f"{f}|{l}|{c}\n" for f, l, c in cases)
        r = subprocess.run([self.binary, "hash6"], input=stdin, capture_output=True,
                           timeout=60, text=True, env=_RUN_ENV)
        self.assertEqual(0, r.returncode)
        got = r.stdout.splitlines()
        expected = [LineRef(f, l, c).hash6() for f, l, c in cases]
        self.assertEqual(len(expected), len(got))
        for i, (e, g) in enumerate(zip(expected, got)):
            if e != g:
                self.fail(f"hash6 mismatch for {cases[i]}: python {e!r}, bootstrap {g!r}")
