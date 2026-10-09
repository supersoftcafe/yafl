"""Named fields and default values are TUPLE-type features.

A tuple type may declare per-field defaults (`(x: Int, y: Int = 10)`); a tuple
value converging on such a receiver is transformed — positional entries bind
left to right, named entries bind by field name in any order after the
positionals, and every remaining unbound field fills from its default. Function
calling inherits all of this because parameters ARE a tuple: there is no
call-specific machinery.

A default must be a literal (Integer/Float/String/Bool) or a reference to a
`[const]` global let — nothing with captures, effects, or evaluation order.

The runtime behaviour is checked by compiler/yafl_tests/tuple_defaults.yafl;
these are the rejections.

Runtime behaviour is checked by compiler/yafl_tests/tuple_defaults.yafl.
"""
from __future__ import annotations


from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_errors


def _errors(src: str) -> str:
    return compile_errors(src)


_PRELUDE = "namespace Test\nimport System\n"


class TestTupleDefaultsErrors(TestCase):
    def test_default_must_be_literal_or_const(self):
        errs = _errors(_PRELUDE
            + "fun g(): Int\n  ret 3\n"
            + "fun f(x: Int = g()): Int\n  ret x\n"
            + "fun main(): Int\n  ret f()\n")
        self.assertIn("default", errs.lower())

    def test_unknown_named_field_is_rejected(self):
        errs = _errors(_PRELUDE
            + "fun f(x: Int, y: Int = 1): Int\n  ret x + y\n"
            + "fun main(): Int\n  ret f(1, nope = 2)\n")
        self.assertTrue(errs.strip(), "expected an error for an unknown field name")

    def test_double_binding_is_rejected(self):
        errs = _errors(_PRELUDE
            + "fun f(x: Int, y: Int = 1): Int\n  ret x + y\n"
            + "fun main(): Int\n  ret f(1, x = 2)\n")
        self.assertTrue(errs.strip(), "expected an error for binding x twice")

    def test_missing_required_field_is_rejected(self):
        errs = _errors(_PRELUDE
            + "fun f(x: Int, y: Int = 1): Int\n  ret x + y\n"
            + "fun main(): Int\n  ret f(y = 2)\n")
        self.assertTrue(errs.strip(), "expected an error for the missing x")


class TestTupleDefaultsOverloads(TestCase):
    def test_ambiguous_after_defaults_is_an_error(self):
        # With defaults considered, tag(7) matches both — must be reported,
        # never silently picked.
        errs = _errors(_PRELUDE
            + "fun tag(x: Int, pad: Int = 0): Int\n  ret x + pad\n"
            + "fun tag(x: Int): Int\n  ret x\n"
            + "fun main(): Int\n  ret tag(7)\n")
        self.assertTrue(errs.strip(), "expected an ambiguity error")
