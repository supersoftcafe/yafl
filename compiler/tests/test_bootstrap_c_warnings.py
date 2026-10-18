"""bootstrap c-mode warnings: a fixed divergence, plus -W flag coverage.

postmonoGate used to compute the check phase's surviving warnings and drop
them on the floor for every C-emitting mode (c/c1/c2/c3, ctest, project*) —
main.py has always printed them (main.py:75-76). This pins the fix: the
bootstrap binary now writes them to stderr, matching compiler.py's own
`compile_project` warnings byte for byte, while leaving stdout (the C output)
untouched — see test_bootstrap_c_o0.py etc. for that byte-parity contract.

Both sides are the compilers' command lines over `test_libraries()`, as in
the byte-parity tests (bootstrap_c_base.py).
"""
from __future__ import annotations

from tests.testutil import (compile_c_result, port_compiler_command, python_c_result,
                            TimedTestCase as TestCase)


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
        cls.port = port_compiler_command()

    def _python(self, *warnings: str):
        return python_c_result(_SOURCE, "wtest.yafl", warnings=warnings)

    def _port(self, *warnings: str):
        return compile_c_result(_SOURCE, "wtest.yafl", warnings=warnings, command=self.port)

    def test_c_mode_prints_warnings_on_stderr(self):
        # unused-variable defaults on; unused-parameter defaults off. The
        # divergence: the bootstrap binary used to print NOTHING here.
        expected = self._python().stderr
        self.assertIn("'x' is never used", expected)
        self.assertNotIn("parameter 'b' is never used", expected)
        r = self._port()
        self.assertEqual(0, r.rc, r.describe())
        self.assertEqual(expected, r.stderr)
        self.assertTrue(r.c, "C output must still be produced")

    def test_wflag_reaches_c_mode(self):
        expected = self._python("unused-parameter").stderr
        self.assertIn("parameter 'b' is never used", expected)
        r = self._port("unused-parameter")
        self.assertEqual(0, r.rc, r.describe())
        self.assertEqual(expected, r.stderr)
        # -W must not change the emitted C itself.
        self.assertEqual(self._port().c, r.c)

    def test_wno_all_silences_c_mode(self):
        r = self._port("no-unused-variable")
        self.assertEqual(0, r.rc, r.describe())
        self.assertEqual("", r.stderr)

    def test_unknown_wflag_fails_before_compiling(self):
        r = self._port("bogus")
        self.assertNotEqual(0, r.rc)
        self.assertIn("unknown warning", r.stderr)
        self.assertEqual("", r.c)
