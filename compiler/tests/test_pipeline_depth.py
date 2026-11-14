"""Compile time does not grow exponentially with pipeline depth (#119).

The program is tests/corpus_converge/pipeline_depth.yafl: sixteen `|>`
stages, nested sixteen blocks deep. Before the fix the AST inliner re-walked
every nested block once per enclosing block and this did not compile within
hours; the CPU budget of this test is what catches a regression. The C parity
harnesses (test_bootstrap_c_o*) compile the same file with both compilers.
"""
from __future__ import annotations

from pathlib import Path

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib

_PROGRAM = (Path(__file__).parent / "corpus_converge" / "pipeline_depth.yafl").read_text()


class TestPipelineDepth(TestCase):

    def test_sixteen_stage_pipeline_compiles_and_runs(self):
        self.assertEqual(0, compile_and_run_stdlib(_PROGRAM))
