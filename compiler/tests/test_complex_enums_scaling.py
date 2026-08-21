"""An interconnected enum graph must not blow the compiler up exponentially.

TWO passes rewrite types nested in an enum's `all_fields` by walking the enum
reference graph: `lowering/complex_enums.py` (which enums must go on the heap)
and `EnumSpec.replace_in_all_fields` (used by `lowering/simple_classes.py`).
Both guarded CYCLES with a `visited` set — but neither guarded REDUNDANCY, so
each re-derived a shared subgraph once per PATH that reached it, and the number
of paths through an interconnected enum graph is exponential in the number of
enums. Measured on this shape before the fix: memory DOUBLED for every two
enums added (n=8:128MB, n=10:284MB, n=12:606MB, n=14:1185MB), and n>=16 did not
finish inside 200s.

Nothing in the corpus had such a graph, so every test looked healthy — the
bootstrap compiler was the first program to expose it (65 enum roots; 10.1GB
and 604s to compile, ~90% of it in these two walks). Memoising each rewrite on
(spec, path) collapses the walk back to the size of the graph: the bootstrap
now compiles in 357MB / 149s, emitting byte-identical C.

This pins the shape. The budget is CPU time (TimedTestCase meters ITIMER_PROF,
not wall clock), so the verdict does not depend on machine load.
"""
from __future__ import annotations

from tests.testutil import BatchedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


def _dense_enum_graph(n: int) -> str:
    """`n` enums, each variant carrying a union of EVERY other enum — many
    PATHS through a graph with few NODES, which is exactly the shape whose
    path count explodes while its size stays trivial."""
    names = [chr(ord("A") + i) for i in range(n)]
    out = ["namespace Test", "import System", ""]
    for nm in names:
        union = "|".join(x for x in names if x != nm) + "|None"
        out += [f"enum {nm}",
                f"  enum {nm}1({nm.lower()}1x: {union})",
                f"  enum {nm}2({nm.lower()}2x: {union})",
                ""]
    out += ["fun pick(a: A): Int",
            "  ret match(a)",
            "    (x: A1) => 1",
            "    (y: A2) => 2",
            "",
            "fun main(): Int",
            '  print(String(pick(A1(None))) + "\\n")',
            "  ret 0"]
    return "\n".join(out) + "\n"


class TestComplexEnumScaling(TestCase):
    # Post-fix this compiles in ~60s CPU. Pre-fix it did not finish in 200s and
    # was still doubling — so the budget bites on a regression without being
    # tight enough to be flaky.
    _TIMEOUT = 150

    def test_dense_enum_graph_does_not_explode(self):
        rc, out = compile_and_run_stdlib_capture(_dense_enum_graph(16))
        self.assertEqual(0, rc)
        self.assertEqual("1\n", out)
