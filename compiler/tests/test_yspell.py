"""The `examples/yspell` spell checker.

Builds the example once and runs it against a fixture dictionary (via -d, so
tests are independent of /usr/share/dict) and small temp files. Covers: clean
runs, suggestion generation for each edit kind, per-file deduplication, case
handling, apostrophes, multi-file (parallel) checking with deterministic output
order, and the error/usage exit codes.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_to_binary, _RUN_ENV

_EXAMPLE = Path(__file__).parent.parent.parent / "examples" / "yspell.yafl"

_DICT_WORDS = [
    "brown", "dog", "don't", "fox", "hello", "jumps", "lazy", "over",
    "package", "quick", "receive", "shall", "the", "we", "world", "Linux",
]


class TestYspell(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary = compile_to_binary(_EXAMPLE.read_text())
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dict_path = str(Path(cls.tmp.name, "words"))
        Path(cls.dict_path).write_text("\n".join(_DICT_WORDS) + "\n")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()
        try:
            os.unlink(cls.binary)
        except OSError:
            pass

    def _write(self, name: str, text: str) -> str:
        p = Path(self.tmp.name, name)
        p.write_text(text)
        return str(p)

    def _run(self, *paths: str):
        r = subprocess.run([self.binary, "-d", self.dict_path, *paths],
                           capture_output=True, timeout=30, text=True, env=_RUN_ENV)
        return r.returncode, r.stdout

    def test_clean_file_is_silent_success(self):
        f = self._write("clean.txt", "The quick brown fox jumps over the lazy dog.\n")
        rc, out = self._run(f)
        self.assertEqual(0, rc)
        self.assertEqual("", out)

    def test_misspelling_reported_with_suggestion(self):
        f = self._write("typo.txt", "We shall recieve the package.\n")
        rc, out = self._run(f)
        self.assertEqual(1, rc)
        self.assertEqual(1, len(out.splitlines()))
        line = out.splitlines()[0]
        self.assertIn(f"{f}:1:", line)
        self.assertIn("'recieve'", line)
        self.assertIn("receive", line.split("->")[1])  # transposition found

    def test_each_edit_kind_finds_its_suggestion(self):
        cases = {
            "helo":   "hello",   # insertion
            "jumpps": "jumps",   # deletion
            "wprld":  "world",   # substitution
            "qucik":  "quick",   # transposition
        }
        for typo, expect in cases.items():
            f = self._write("edit.txt", f"a {typo} b\n")
            rc, out = self._run(f)
            self.assertEqual(1, rc, typo)
            self.assertIn(expect, out, typo)

    def test_unknown_word_without_suggestions(self):
        f = self._write("noidea.txt", "complete zzxqj nonsense\n")
        rc, out = self._run(f)
        self.assertEqual(1, rc)
        self.assertIn("'zzxqj' (no suggestions)", out)
        # 'complete' and 'nonsense' are not in the fixture dictionary either:
        self.assertEqual(3, len(out.splitlines()))

    def test_repeated_misspelling_reported_once_per_file(self):
        # Surround the repeats with dictionary words only, so the one
        # misspelling is the only candidate — and is reported exactly once.
        f = self._write("dup.txt", "qucik the\nthe qucik\nover qucik dog\n")
        rc, out = self._run(f)
        self.assertEqual(1, rc)
        self.assertEqual(1, len(out.splitlines()))
        self.assertIn("'qucik'", out)
        self.assertIn(":1:", out)   # reported at first occurrence

    def test_case_insensitive_against_dictionary(self):
        # 'The' (capitalised) and 'HELLO' (upper) must pass via lowercasing;
        # 'linux' must pass via capitalisation against dictionary 'Linux'.
        f = self._write("case.txt", "The HELLO linux\n")
        rc, out = self._run(f)
        self.assertEqual(0, rc)
        self.assertEqual("", out)

    def test_apostrophes(self):
        f = self._write("apos.txt", "don't worry\n")
        rc, out = self._run(f)
        # "don't" is in the dictionary; "worry" is not.
        self.assertEqual(1, rc)
        self.assertNotIn("don't", out)
        self.assertIn("'worry'", out)

    def test_multiple_files_report_in_file_order(self):
        a = self._write("a.txt", "aardvarkk\n")
        b = self._write("b.txt", "bbattleship\n")
        c = self._write("c.txt", "ccatapult\n")
        rc, out = self._run(a, b, c)
        self.assertEqual(1, rc)
        lines = out.splitlines()
        self.assertEqual(3, len(lines))
        self.assertIn(a, lines[0])
        self.assertIn(b, lines[1])
        self.assertIn(c, lines[2])

    def test_missing_input_file(self):
        rc, out = self._run(str(Path(self.tmp.name, "absent.txt")))
        self.assertEqual(1, rc)
        self.assertIn("cannot open", out)

    def test_missing_dictionary(self):
        f = self._write("x.txt", "hello\n")
        r = subprocess.run([self.binary, "-d", "/nonexistent/dict", f],
                           capture_output=True, timeout=30, text=True, env=_RUN_ENV)
        self.assertEqual(2, r.returncode)
        self.assertIn("cannot read dictionary", r.stdout)

    def test_usage_when_no_args(self):
        r = subprocess.run([self.binary], capture_output=True, timeout=30,
                           text=True, env=_RUN_ENV)
        self.assertEqual(2, r.returncode)
        self.assertIn("usage:", r.stdout)
