"""bootstrap c-mode warnings: a fixed divergence, plus -W flag coverage.

postmonoGate used to compute the check phase's surviving warnings and drop
them on the floor for every C-emitting mode (c/c1/c2/c3, ctest, project*) —
main.py has always printed them (main.py:75-76). This pins the fix: the
bootstrap binary now writes them to stderr, matching compiler.py's own
`compile_project` warnings byte for byte, while leaving stdout (the C output)
untouched — see test_bootstrap_c_o0.py etc. for that byte-parity contract.

`c` mode compiles a statement SET the caller assembled (bootstrap_c_base.py's
own note): the stdlib has to be concatenated into the input stream by hand,
exactly as the byte-parity tests do via `_port_stream`.
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import compiler as c
import warning_flags as wf
from tests.bootstrap_c_base import _port_stream
from tests.testutil import TimedTestCase as TestCase
from tests.testutil import _RUN_ENV


_SOURCE = (
    "namespace Main\n"
    "import System\n"
    "fun f(a: System::Int, b: System::Int): System::Int\n"
    "  ret a\n"
    "fun main(): System::Int\n"
    "  let x = 5\n"
    "  ret f(1, 2)\n")


class TestBootstrapCWarnings(TestCase):
    _TIMEOUT = 300

    @classmethod
    def setUpClass(cls):
        from tests.testutil import shared_bootstrap_binary
        cls.binary = shared_bootstrap_binary()
        cls._tmpdir = tempfile.TemporaryDirectory()
        cls._source_path = Path(cls._tmpdir.name) / "wtest.yafl"
        cls._source_path.write_text(_SOURCE)
        cls._stream = _port_stream(cls._source_path)

    @classmethod
    def tearDownClass(cls):
        cls._tmpdir.cleanup()

    def _python_warnings(self, warn_flags: tuple[str, ...] = ()) -> str:
        enabled = wf.resolve_enabled_warnings(list(warn_flags))
        _code, _link, warns = c.compile_project(
            [c.Input(_SOURCE, "wtest.yafl")], use_stdlib=True, just_testing=True,
            enabled_warnings=enabled)
        return "".join(f"{w}\n" for w in sorted(set(warns)))

    def _run_c(self, *w_args: str):
        return subprocess.run([self.binary, "c", *w_args], input=self._stream,
                              capture_output=True, timeout=self._TIMEOUT, text=True,
                              env=_RUN_ENV)

    def test_c_mode_prints_warnings_on_stderr(self):
        # unused-variable defaults on; unused-parameter defaults off. The
        # divergence: the bootstrap binary used to print NOTHING here.
        expected = self._python_warnings()
        self.assertIn("'x' is never used", expected)
        self.assertNotIn("parameter 'b' is never used", expected)
        r = self._run_c()
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertEqual(expected, r.stderr)
        self.assertTrue(r.stdout, "C output must still be produced")

    def test_wflag_reaches_c_mode(self):
        expected = self._python_warnings(("unused-parameter",))
        self.assertIn("parameter 'b' is never used", expected)
        r = self._run_c("-Wunused-parameter")
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertEqual(expected, r.stderr)
        # -W must not change the emitted C itself.
        self.assertEqual(self._run_c().stdout, r.stdout)

    def test_wno_all_silences_c_mode(self):
        r = self._run_c("-Wno-unused-variable")
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertEqual("", r.stderr)

    def test_unknown_wflag_fails_before_compiling(self):
        r = self._run_c("-Wbogus")
        self.assertNotEqual(0, r.returncode)
        self.assertIn("unknown warning", r.stderr)
        self.assertEqual("", r.stdout)
