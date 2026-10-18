"""INSTANCE parity — first-class `instance` statements must behave the same in
both compilers.

The `instance` feature is implemented on both sides and the stdlib has fully
migrated to it (45 instance statements; zero `let [trait]` declarations
remain). What was missing was any gate: no bootstrap test drove an instance
program through both compilers, so a divergence could sit unnoticed
indefinitely — and one did. The port's `checkOneWhere` matched a `where`
constraint against `[trait]` lets ONLY, never against first-class instances,
which is 512 failures on the bootstrap itself. It stayed invisible because the
port's C path ran no check phase at all (fixed alongside, see
test_bootstrap_reject); lowering already knew about instances, checking did
not.

Acceptance is gated by compiler/yafl_tests/instance_stmt.yafl — the ambient,
constrained and generic cases — which the suite builds and runs at every
level with whichever compiler it is given. This drives the cases that must be
REJECTED through each compiler's C path. Rejection is checked as carefully as
acceptance: a compiler that accepts `ambient-instance-for-a-caller-placeholder`
is as broken as one that rejects a valid program, and only the error cases pin
the USER RULING that ambience applies to concrete use sites only.
"""
from __future__ import annotations

from tests.testutil import (compile_c_result, port_compiler_command, python_c_result,
                            TimedTestCase as TestCase)


class TestBootstrapInstances(TestCase):
    _TIMEOUT = 1800

    @classmethod
    def setUpClass(cls):
        cls.port = port_compiler_command()

    def test_both_reject_ambient_for_a_caller_placeholder(self):
        """USER RULING: ambience applies to CONCRETE use sites only — a caller
        placeholder never matches an ambient instance; generic bodies get
        members solely via their own `where`. Both compilers must say so, and
        name the member that could not be resolved."""
        import tests.test_instance_stmt as m
        for const, wanted in (("_AMBIENT_NOT_FOR_GENERIC", "sizeOf"),
                              ("_NOT_AMBIENT_ERR", "tagOf")):
            with self.subTest(case=const):
                src = getattr(m, const)
                py = python_c_result(src, "case.yafl", optimization_level=1)
                self.assertNotEqual(0, py.rc, f"{const}: python accepted it")

                r = compile_c_result(src, "case.yafl", optimization_level=1, command=self.port)
                self.assertNotEqual(0, r.rc, f"{const}: port accepted it")
                self.assertIn(wanted, r.stdout,
                              f"{const}: port rejected it, but its diagnostic "
                              f"never mentions '{wanted}'")
