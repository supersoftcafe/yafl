"""System::Test's runner (compiler/libs/system-test/test.yafl): every test runs
in a SUBPROCESS of the test binary (docs/testing-proposal.md §7, user ruling).

The runner relaunches its own binary once per test, so a test that crashes
fails alone and the run goes on; a test's stdout and stderr are captured and
reported with its result; and each test's line is written once, whole, after
the test has finished — nothing announces a test before it runs.

The probe below covers each outcome: a pass, an assertion failure, a pass that
writes to both streams, and a crash (an integer division by zero aborts). A
test may also declare the stdout it must produce, `[test("…", stdout = "…")]`:
the runner compares what it captured, so a program that prints is checked as
written.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import _compile, compile_errors


_PROBE = """\
namespace RunnerProbe

import System
import System::IO
import System::Test

fun [impure] chatter(): Int
    println("out line")
    ret match(writeAll(stderr(), "err line\\n").io.close())
        (e: IOError) => 1
        ()           => 0

fun boom(z: Int): Int
    ret 100 / z

fun [test("passes")] passes(): None|TestFailure
    ret assertEqInt(1 + 1, 2, "sum")

fun [test("fails")] fails(): None|TestFailure
    ret assertEqInt(1 + 1, 3, "sum")

fun [test("prints, then passes")] prints(): None|TestFailure
    ret assertEqInt(chatter(), 0, "chatter")

fun [test("crashes")] crashes(): None|TestFailure
    let zero = 0
    ret assertEqInt(boom(zero), 1, "never reached")

fun [test("prints what it declares", stdout = "out line\\n")] printsAsDeclared(): None|TestFailure
    ret assertEqInt(chatter(), 0, "chatter")

fun [test(stdout = "something else\\n")] printsOtherwise(): None|TestFailure
    ret assertEqInt(chatter(), 0, "chatter")
"""

_IDS = {f"RunnerProbe::{n}" for n in ("passes", "fails", "prints", "crashes",
                                      "printsAsDeclared", "printsOtherwise")}


class TestTestRunner(TestCase):
    _TIMEOUT = 600

    @classmethod
    def setUpClass(cls):
        cls._dir = tempfile.TemporaryDirectory()
        cls.binary = str(Path(cls._dir.name) / "probe")
        r = _compile(_PROBE, "probe.yafl", ["-o", cls.binary], 0, False, (), True,
                     Path(cls._dir.name))
        assert r.returncode == 0, r.stdout + r.stderr

    @classmethod
    def tearDownClass(cls):
        cls._dir.cleanup()

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([self.binary, *args], capture_output=True, text=True,
                              timeout=120, stdin=subprocess.DEVNULL)

    def _events(self, *args: str) -> tuple[int, list[dict]]:
        r = self._run("--format", "json", *args)
        return r.returncode, [json.loads(line) for line in r.stdout.splitlines()]

    def _ends(self, events: list[dict]) -> dict[str, dict]:
        return {e["id"]: e for e in events if e["event"] == "test_end"}

    def test_a_crash_fails_alone_and_the_run_goes_on(self):
        rc, events = self._events()
        self.assertEqual(1, rc)
        ends = self._ends(events)
        self.assertEqual(_IDS, set(ends))
        self.assertEqual("pass", ends["RunnerProbe::passes"]["status"])
        self.assertEqual("pass", ends["RunnerProbe::prints"]["status"])
        self.assertEqual("fail", ends["RunnerProbe::fails"]["status"])
        crash = ends["RunnerProbe::crashes"]
        self.assertEqual("fail", crash["status"])
        self.assertIn("crashed", crash["message"])
        self.assertIn("Division by zero", crash["stderr"])
        self.assertEqual({"event": "run_end", "passed": 3, "failed": 3}, events[-1])

    def test_output_is_captured_into_the_result(self):
        _, events = self._events()
        prints = self._ends(events)["RunnerProbe::prints"]
        self.assertEqual("out line\n", prints["stdout"])
        self.assertEqual("err line\n", prints["stderr"])
        quiet = self._ends(events)["RunnerProbe::passes"]
        self.assertEqual("", quiet["stdout"])
        self.assertEqual("", quiet["stderr"])

    def test_a_failure_carries_its_message_and_location(self):
        _, events = self._events()
        fails = self._ends(events)["RunnerProbe::fails"]
        self.assertEqual("sum", fails["message"])
        self.assertEqual("expected 3, got 2", fails["detail"])
        self.assertEqual("probe.yafl", fails["file"])

    def test_no_test_is_announced_before_it_runs(self):
        _, events = self._events()
        self.assertEqual({"run_start", "test_end", "run_end"}, {e["event"] for e in events})
        self.assertEqual({"event": "run_start", "count": 6}, events[0])

    def test_one_test_selected_by_id(self):
        rc, events = self._events("RunnerProbe::prints")
        self.assertEqual(0, rc)
        self.assertEqual({"RunnerProbe::prints"}, set(self._ends(events)))

    def test_human_report(self):
        r = self._run()
        self.assertEqual(1, r.returncode)
        self.assertIn("  ok    RunnerProbe::passes", r.stdout)
        self.assertIn("  FAIL  RunnerProbe::fails\n        sum: expected 3, got 2", r.stdout)
        self.assertIn("  FAIL  RunnerProbe::crashes", r.stdout)
        self.assertIn("Division by zero", r.stdout)
        self.assertTrue(r.stdout.endswith("3 passed, 3 failed\n"), r.stdout)
        # A passing test's output is not shown in the human report.
        self.assertIn("  ok    RunnerProbe::prints\n  FAIL  RunnerProbe::crashes", r.stdout)

    def test_declared_stdout_is_checked(self):
        _, events = self._events()
        ends = self._ends(events)
        self.assertEqual("pass", ends["RunnerProbe::printsAsDeclared"]["status"])
        other = ends["RunnerProbe::printsOtherwise"]
        self.assertEqual("fail", other["status"])
        self.assertEqual("stdout differs", other["message"])
        self.assertEqual('expected "something else\\n", got "out line\\n"', other["detail"])
        self.assertEqual("out line\n", other["stdout"])

    def test_listing_runs_nothing(self):
        r = self._run("--list")
        self.assertEqual(0, r.returncode)
        self.assertEqual(_IDS, {line.split("\t")[0] for line in r.stdout.splitlines()})
        self.assertEqual("", r.stderr)



class TestTestAttribute(TestCase):
    """`[test]` takes an optional description and an optional `stdout =`
    expectation, both strings; anything else is an error."""

    def _errors(self, attribute: str) -> str:
        return compile_errors(
            "namespace AttrProbe\nimport System\nimport System::Test\n"
            f"fun [{attribute}] t(): None|TestFailure\n    ret None\n", test=True)

    def test_accepted_shapes(self):
        for shape in ('test', 'test("d")', 'test("d", stdout = "x")', 'test(stdout = "x")'):
            with self.subTest(shape=shape):
                self.assertEqual("", self._errors(shape))

    def test_rejected_shapes(self):
        for shape in ('test(1)', 'test("a", "b")', 'test("a", out = "x")',
                      'test("a", stdout = 3)', 'test(stdout = "x", "d")',
                      'test("a", stdout = "x", stdout = "y")'):
            with self.subTest(shape=shape):
                self.assertIn("[test] takes", self._errors(shape))
