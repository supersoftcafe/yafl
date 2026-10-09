"""A match's SUBJECT must be checked like any other expression.

A call to an undefined function in subject position must report a clean
"Failed to resolve" diagnostic at check time — not slip past the checks (which
never visited the subject) into a codegen crash when the subject is generated.
Regression for that gap: `MatchExpression.check` didn't check `self.subject`.
"""
from __future__ import annotations


from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_c_result


class TestMatchSubjectChecked(TestCase):
    def test_unresolved_match_subject_is_a_clean_error(self):
        src = ("namespace Main\n"
               "import System\n"
               "fun main(): System::Int\n"
               "  ret match(undefinedFunc(1))\n"
               "    (x: System::Int) => x\n")
        # Must NOT crash: the bug slipped an unresolved subject into codegen,
        # where it crashed casting a None type to CallableSpec.
        r = compile_c_result(src, "t.yafl")
        # Clean failure: no C emitted, and the diagnostic names the unresolved call.
        self.assertEqual((1, ""), (r.rc, r.c))
        out = r.stdout
        self.assertIn("resolve", out.lower())
        self.assertIn("undefinedFunc", out)
