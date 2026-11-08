"""`[capacity]` fields and element writes with `:=` (issue #95).

A `[capacity]` field sizes an array class's storage past its length, and
`subject.items(i) := value` writes an element of it under the pin. The
runtime behaviour is checked by compiler/yafl_tests/array_append.yafl; the
compile errors are checked here, against whichever compiler is under test.
"""

from tests.testutil import TimedTestCase
from tests.testutil import compile_errors


def _errors(body: str) -> str:
    return compile_errors("""
namespace Main
import System
import System::Internal
""" + body + """

fun main(): System::Int
  ret 0
""")


class TestCapacityField(TimedTestCase):
    def test_capacity_must_be_int32(self):
        self.assertIn("a [capacity] field must be of type Int32", _errors("""
class [final] B(used: Int32, [capacity] cap: Int, items: Int[used])
"""))

    def test_capacity_needs_an_array_field(self):
        self.assertIn("a [capacity] field needs an array field to size", _errors("""
class [final] B(used: Int32, [capacity] cap: Int32)
"""))

    def test_one_capacity_field(self):
        self.assertIn("a class may have at most one [capacity] field", _errors("""
class [final] B(used: Int32, [capacity] c1: Int32, [capacity] c2: Int32, items: Int[used])
"""))

    def test_capacity_is_not_the_length(self):
        self.assertIn("the array's length field cannot be its [capacity] field", _errors("""
class [final] B([capacity] used: Int32, items: Int[used])
"""))


class TestElementAssign(TimedTestCase):
    def test_element_write_needs_a_late_write_class(self):
        self.assertIn("needs a [pinnable] or [mutable] class; 'B' is neither", _errors("""
class [final] B(used: Int32, [capacity] cap: Int32, items: Int[used])

fun f(b: B): None
  b.items(0i32) := 1
  ret None
"""))

    def test_element_write_names_the_array_field(self):
        self.assertIn("'other' is not an array field of 'B'", _errors("""
class [final, pinnable] B(used: Int32, [capacity] cap: Int32, items: Int[used])

fun other(b: B, i: Int32): Int
  ret 0

fun f(b: B): None
  b.other(0i32) := 1
  ret None
"""))

    def test_element_type_is_checked(self):
        self.assertIn("Incorrect type assigned to the element", _errors("""
class [final, pinnable] B(used: Int32, [capacity] cap: Int32, items: Int[used])

fun f(b: B): None
  b.items(0i32) := "text"
  ret None
"""))
