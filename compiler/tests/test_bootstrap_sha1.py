"""The bootstrap's sha1Hex must match hashlib.sha1 byte for byte — it feeds
irMangle's struct-signature hashing (lazy stub class names, Lazy$s_<hash16>),
which the C-byte contract needs identical across both compilers.

Same battery shape as test_bootstrap_hash6: padding boundaries (the SHA1
length trailer occupies the same 56/64-byte block edges as MD5's) plus a
randomised spread including multi-block inputs.
"""
from __future__ import annotations

import hashlib
import random
import subprocess

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import _RUN_ENV


class TestBootstrapSha1(TestCase):
    _TIMEOUT = 300

    @classmethod
    def setUpClass(cls):
        from tests.testutil import shared_bootstrap_binary
        cls.binary = shared_bootstrap_binary()

    @classmethod
    def tearDownClass(cls):
        pass  # the shared binary is cache-owned

    def test_sha1_matches_hashlib(self):
        rng = random.Random(20260716)
        # No empty case: the driver skips empty segments (splitLines yields a
        # trailing one), and irMangle never hashes an empty signature.
        cases: list[str] = []
        for n in (1, 54, 55, 56, 57, 63, 64, 65, 119, 120, 128, 200):
            cases.append("f" * n)
        # Field-signature-shaped inputs (what irMangle actually hashes).
        for _ in range(200):
            n = rng.randint(1, 6)
            cases.append("|".join(
                f"_{i}:{rng.choice(['ptr', 'i64', 'i32', 'f64', 'fun'])}"
                for i in range(n)))
        # Random text spread, multi-block included.
        for _ in range(100):
            cases.append("".join(rng.choice("abcdefghijklmnopqrstuvwxyz_:|./$")
                                 for _ in range(rng.randint(1, 150))))
        cases = [c for c in cases if "\n" not in c]
        stdin = "".join(c + "\n" for c in cases)
        r = subprocess.run([self.binary, "sha1"], input=stdin, capture_output=True,
                           timeout=60, text=True, env=_RUN_ENV)
        self.assertEqual(0, r.returncode, r.stderr)
        got = r.stdout.splitlines()
        expected = [hashlib.sha1(c.encode()).hexdigest() for c in cases]
        self.assertEqual(len(expected), len(got))
        for i, (e, g) in enumerate(zip(expected, got)):
            if e != g:
                self.fail(f"sha1 mismatch for {cases[i]!r}: python {e}, bootstrap {g}")
