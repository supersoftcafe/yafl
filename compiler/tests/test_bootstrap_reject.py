"""REJECTION parity — the two compilers must refuse the same programs.

Byte-identical C output says nothing about programs that should not compile at
all, and until this test there was no gate feeding either compiler an invalid
program through its C path. The hole that opened under it: the port's `c1`
pipeline ran NO check phase whatsoever. `let x = System::nosuchname` emitted C
and exited 0, where Python printed "Failed to resolve" and exited 1 — and the
same held for an undefined call, an undefined name inside a generic call, and
a plain type mismatch. Silent wrong codegen, the worst failure class, and the
existing contracts could not see it: test_bootstrap_check drives the port's
`check` mode directly, so it proved the check phase WORKS while saying nothing
about whether the C path ever calls it.

So this test deliberately goes through the C path on both sides — Python's
`compile()`, the port's `c1` — and asserts refusal, not just a diagnostic.

Both compilers print errors to STDOUT and exit non-zero (compiler.py's
__print_errors uses plain print; main.py exits 1 when compile_project returns
no code, so a build system cannot pick up a stale object file). The text is
compared too, since a refusal for the wrong reason is its own bug.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import compiler as c

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import _RUN_ENV

_REPO = Path(__file__).parent.parent.parent
_STDLIB = _REPO / "compiler" / "stdlib"

_PRELUDE = "namespace Test\nimport System\n\n"

# Each case is (name, body) where body sits inside main(). Every one of these
# leaked through the port's C path before the gate was added.
_INVALID = [
    ("bare_undefined_name",     "  let x = System::nosuchname"),
    ("undefined_call",          "  let x = System::nosuchname(1)"),
    ("undefined_two_arg_call",  "  let x = System::list2(1, 2)"),
    ("undefined_in_generic",
     "  let x = fold(System::list2(1,2), 0,"
     " (a: System::Int, b: System::Int) => a)"),
    ("type_mismatch",           "  let x: System::Bool = 5"),
    ("undefined_type",          "  let x: System::NoSuchType = 5"),
]


def _program(body: str) -> str:
    return f"{_PRELUDE}fun main(): System::Int\n{body}\n  ret 0\n"


def _stream(text: str) -> str:
    """stdlib + the case, as the `#FILE#`-marked stream mode c1 expects.

    Python loads the stdlib itself via use_stdlib; the port is handed a whole
    program, so the two see the same sources either way."""
    def terminated(t: str) -> str:
        return t if t.endswith("\n") else t + "\n"
    parts = [f"#FILE# {p.name}\n{terminated(p.read_text())}"
             for p in sorted(_STDLIB.glob("*.yafl"))]
    parts.append(f"#FILE# case.yafl\n{terminated(text)}")
    return "".join(parts)


class TestBootstrapReject(TestCase):
    _TIMEOUT = 1800

    @classmethod
    def setUpClass(cls):
        from tests.testutil import shared_bootstrap_binary
        cls.binary = shared_bootstrap_binary()

    def _port(self, text: str) -> subprocess.CompletedProcess:
        return subprocess.run([self.binary, "c1"], input=_stream(text),
                              capture_output=True, timeout=300, text=True,
                              env=_RUN_ENV)

    def test_both_reject_invalid_programs(self):
        for name, body in _INVALID:
            with self.subTest(case=name):
                text = _program(body)

                py = c.compile([c.Input(text, "case.yafl")], use_stdlib=True,
                               just_testing=False, optimization_level=1)
                self.assertFalse(
                    py, f"{name}: PYTHON accepted a program it must reject")

                r = self._port(text)
                self.assertNotEqual(
                    0, r.returncode,
                    f"{name}: PORT exited 0 on a program Python rejects\n"
                    f"  emitted {len(r.stdout)} bytes of C")
                self.assertNotIn(
                    "#include", r.stdout,
                    f"{name}: PORT emitted C for a rejected program")

    def test_valid_program_still_compiles(self):
        """The gate must refuse invalid programs, not everything — without this
        a check phase that always failed would pass the test above."""
        text = _program("  let x = 1")

        py = c.compile([c.Input(text, "case.yafl")], use_stdlib=True,
                       just_testing=False, optimization_level=1)
        self.assertTrue(py, "python rejected a valid program")

        r = self._port(text)
        self.assertEqual(0, r.returncode,
                         f"port rejected a valid program:\n{r.stdout[:2000]}")
        self.assertIn("#include", r.stdout, "port emitted no C for a valid program")
