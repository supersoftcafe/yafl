"""Two interfaces that give the SAME method a default body conflict in a class
that implements both: a call must be rejected until the class overrides the
method itself.

Member lookup keeps an inherited member visible unless an own member of the
same signature overrides it (so an inherited OVERLOAD with a default stays
reachable — yafl_tests/interface_default_overloads.yafl). That change must not
let a same-signature conflict through as if either default would do.
"""
from __future__ import annotations

import unittest

from tests.testutil import compile_c_result


_INTERFACES = """namespace Main
import System
interface A
  fun f(): String
    ret "a"
interface B
  fun f(): String
    ret "b"
"""


class TestInterfaceDefaultConflict(unittest.TestCase):

    def test_conflicting_defaults_are_rejected(self):
        src = _INTERFACES + """class C() : A|B
fun main(): Int
  System::println(C().f())
  ret 0
"""
        r = compile_c_result(src, "t.yafl")
        self.assertFalse(r.c, "a call that two defaults both answer must be rejected")
        self.assertIn("Ambiguous reference to field named f", r.stdout)

    def test_an_override_resolves_the_conflict(self):
        src = _INTERFACES + """class C() : A|B
  fun f(): String
    ret "c"
fun main(): Int
  System::println(C().f())
  ret 0
"""
        r = compile_c_result(src, "t.yafl")
        self.assertTrue(r.c, r.stdout)

    def test_an_overload_does_not_resolve_the_conflict(self):
        # `f(s)` overrides neither default: both stay visible, and `f()` is
        # still answered twice.
        src = _INTERFACES + """class C() : A|B
  fun f(s: String): String
    ret s
fun main(): Int
  System::println(C().f())
  ret 0
"""
        r = compile_c_result(src, "t.yafl")
        self.assertFalse(r.c, "an overload of another signature must not hide the conflict")


if __name__ == "__main__":
    unittest.main()
