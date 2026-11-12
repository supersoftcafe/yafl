"""`System::abort<T>(message)` — end the program with a message.

For a state the program cannot continue from: the message goes to stderr and
the process ends at once with exit code 1. It is typed as whatever the caller needs, so it
stands in an arm that cannot happen (the port's code generation uses it where
an earlier stage's bug would otherwise be emitted as a wrong program, #108).

Python, not a `[test]`: the program under test has to die.
"""
from __future__ import annotations

import os
import subprocess

from tests import testutil
from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_to_binary


_PROGRAM = (
    "import System\n"
    "import System::Containers\n"
    "fun pick(n: Int): String\n"
    "  ret n > 0 ? \"ok\" : abort<String>(\"pick: n must be positive\")\n"
    "fun main(): Int\n"
    "  print(pick(1) + \"\\n\")\n"
    "  ret length(pick(isEmpty(args()) ? 0 : 1))\n"
)


def _run(args: list[str], optimization_level: int) -> subprocess.CompletedProcess:
    binary = compile_to_binary(_PROGRAM, optimization_level=optimization_level)
    try:
        return subprocess.run([binary, *args], capture_output=True, timeout=5,
                              env=testutil._RUN_ENV, stdin=subprocess.DEVNULL)
    finally:
        os.unlink(binary)


class TestAbort(TestCase):

    def test_exits_1_with_the_message(self):
        for level in (0, 3):
            with self.subTest(optimization_level=level):
                run = _run([], level)
                self.assertEqual(1, run.returncode)
                self.assertEqual("pick: n must be positive\n", run.stderr.decode())

    def test_output_before_the_abort_is_kept(self):
        self.assertEqual("ok\n", _run([], 0).stdout.decode())

    def test_an_arm_not_taken_does_not_abort(self):
        for level in (0, 3):
            with self.subTest(optimization_level=level):
                run = _run(["x"], level)
                self.assertEqual(2, run.returncode)
                self.assertEqual("", run.stderr.decode())
