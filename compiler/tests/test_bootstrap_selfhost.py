"""PORT 9 — the three-step self-host: stage2 ≡ stage3, byte-for-byte.

  stage1: the PYTHON compiler compiles bootstrap/*.yafl at -O1 → ybootstrap₁
          (this is exactly the cached shared_bootstrap_binary).
  stage2: ybootstrap₁ compiles the SAME sources (mode c1) → C₂ → clang → ybootstrap₂.
  stage3: ybootstrap₂ compiles the same sources again        → C₃.

C₂ == C₃ proves the compiler reached a FIXED POINT: the binary built by the
port behaves identically to the binary built by Python on the hardest input
there is — the compiler itself. This subsumes source-level parity and also
catches what only a compiled compiler can show: codegen bugs in paths only
the compiler's own sources exercise, runtime/GC misbehaviour under a
compiler-sized workload, and residual nondeterminism.

NOT in the default battery: a self-compile is GC-bound and takes hours on
this VM (baseline recorded in the session ledger), and it needs a compiler-
sized managed heap and C stack. Gated on YAFL_SELFHOST=1 so a discover run
skips it; run explicitly:

    YAFL_SELFHOST=1 PYTHONHASHSEED=0 python -m unittest tests.test_bootstrap_selfhost
"""
from __future__ import annotations

import os
import resource
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import _RUN_ENV, _CLANG_BUILD_FLAGS, static_link_for

_REPO = Path(__file__).parent.parent.parent
_SELF_TIMEOUT = 8 * 3600   # a self-compile stage is GC-bound; be generous

# A compiler-sized workload needs a big managed heap; the C-stack raise is
# shared (testutil.raise_stack_limit). The heap was 6 GiB until the final
# output-assembly append (one ~83 MB contiguous run) flaked on fragmentation;
# the banded allocator fixed that, 12 GiB is belt-and-braces.
_SELF_ENV = dict(_RUN_ENV, YAFL_HEAP_SIZE="12G")


def _stream() -> str:
    """The #FILE#-marked whole-program stream: stdlib then the bootstrap.
    Every part is newline-terminated — a file without a final newline would
    otherwise glue the next #FILE# marker onto its last line and the port
    would misattribute that whole file's statements."""
    def terminated(p: Path) -> str:
        text = p.read_text()
        return text if text.endswith("\n") else text + "\n"
    parts = [f"#FILE# {p.name}\n{terminated(p)}"
             for p in sorted((_REPO / "compiler" / "stdlib").glob("*.yafl"))]
    parts += [f"#FILE# {p.name}\n{terminated(p)}"
              for p in sorted((_REPO / "bootstrap").rglob("*.yafl"))]
    return "".join(parts)


def _compile_self(binary: str, text: str) -> str:
    r = subprocess.run([binary, "c1"], input=text, capture_output=True,
                       timeout=_SELF_TIMEOUT, text=True, env=_SELF_ENV)
    assert r.returncode == 0, f"self-compile exited {r.returncode}: {r.stdout[:500]}"
    return r.stdout


@unittest.skipUnless(os.environ.get("YAFL_SELFHOST") == "1",
                     "set YAFL_SELFHOST=1 to run the multi-hour self-host contract")
class TestBootstrapSelfhost(TestCase):
    _TIMEOUT = 3 * _SELF_TIMEOUT

    @classmethod
    def setUpClass(cls):
        assert os.environ.get("PYTHONHASHSEED") == "0", (
            "self-host requires PYTHONHASHSEED=0 (stage1 is Python-emitted)")
        from tests.testutil import shared_bootstrap_binary
        cls.stage1 = shared_bootstrap_binary()

    def test_stage2_equals_stage3(self):
        text = _stream()
        c2 = _compile_self(self.stage1, text)

        with tempfile.NamedTemporaryFile(suffix="", delete=False) as tmp:
            stage2 = tmp.name
        try:
            r = subprocess.run(
                ["clang", "-g", "-x", "c", "-", "-O0",
                 *_CLANG_BUILD_FLAGS, *static_link_for(1), "-o", stage2],
                input=c2, text=True, capture_output=True, timeout=600)
            self.assertEqual(0, r.returncode, f"clang on stage2 C failed:\n{r.stderr[:2000]}")

            c3 = _compile_self(stage2, text)
        finally:
            os.unlink(stage2)

        if c2 != c3:
            l2, l3 = c2.splitlines(), c3.splitlines()
            i = next((k for k, (a, b) in enumerate(zip(l2, l3)) if a != b),
                     min(len(l2), len(l3)))
            self.fail(f"stage2 != stage3 at line {i + 1}:\n"
                      f"  stage2 {l2[i] if i < len(l2) else '<eof>'!r}\n"
                      f"  stage3 {l3[i] if i < len(l3) else '<eof>'!r}\n"
                      f"  ({len(l2)} vs {len(l3)} lines)")
