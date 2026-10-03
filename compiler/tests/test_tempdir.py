"""compiler/tempdir.py — this process's private temp folder."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import tempdir
from tests.testutil import compile_and_run_stdlib_capture

_COMPILER = Path(__file__).parent.parent


class TestTempdir(unittest.TestCase):
    def test_one_private_folder_per_process(self):
        p = tempdir.process_temp_dir()
        self.assertEqual(p, tempdir.process_temp_dir())
        self.assertTrue(p.is_dir())
        self.assertEqual(Path(tempfile.gettempdir()), p.parent)
        self.assertTrue(p.name.startswith(f"yafl-{os.getpid()}-"), p.name)
        self.assertEqual(0o700, p.stat().st_mode & 0o777)

    def test_the_folder_is_deleted_at_exit(self):
        with tempfile.TemporaryDirectory() as td:
            script = ("import tempdir\n"
                      "p = tempdir.process_temp_dir()\n"
                      "(p / 'a' / 'b').mkdir(parents=True)\n"
                      "(p / 'a' / 'b' / 'f').write_text('x')\n"
                      "print(p)\n")
            env = dict(os.environ, TMPDIR=td)
            r = subprocess.run([sys.executable, "-c", script], cwd=_COMPILER,
                               env=env, capture_output=True, text=True, check=True)
            made = Path(r.stdout.strip())
            self.assertEqual(Path(td), made.parent)
            self.assertFalse(made.exists(), f"{made} survived its process")
            self.assertEqual([], list(Path(td).iterdir()))

    def test_a_fork_child_does_not_delete_its_parents_folder(self):
        p = tempdir.process_temp_dir()
        (p / "keep").write_text("x")
        pid = os.fork()
        if pid == 0:
            # What the inherited atexit handler does when the child exits.
            tempdir._cleanup(p, tempdir._owner)
            os._exit(0)
        _, status = os.waitpid(pid, 0)
        self.assertEqual(0, status)
        self.assertTrue((p / "keep").exists())


class TestSystemTempDir(unittest.TestCase):
    """`System::tempDir()` — the runtime side (yafllib/tempdir.c)."""

    _PROG = (
        "import System\n"
        "fun main(): System::Int\n"
        "    ret match(System::tempDir())\n"
        "        (p: System::String) => match(System::tempDir())\n"
        "            (q: System::String) => (System::print(p + \"\\n\"), p == q ? 0 : 2)\n"
        "                |> (_, rc) => rc\n"
        "            (n: System::None)   => 3\n"
        "        (n: System::None)   => 1\n"
    )

    def test_a_program_gets_one_folder_deleted_at_exit(self):
        with tempfile.TemporaryDirectory() as td:
            rc, out = compile_and_run_stdlib_capture(self._PROG, env={"TMPDIR": td})
            self.assertEqual(0, rc, out)
            made = Path(out.strip())
            self.assertEqual(Path(td), made.parent)
            self.assertRegex(made.name, r"^yafl-\d+-")
            self.assertEqual([], list(Path(td).iterdir()),
                             "the folder survived its process")


if __name__ == "__main__":
    unittest.main()
