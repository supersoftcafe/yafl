"""Regression: the -O3 stub launch must declare its `$sv_discard` target.

A large, looping, genuinely-async function whose result needs a synthesised
task subtype is lowered onto the "stub launch" springboard at -O3. That
springboard allocates the task via `task_init`, discarding the result through
`$sv_discard` — a `keep=True` write kept only for the side effect. The launcher
must DECLARE `$sv_discard` among its C stack vars; otherwise clang rejects the
generated C with `use of undeclared identifier '_sv_discard'`.

Found by examples/ylisp.yafl at -O3 (its `_evalArgs`/`readForm`/`main` all land
on the stub with tuple/union results). Reproduced minimally here by forcing the
stub threshold to zero so a small program exercises the same path.
"""
import subprocess
import unittest
from pathlib import Path

import compiler as c
import lowering.async_lower as async_lower

_YAFLLIB_DIR = Path(__file__).parent.parent.parent / "yafllib"

# `_spin` returns a tuple `(IO, Int)` (→ a synthesised task subtype, the path
# that emits the `$sv_discard = task_init(...)` write), is `[tail]`-looping
# (a back edge) and genuinely async (`writeAll` suspends). It is called from
# two sites so it is not inlined away — exactly the shape that reaches the stub
# launcher.
_SRC = """\
namespace Main
import System
import System::IO

fun [tail] _spin(io: IO, n: System::Int): (io: IO, r: System::Int)
  ret n < 1
    ? (io, n)
    : writeAll(io, "x") |> (io2, res) => _spin(io2, n - 1)

fun main(): System::Int
  ret stdout()
    |> (o) => _spin(o, 3)
    |> (o, r1) => _spin(o, 2)
    |> (o, r2) => (o.close(), r2)
    |> (c, r) => r
"""


class TestStubLaunchO3(unittest.TestCase):
    def test_stub_launch_declares_sv_discard(self):
        # Force any qualifying async function onto the stub launch so a small
        # program exercises the path (the real threshold needs a ~256-op body).
        saved = async_lower._STUB_THRESHOLD_OPS
        async_lower._STUB_THRESHOLD_OPS = 0
        try:
            c_code = c.compile([c.Input(_SRC, "stub.yafl")], use_stdlib=True,
                               just_testing=False, optimization_level=3)
        finally:
            async_lower._STUB_THRESHOLD_OPS = saved

        self.assertTrue(c_code, "compilation produced no C")
        # Guard: the test only means something if it actually reaches the
        # stub launcher's synthesised-subtype task_init (the site of the bug).
        self.assertIn("_sv_discard = task_init", c_code,
                      "test no longer exercises the stub-launch task_init path")

        result = subprocess.run(
            ["clang", "-std=c11", "-Wall", "-Wextra", "-Werror",
             "-x", "c", "-", "-O0", "-fsyntax-only", "-I", str(_YAFLLIB_DIR)],
            input=c_code, text=True, capture_output=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0,
                         f"clang rejected the -O3 stub-launch C:\n{result.stderr}")
        self.assertNotIn("_sv_discard", result.stderr)


if __name__ == "__main__":
    unittest.main()
