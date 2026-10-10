"""Pipeline placeholder: `x |> f(a, _)` slots the piped value into the `_`
argument position — a point-free stage needing no lambda. The `_` must be a
top-level argument of the stage's call, and at most one per stage. Lowered at
parse time to the same capture-avoiding block binding the lambda form uses.

The runtime behaviour is checked by compiler/yafl_tests/pipeline_placeholder.yafl.
"""
from __future__ import annotations



from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_errors


def _errors(src: str) -> str:
    return compile_errors(src)


class TestPipelinePlaceholderErrors(TestCase):
    def test_two_placeholders_in_one_stage_are_rejected(self):
        errs = _errors(
            "namespace Test\nimport System\n"
            "fun add2(a: Int, b: Int): Int\n  ret a + b\n"
            "fun main(): Int\n  ret 7 |> add2(_, _)\n")
        self.assertIn("placeholder", errs.lower())
