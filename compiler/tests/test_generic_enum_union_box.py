"""A specialised generic-enum VALUE must box into a union of tuples.

`List<String>()` lowers to a NewEnumExpression whose type is read off the
specialised EnumStatement's _enum_spec. The specialisation renames the enum
ROOT but historically left the cloned VARIANT statements' names un-mangled,
so every _enum_spec rebuild collected ORIGINAL leaf names under the MANGLED
root. The stale spec then failed EnumSpec.trivially_assignable_from against
the (correctly leaf-mangled) declared result type, matching_tuple_variant
found no variant at emit time, and the tuple was silently NOT boxed into its
union container — invalid C (struct type mismatch), at every -O level.
"""
from __future__ import annotations

from tests.testutil import BatchedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


_SRC = """\
import System

class [final] Thing(tName: System::String)

fun probe(x: Thing|System::None, acc: List<Thing>): (ops: List<Thing>, moves: List<System::String>)|None
  ret match(x)
    (t: Thing)        => (prepend<Thing>(t, acc), List<System::String>())
    (n: System::None) => None

fun main(): System::Int
  let none: Thing|System::None = System::None
  let hit = match(probe(Thing("a"), List<Thing>()))
    (r: (ops: List<Thing>, moves: List<System::String>)) => 1
    ()                                                   => 9
  let miss = match(probe(none, List<Thing>()))
    (r: (ops: List<Thing>, moves: List<System::String>)) => 9
    ()                                                   => 2
  print(String(hit) + "\\n")
  print(String(miss) + "\\n")
  ret 0
"""


class TestGenericEnumUnionBox(TestCase):
    def test_specialised_enum_value_boxes_into_tuple_union(self):
        rc, out = compile_and_run_stdlib_capture(_SRC, timeout=30)
        self.assertEqual(0, rc, f"failed; stdout:\n{out}")
        self.assertEqual(["1", "2"], out.splitlines())
