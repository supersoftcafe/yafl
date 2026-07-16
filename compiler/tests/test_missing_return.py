"""A function with a declared result whose body never yields a value (a
trailing expression STATEMENT without `ret`) must be a check error naming the
function — not a codegen crash. Found porting generate_expr2.yafl: three
helpers ended in a bare tail-call statement; check passed them and Python's
codegen died building `Return(None)` (ops.py Return.__post_init__ ValueError).
"""
from __future__ import annotations

import contextlib
import io

import compiler as c
from tests.testutil import TimedTestCase as TestCase


def _errors(src: str) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        c.compile([c.Input(src, "test.yafl")], use_stdlib=True, just_testing=True)
    return buf.getvalue()


class TestMissingReturn(TestCase):
    def test_missing_ret_is_a_check_error(self):
        # `helper` ends in a bare call statement — no `ret` — but declares Int.
        errs = _errors(
            "namespace Main\nimport System\n"
            "fun helper(a: System::Int): System::Int\n"
            "  let b = a + 1\n"
            "  ignore(b)\n"
            "fun ignore(x: System::Int): System::Int\n"
            "  ret x\n"
            "fun main(): System::Int\n"
            "  ret helper(1)\n")
        self.assertIn("return", errs.lower())
        self.assertNotIn("Traceback", errs)

    def test_ret_present_still_compiles(self):
        errs = _errors(
            "namespace Main\nimport System\n"
            "fun helper(a: System::Int): System::Int\n"
            "  let b = a + 1\n"
            "  ret b\n"
            "fun main(): System::Int\n"
            "  ret helper(1)\n")
        self.assertEqual("", errs)
