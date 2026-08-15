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

So this drives Python's own instance corpus — the ambient cases, the
constrained and generic ones, and both cases that must be REJECTED — through
each compiler's C path and requires them to agree. Rejection is checked as
carefully as acceptance: a compiler that accepts
`ambient-instance-for-a-caller-placeholder` is as broken as one that rejects
a valid program, and only the error cases pin the USER RULING that ambience
applies to concrete use sites only.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import compiler as c

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import _RUN_ENV

_REPO = Path(__file__).parent.parent.parent
_STDLIB = sorted((_REPO / "compiler" / "stdlib").glob("*.yafl"))


def _cases() -> dict[str, str]:
    """The source constants from the Python-side instance tests, so the corpus
    cannot drift away from the feature's own tests."""
    import tests.test_instance_stmt as m
    return {k: v for k, v in vars(m).items()
            if re.fullmatch(r"_[A-Z][A-Z0-9_]*", k) and isinstance(v, str)
            and "instance " in v}


def _stream(src: str) -> str:
    def terminated(t: str) -> str:
        return t if t.endswith("\n") else t + "\n"
    parts = [f"#FILE# {p.name}\n{terminated(p.read_text())}" for p in _STDLIB]
    parts.append(f"#FILE# case.yafl\n{terminated(src)}")
    return "".join(parts)


class TestBootstrapInstances(TestCase):
    _TIMEOUT = 1800

    @classmethod
    def setUpClass(cls):
        from tests.testutil import shared_bootstrap_binary
        cls.binary = shared_bootstrap_binary()

    def test_instance_corpus_agrees(self):
        cases = _cases()
        self.assertGreaterEqual(len(cases), 6,
                                "instance corpus went missing — the constants "
                                "in test_instance_stmt were renamed?")
        for name, src in sorted(cases.items()):
            with self.subTest(case=name):
                py = c.compile([c.Input(src, "case.yafl")], use_stdlib=True,
                               just_testing=False, optimization_level=1)
                r = subprocess.run([self.binary, "c1"], input=_stream(src),
                                   capture_output=True, timeout=600, text=True,
                                   env=_RUN_ENV)
                port_ok = r.returncode == 0
                self.assertEqual(
                    bool(py), port_ok,
                    f"{name}: python {'accepted' if py else 'rejected'} but "
                    f"port {'accepted' if port_ok else 'rejected'}\n"
                    f"port output: {r.stdout[:1500]}")

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
                py = c.compile([c.Input(src, "case.yafl")], use_stdlib=True,
                               just_testing=False, optimization_level=1)
                self.assertFalse(py, f"{const}: python accepted it")

                r = subprocess.run([self.binary, "c1"], input=_stream(src),
                                   capture_output=True, timeout=600, text=True,
                                   env=_RUN_ENV)
                self.assertNotEqual(0, r.returncode, f"{const}: port accepted it")
                self.assertIn(wanted, r.stdout,
                              f"{const}: port rejected it, but its diagnostic "
                              f"never mentions '{wanted}'")
