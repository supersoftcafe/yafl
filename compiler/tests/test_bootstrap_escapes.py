"""ESCAPE parity — the port's string-escape decoder must agree with
parser.py's `_unescape_string`, value and error text alike.

The port carries an `unesc` driver mode built for exactly this contract, and
nothing was driving it. Both compilers implement `\\xNN`, `\\uXXXX` and
`\\u{…}` and decode them identically — but two error messages had drifted:

    python: codepoint U+110000 is out of range (max U+10FFFF)
    port:   codepoint out of range (max 10FFFF)

    python: codepoint U+D800 is a UTF-16 surrogate, not a scalar value
    port:   surrogate codepoints are not valid scalars

Message strings are VERBATIM across the two compilers — the diagnostics
contracts diff them byte for byte — so a paraphrase is a parity break, and one
that only shows up on invalid input, which is the half nothing was checking.

LENGTH IS COMPARED IN BYTES. `unesc` reports `out=length(decoded)`, and YAFL's
`length` counts BYTES (string_length_int; `slice`/`byteAt` are byte offsets),
whereas Python's `len` counts CODEPOINTS — `\\u{1F600}` is 4 against 1. Neither
is wrong; the string models differ. The mirror therefore measures
`len(decoded.encode("utf-8"))`, which is the same quantity the port reports.

The input is fed WITHOUT a trailing newline: the port splits stdin into lines,
so a final newline would yield one extra empty record that Python's
`splitlines()` does not produce.
"""
from __future__ import annotations

import subprocess

from parsing.parser import _unescape_string

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import _RUN_ENV

# Decode cases then every error case parser.py can raise. Each must be
# non-empty and free of newlines — one case per line is the mode's protocol.
_CASES = [
    r"plain",
    r"AB\x41",
    r"\x00",
    r"\xff",
    r"C",
    r"é",
    r"\u{43}",
    r"\u{1F600}",
    r"\u{10FFFF}",
    r"tab\there",
    r"quote\"inside",
    # errors
    r"\x",
    r"\xZZ",
    r"\x4",
    r"\u12",
    r"\uZZZZ",
    r"\u{}",
    r"\u{1234567}",
    r"\u{110000}",
    r"\u{D800}",
    r"\u{DFFF}",
    r"\q",
    "dangling\\",
]


def _python_record(line: str) -> str:
    decoded, err = _unescape_string(line)
    # BOTH lengths in BYTES, not codepoints — see the module docstring. `in=`
    # needs it as much as `out=`: a raw 'é' in the source is one codepoint to
    # Python and two bytes to the port.
    in_len = len(line.encode("utf-8"))
    out_len = len(decoded.encode("utf-8"))
    return f"in={in_len} out={out_len} err={err or ''} val={decoded}"


class TestBootstrapEscapes(TestCase):
    _TIMEOUT = 900

    @classmethod
    def setUpClass(cls):
        from tests.testutil import shared_bootstrap_binary
        cls.binary = shared_bootstrap_binary()

    def test_unesc_matches_python(self):
        stdin = "\n".join(_CASES)          # deliberately unterminated
        r = subprocess.run([self.binary, "unesc"], input=stdin,
                           capture_output=True, timeout=300, text=True,
                           env=_RUN_ENV)
        self.assertEqual(0, r.returncode, f"port unesc failed:\n{r.stdout[:800]}")

        port = r.stdout.splitlines()
        expected = [_python_record(line) for line in _CASES]
        self.assertEqual(len(expected), len(port),
                         f"record count differs (python {len(expected)}, "
                         f"port {len(port)})")
        for case, e, g in zip(_CASES, expected, port):
            with self.subTest(case=case):
                self.assertEqual(e, g, f"unesc differs for {case!r}")

    def test_error_cases_actually_error(self):
        """Guard the guard: if the corpus stopped containing invalid escapes,
        the comparison above would still pass while checking nothing about
        error text — which is the half that had drifted."""
        errored = [c for c in _CASES if _unescape_string(c)[1] is not None]
        self.assertGreaterEqual(len(errored), 10,
                                "error corpus shrank — escape error messages "
                                "would no longer be compared")
