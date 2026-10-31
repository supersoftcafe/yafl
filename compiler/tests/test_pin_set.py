"""`__builtin_pin_set__(obj, obj.field, value)` is checked: a name, then a field
of it, in a class that admits a late write, the field holding a heap object or
None, and a value of the field's type. The behaviour of the fill is the
`[test]` in yafl_tests/pin_set.yafl; this pins what the compiler must REFUSE,
which a `[test]` cannot express, and the call it emits.
"""
from __future__ import annotations

import unittest

from tests.testutil import compile_c_result


def _compile(body: str, cls_attrs: str = "[pinnable] ", extra: str = "") -> tuple[object, str]:
    src = f"""namespace Main
import System
class {cls_attrs}Cell(value: System::Int, next: Cell|None, name: System::String|None)
class Small(n: System::Int32)
class [pinnable] Holder(small: Small|None, cell: Cell|None, both: Cell|Holder|None)
{extra}
fun f(c: Cell, h: Holder): System::Int
{body}
fun main(): System::Int
  ret f(Cell(1, None, None), Holder(None, None, None))
"""
    r = compile_c_result(src, "t.yafl")
    return r.c, r.stdout


class TestPinSet(unittest.TestCase):

    def test_a_pinnable_class_is_accepted(self):
        out, diag = _compile("  ret __builtin_pin_set__(c, c.next, Cell(2, None, None)) is None ? 1 : 0")
        self.assertTrue(out, diag)
        self.assertIn("object_pin_set(", out)
        self.assertIn("offsetof(", out)

    def test_a_mutable_class_is_accepted(self):
        out, diag = _compile("  ret __builtin_pin_set__(c, c.next, c) is None ? 1 : 0",
                             cls_attrs="[mutable] ")
        self.assertTrue(out, diag)

    def test_an_ordinary_class_is_refused(self):
        out, diag = _compile("  ret __builtin_pin_set__(c, c.next, c) is None ? 1 : 0", cls_attrs="")
        self.assertFalse(out)
        self.assertIn("[pinnable] or [mutable]", diag)

    def test_three_positional_arguments(self):
        for args in ("c, c.next", "c, c.next, c, c", "c, c.next, v = c"):
            with self.subTest(args=args):
                out, diag = _compile(f"  ret __builtin_pin_set__({args}) is None ? 1 : 0")
                self.assertFalse(out)
                self.assertIn("three arguments", diag)

    def test_the_field_must_be_of_the_named_object(self):
        for args in ("c, h.cell, c", "c, c, c", "f(c, h).next, c.next, c"):
            with self.subTest(args=args):
                out, diag = _compile(f"  ret __builtin_pin_set__({args}) is None ? 1 : 0")
                self.assertFalse(out)
                self.assertIn("a name, then a field of it", diag)

    def test_a_missing_field_is_refused(self):
        out, diag = _compile("  ret __builtin_pin_set__(c, c.nope, c) is None ? 1 : 0")
        self.assertFalse(out)
        self.assertIn("nope", diag)

    def test_the_field_must_hold_a_heap_object_or_none(self):
        # A bigint; a String; a class that may become a value struct; two
        # classes: none is one heap pointer whose empty case is NULL.
        for target, value in (("c.value", "3"), ('c.name', '"x"'),
                              ("h.small", "Small(1i32)"), ("h.both", "c")):
            subject = target.split(".")[0]
            with self.subTest(field=target):
                out, diag = _compile(
                    f"  ret __builtin_pin_set__({subject}, {target}, {value}) is None ? 1 : 0")
                self.assertFalse(out)
                self.assertIn("heap object or None", diag)

    def test_the_value_must_fit_the_field(self):
        out, diag = _compile("  ret __builtin_pin_set__(h, h.cell, h) is None ? 1 : 0")
        self.assertFalse(out)
        self.assertIn("Incorrect type assigned", diag)


if __name__ == "__main__":
    unittest.main()
