"""StringBuilder linearity tests.

The runtime behaviour (empty/short/heap/multi/regrowth/Int-append) is
covered by test_string_builder_runtime.TestAllStringBuilderRuntime in a
single compile. This file retains only the linear-type rejection checks
because each verifies a *compile* failure, which can't share a compile
with anything else.
"""
from __future__ import annotations

import io
import contextlib

import compiler as c

from tests.testutil import TimedTestCase as TestCase


class TestStringBuilderLinearity(TestCase):
    """The linear+terminal annotations are load-bearing — verify both
    misuse patterns are rejected."""

    def _reject(self, body: str, needle: str):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = c.compile([c.Input(body, "test.yafl")],
                             use_stdlib=True, just_testing=False)
        self.assertEqual("", code, "expected compile error, got C output")
        self.assertIn(needle, buf.getvalue().lower())

    def test_double_use_rejected(self):
        """Using the same builder twice violates linearity."""
        src = (
            "import System\n"
            "fun main(): System::Int\n"
            "    let sb = System::StringBuilder()\n"
            "    let s1 = System::toString(sb)\n"
            "    let s2 = System::toString(sb)\n"
            "    ret System::length(s1)\n"
        )
        self._reject(src, "times")

    def test_leak_rejected(self):
        """A builder that's allocated and never consumed must be rejected."""
        src = (
            "import System\n"
            "fun main(): System::Int\n"
            "    let sb = System::StringBuilder()\n"
            "    ret 0\n"
        )
        self._reject(src, "never used")
