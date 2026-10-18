"""Shared fixture + corpus comparison for the bootstrap C-emission tests.

NOT a test module — the filename deliberately does not match `test*.py`, so
discovery skips it and the base class is not collected twice. The
test_bootstrap_c_*.py modules each subclass this and contribute ONE test.

Split into separate MODULES rather than methods or classes because
unittest-parallel shards by module: as one module this was 24-37 minutes in
a single worker while the other four idled, and it set the floor for the
whole suite. --level=test would split it but does not preserve setUpClass;
--level=class cannot split a single-class module.

The contract: for every corpus program, the port's COMMAND LINE produces the
same exit code, diagnostics (stdout), warnings (stderr) and C as the Python
compiler's, at the module's optimisation level — the whole of compile_project:
library discovery and namespace pruning, convergence, checks, every lowering,
and codegen through the final Application.gen assembly (perfect-hash vtables,
extends-ordered emission, GC roots, main).

Both sides are the real compilers over `test_libraries()`. This used to drive
a hand-copied mirror of compiler.py's pipeline against the port's `c` modes,
with the whole stdlib concatenated into every program — a second copy of the
pipeline that drifted (it had no regex step), and a program that never got
the loader's pruning.

PYTHONHASHSEED=0 is asserted hard — Python's C output is only deterministic
under it (the known codegen-nondeterminism bug), and a flaky byte contract is
worse than none.
"""
from __future__ import annotations

import multiprocessing
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from tests.testutil import (compile_c_result, port_compiler_command, python_c_result,
                            Compiled, TimedTestCase as TestCase)

_REPO = Path(__file__).parent.parent.parent

_CORPUS = sorted((_REPO / "examples").glob("*.yafl")) \
    + sorted((Path(__file__).parent / "corpus_converge").glob("*.yafl"))


class BootstrapCBase(TestCase):
    _TIMEOUT = 3600

    @classmethod
    def setUpClass(cls):
        assert os.environ.get("PYTHONHASHSEED") == "0", (
            "test_bootstrap_c requires PYTHONHASHSEED=0 — Python's C output "
            "is only deterministic under it")
        cls.port = port_compiler_command()

    def _compare_corpus(self, optimization_level: int, profile: bool = False):
        # Every corpus file is independent, and per file the two compiles are
        # independent, so a bounded process pool takes both. Under a parallel
        # test runner this process is daemonic and cannot fork a pool — compile
        # serially instead. Results compare in corpus order, so the first diff
        # reported is always the simplest file's.
        kw = dict(optimization_level=optimization_level, profile=profile)
        jobs = [(path, side) for path in _CORPUS for side in ("python", "port")]
        if multiprocessing.current_process().daemon:
            done = {job: _compile_side(*job, self.port, kw) for job in jobs}
        else:
            with ProcessPoolExecutor(max_workers=4) as pool:
                futures = {job: pool.submit(_compile_side, *job, self.port, kw) for job in jobs}
                done = {job: f.result() for job, f in futures.items()}
        for path in _CORPUS:
            with self.subTest(file=path.name):
                self.assert_same_compile(done[(path, "python")], done[(path, "port")],
                                         f"{path.name}: -O{optimization_level}"
                                         + (" --profile" if profile else ""))

    def assert_same_compile(self, expected: Compiled, got: Compiled, what: str):
        self.assertEqual(expected.stdout, got.stdout, f"{what}: diagnostics differ")
        self.assertEqual(expected.stderr, got.stderr, f"{what}: warnings differ")
        self.assertEqual(expected.rc, got.rc, f"{what}: exit code differs")
        want, have = expected.c.splitlines(), got.c.splitlines()
        for i, (e, g) in enumerate(zip(want, have)):
            self.assertEqual(e, g, f"{what}: C differs at line {i + 1}")
        self.assertEqual(len(want), len(have),
                         f"{what}: C length differs (python {len(want)}, port {len(have)})")


def _compile_side(path: Path, side: str, port: list[str], kw: dict) -> Compiled:
    """One corpus file through one compiler's command line — module level, so
    a process pool can run it."""
    if side == "python":
        return python_c_result(path.read_text(), path.name, **kw)
    return compile_c_result(path.read_text(), path.name, command=port, **kw)
