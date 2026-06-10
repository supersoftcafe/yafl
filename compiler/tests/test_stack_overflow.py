"""A true C-stack overflow (deep, non-suspending recursion — which runs on the C
stack via the synchronous async hot path) is turned by the runtime into a clean
diagnostic on stderr and exit code 134, instead of a bare SIGSEGV.

See yafllib/stackguard.c: a per-thread sigaltstack + SIGSEGV/SIGBUS handler.
"""
from __future__ import annotations

import os
import subprocess

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_to_binary, _RUN_ENV


# `1 + deep(n - 1)` is non-tail (the call is an argument), so it does NOT lower
# to a loop; being pure it never suspends, so it recurses on the C stack until it
# overflows.
_DEEP = """namespace Main
import System
fun deep(n: System::Int): System::Int
  ret n <= 0 ? 0 : 1 + deep(n - 1)
"""


class TestStackOverflow(TestCase):
    def _run(self, src: str) -> tuple[int, str]:
        binary = compile_to_binary(src)
        try:
            r = subprocess.run([binary], capture_output=True, timeout=30, env=_RUN_ENV)
            return r.returncode, r.stderr.decode("utf-8", "replace")
        finally:
            try:
                os.unlink(binary)
            except OSError:
                pass

    def test_main_thread_overflow_reports_cleanly(self):
        rc, err = self._run(_DEEP + "fun main(): System::Int\n  ret deep(100000000)\n")
        self.assertEqual(134, rc, f"expected clean overflow exit; stderr:\n{err}")
        self.assertIn("stack overflow", err)

    def test_worker_thread_overflow_reports_cleanly(self):
        # The recursion runs inside a __parallel__ branch, i.e. on a worker
        # thread — the original findstr crash site.
        src = _DEEP + (
            "fun main(): System::Int\n"
            "  let (a, b) = __parallel__(() => deep(100000000), () => 0)\n"
            "  ret a + b\n"
        )
        rc, err = self._run(src)
        self.assertEqual(134, rc, f"expected clean overflow exit; stderr:\n{err}")
        self.assertIn("stack overflow", err)
