"""`subject.field := value` is checked: only a field of a `[pinnable]` or
`[mutable]` class may be written after construction, and only with a value of
the field's type. The behaviour of the store (pin, check null, store, unpin) is
the `[test]` in yafl_tests/field_assign.yafl; this pins what the compiler must
REFUSE, which a `[test]` cannot express.
"""
from __future__ import annotations

import unittest

from tests.testutil import compile_c_result


def _compile(body: str, cls_attrs: str = "[pinnable] ") -> tuple[object, str]:
    src = f"""namespace Main
import System
class {cls_attrs}Cell(value: System::Int, next: Cell|None)
fun f(c: Cell): System::Int
{body}
fun main(): System::Int
  ret 0
"""
    r = compile_c_result(src, "t.yafl")
    return r.c, r.stdout


class TestFieldAssign(unittest.TestCase):

    def test_pinnable_class_is_accepted(self):
        out, diag = _compile("  c.next := Cell(2, None)\n  ret 0")
        self.assertTrue(out, diag)

    def test_mutable_class_is_accepted(self):
        out, diag = _compile("  c.value := 3\n  ret 0", cls_attrs="[mutable] ")
        self.assertTrue(out, diag)

    def test_an_ordinary_class_is_refused(self):
        out, diag = _compile("  c.value := 3\n  ret 0", cls_attrs="")
        self.assertFalse(out)
        self.assertIn("[pinnable] or [mutable]", diag)

    def test_the_left_must_be_a_field(self):
        out, diag = _compile("  let x = 1\n  x := 3\n  ret 0")
        self.assertFalse(out)
        self.assertIn("must be a field", diag)

    def test_a_missing_field_is_refused(self):
        out, diag = _compile("  c.nope := 3\n  ret 0")
        self.assertFalse(out)
        self.assertIn("nope", diag)

    def test_the_value_must_fit_the_field(self):
        out, diag = _compile('  c.value := "text"\n  ret 0')
        self.assertFalse(out)
        self.assertIn("Incorrect type assigned", diag)

    def test_a_narrow_value_converts_into_a_union_field(self):
        # `Cell` into `Cell|None`: accepted and converted.
        out, diag = _compile("  c.next := c\n  ret 0")
        self.assertTrue(out, diag)

    def test_it_is_a_statement_not_an_expression(self):
        out, diag = _compile("  let y = (c.value := 3)\n  ret 0")
        self.assertFalse(out)


if __name__ == "__main__":
    unittest.main()
