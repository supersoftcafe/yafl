"""End-to-end project builds and the discovery worklist.

Covers the parts of the build system that go beyond the unit-level library model
in `test_libraries.py`: compiling without an explicit import (discovery via a
qualified reference), building a whole project directory through the real CLI
(static-linked against the discovered System library), and the ambiguity
diagnostic for a name that resolves more than one way.
"""
from __future__ import annotations

import io
import os
import subprocess
import sys
import contextlib
import tempfile
from pathlib import Path

import compiler as c
from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture

_COMPILER_DIR = Path(__file__).resolve().parent.parent


class TestDiscovery(TestCase):
    def test_compiles_without_import_via_qualified_reference(self):
        # No `import System` — only qualified references. The permissive worklist
        # must still pull System in (from the `System::` candidates) and compile.
        rc, out = compile_and_run_stdlib_capture("""fun main(): System::Int
  ret System::length("abcd")
""", timeout=30)
        self.assertEqual(4, rc, f"discovery via qualified ref failed; stdout:\n{out}")

    def test_ambiguous_reference_lists_candidates(self):
        # `thing` is provided by both A and B (same signature, both imported), so
        # it resolves two ways. There is no precedence rule — it's an error, and
        # the message must name both fully-qualified candidates so the user can
        # qualify it away.
        src = """namespace A
fun thing(): System::Int
  ret 1
namespace B
fun thing(): System::Int
  ret 2
namespace Main
import System
import A
import B
fun main(): System::Int
  ret thing()
"""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            out = c.compile([c.Input(src, "t.yafl")], use_stdlib=True)
        self.assertFalse(out, "ambiguous reference should be rejected")
        diag = buf.getvalue()
        self.assertIn("Ambiguous reference 'thing'", diag)
        self.assertIn("A::thing", diag)
        self.assertIn("B::thing", diag)


class TestProjectFolderBuild(TestCase):
    def test_builds_and_runs_a_multi_file_project(self):
        # Drive the real CLI: point `main.py` at a project directory, which gathers
        # every .yafl under it, discovers System on the search path, and statically
        # links the resulting binary.
        with tempfile.TemporaryDirectory() as d:
            proj = Path(d)
            (proj / "main.yafl").write_text(
                "import System\n"
                "fun main(): System::Int\n"
                "  let a = System::Array<System::Int32>(5i32, (i: System::Int32) => i * 2i32)\n"
                "  ret helper() + System::Int(a[3i32])\n", encoding="utf-8")
            (proj / "sub").mkdir()
            (proj / "sub" / "helper.yafl").write_text(
                "import System\nfun helper(): System::Int\n  ret 100\n", encoding="utf-8")

            binary = proj / "out"
            build = subprocess.run(
                [sys.executable, "main.py", str(proj), "-o", str(binary)],
                cwd=_COMPILER_DIR, capture_output=True, text=True, timeout=120)
            self.assertEqual(0, build.returncode,
                             f"project build failed:\n{build.stdout}\n{build.stderr}")
            self.assertTrue(binary.exists(), "expected an output binary")

            run = subprocess.run([str(binary)], capture_output=True, timeout=30)
            self.assertEqual(106, run.returncode,
                             f"expected helper()+a[3] == 100+6 == 106; got {run.returncode}")
