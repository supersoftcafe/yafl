"""The diagnostics contract for unresolved calls (item 7): a call whose
callee doesn't resolve to a single function must name the callee, the
argument types, and the candidate signatures — never the internal spec
class name. Replaces the opaque "Callable must be of type CallableSpec"."""
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


class TestCallDiagnostics(TestCase):
    def test_no_overload_names_args_and_candidates(self):
        errs = _errors(
            "namespace Main\nimport System\n"
            "fun isSpace(c: System::Int): System::Bool\n  ret c == ' '\n"
            "fun main(): System::Int\n  ret isSpace(32) ? 0 : 1\n")
        self.assertNotIn("CallableSpec", errs)
        self.assertIn("(Int, Int32)", errs)     # the actual argument types
        self.assertIn("candidates", errs)

    def test_calling_a_non_function_says_so(self):
        errs = _errors(
            "namespace Main\nimport System\n"
            "let x: System::Int = 5\n"
            "fun main(): System::Int\n  ret x(3)\n")
        self.assertNotIn("CallableSpec", errs)
        self.assertIn("not a function", errs)
        self.assertIn("Int", errs)

    def test_internal_spec_names_never_leak(self):
        # Any call-resolution failure: the message must be source-shaped.
        errs = _errors(
            "namespace Main\nimport System\n"
            "fun f(a: System::String): System::Int\n  ret 0\n"
            "fun main(): System::Int\n  ret f(5)\n")
        self.assertNotIn("CallableSpec", errs)
        self.assertNotIn("GenericPlaceholderSpec", errs)
        self.assertNotIn("BuiltinSpec", errs)
