"""Compile errors in interpolated strings (`$"…{expr}…"`, #126).

The behaviour lives in yafl_tests/string_interpolation.yafl; what a [test]
cannot check is a compile error, so the parse errors of a malformed slot and
the type errors of a slot that cannot render are pinned here — message and
position, the slot's own column, never the `show` call the lowering wrote.
"""
from __future__ import annotations

import unittest

from tests.testutil import compile_c_result


def _diagnostics(body: str) -> str:
    src = f"""namespace Main
import System
class Foo()
fun main(): Int
  let x = 1
  System::println({body})
  ret 0
"""
    r = compile_c_result(src, "t.yafl")
    assert not r.c, f"expected a compile error for {body}"
    return r.stdout


# `  System::println(` is 18 characters, so the literal starts at column 19 and
# its body (past `$"`) at 21.
_BODY = 21


class TestStringInterpolationErrors(unittest.TestCase):

    def test_unterminated_slot(self):
        out = _diagnostics('$"a {x b"')
        self.assertIn(f"t.yafl[6:{_BODY + 2}] - unterminated interpolation slot", out)

    def test_empty_slot(self):
        out = _diagnostics('$"a {} b"')
        self.assertIn(f"t.yafl[6:{_BODY + 2}] - empty interpolation slot", out)

    def test_empty_spec(self):
        out = _diagnostics('$"a {x:} b"')
        self.assertIn(f"t.yafl[6:{_BODY + 4}] - empty format spec after `:`", out)

    def test_slot_that_is_not_one_expression(self):
        out = _diagnostics('$"a {x +} b"')
        self.assertIn("t.yafl[6:", out)
        self.assertIn("interpolation slot", out)

    def test_nested_interpolated_string(self):
        out = _diagnostics('$"a {$"{x}"} b"')
        self.assertIn(f"t.yafl[6:{_BODY + 3}] - an interpolated string inside an interpolation slot", out)

    def test_brace_inside_a_slot(self):
        out = _diagnostics('$"a {x{ b"')
        self.assertIn(f"t.yafl[6:{_BODY + 4}] - `{{` inside an interpolation slot", out)

    def test_no_show_instance_names_the_slot(self):
        out = _diagnostics('$"a {Foo()} b"')
        self.assertIn(f"t.yafl[6:{_BODY + 2}] - cannot interpolate `Foo()`: no `show` accepts arguments (Foo)", out)

    def test_an_unresolved_name_is_reported_alone(self):
        # The slot's own error is the cause; the `show` call it feeds adds
        # nothing (an argument of unknown type makes every overload fit).
        out = _diagnostics('$"a {nope} b"')
        self.assertIn(f"t.yafl[6:{_BODY + 3}]", out)
        self.assertIn("nope", out)
        self.assertNotIn("cannot interpolate", out)
        self.assertNotIn("show", out)


if __name__ == "__main__":
    unittest.main()
