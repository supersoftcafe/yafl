"""Array-as-final-class-attribute — step 1: parsing and representation.

An array is a trailing variable-length field of a `[final]` class, declared
`name: ElemType[lengthField]`, where `lengthField` names the Int32 field giving
the element count. This stage only covers parsing the syntax into an
`ArrayFieldSpec`, recording it on the class, and validating the structural rules
(`[final]`, a valid Int32 length field, at most one array field). Construction,
the generated accessor, and codegen come in later stages.
"""
from __future__ import annotations

from parsing.tokenizer import tokenize
import parsing.parser as parser
import pyast.typespec as t
import pyast.statement as s
import lowering.simple_classes as simple_classes

import compiler as c
from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


class TestArrayParsing(TestCase):
    def test_array_marker_on_a_field_yields_array_field_spec(self):
        # The `[lengthField]` marker is part of the field declaration, not the
        # type grammar, so it produces an ArrayFieldSpec around the element type.
        r = parser.parse_target_type_expr(tokenize("data: Int32[length]", "f"))
        self.assertIsInstance(r.value.declared_type, t.ArrayFieldSpec)
        self.assertEqual("length", r.value.declared_type.length_field)
        self.assertIsInstance(r.value.declared_type.element, t.NamedSpec)

    def test_array_marker_is_not_part_of_the_type_grammar(self):
        # A bare type never consumes a trailing `[...]`; `Int32` parses and the
        # `[length]` is left untouched. This keeps `[` special only in a field
        # declaration, so misplaced markers give local, useful errors.
        r = parser.parse_type(tokenize("Int32[length]", "f"))
        self.assertNotIsInstance(r.value, t.ArrayFieldSpec)
        self.assertEqual("[", r.tokens[0].value)

    def test_array_field_need_not_come_last(self):
        # The field may appear in any position; codegen moves it to the end.
        src = "class [final] CustomArray(array: Int32[length], length: Int32, label: String)\n"
        cls = parser.parse_statement(tokenize(src, "f")).value
        self.assertIsInstance(cls, s.ClassStatement)
        array_fields = [f for f in cls.parameters.flatten()
                        if isinstance(f.declared_type, t.ArrayFieldSpec)]
        self.assertEqual(1, len(array_fields))
        self.assertEqual("length", array_fields[0].declared_type.length_field)

    def test_array_class_records_the_field(self):
        src = "class [final] CustomArray(length: Int32, label: String, array: Int32[length])\n"
        cls = parser.parse_statement(tokenize(src, "f")).value
        self.assertIsInstance(cls, s.ClassStatement)
        self.assertIn("final", cls.attributes)
        array_fields = [f for f in cls.parameters.flatten()
                        if isinstance(f.declared_type, t.ArrayFieldSpec)]
        self.assertEqual(1, len(array_fields))
        self.assertEqual("length", array_fields[0].declared_type.length_field)


class TestArrayClassValidation(TestCase):
    """The structural rules are enforced at check time, before any codegen."""

    def _rejected(self, src: str) -> None:
        out = c.compile([c.Input(src, "t.yafl")], use_stdlib=True, just_testing=False)
        self.assertFalse(out, "expected this array class to be rejected")

    def test_non_final_array_class_is_rejected(self):
        self._rejected("""import System
class CustomArray(length: System::Int32, array: System::Int32[length])
fun main(): System::Int
  ret 0
""")

    def test_missing_length_field_is_rejected(self):
        self._rejected("""import System
class [final] CustomArray(label: System::String, array: System::Int32[length])
fun main(): System::Int
  ret 0
""")

    def test_non_int32_length_field_is_rejected(self):
        self._rejected("""import System
class [final] CustomArray(length: System::Int, array: System::Int32[length])
fun main(): System::Int
  ret 0
""")

    def test_two_array_fields_is_a_compiler_error_not_a_parse_error(self):
        # Two array fields parse cleanly (each field is independently an array);
        # the "at most one" rule is a compile-time check, so the parser must
        # accept it and the compiler must then reject it with a meaningful error.
        src = """import System
class [final] CustomArray(len1: System::Int32, a: System::Int32[len1], len2: System::Int32, b: System::Int32[len2])
fun main(): System::Int
  ret 0
"""
        parsed = parser.parse_statement(tokenize(
            "class [final] CustomArray(len1: Int32, a: Int32[len1], len2: Int32, b: Int32[len2])\n", "f"))
        self.assertEqual([], parsed.errors, "two array fields must parse without a parser error")
        self.assertIsInstance(parsed.value, s.ClassStatement)
        self._rejected(src)


class TestArrayClassNeverFlattened(TestCase):
    """An array class is always a heap object — `simple_classes` must never
    lower it to a flat value struct, even when it has few enough fields to
    otherwise qualify."""

    def test_two_field_array_class_survives_lowering(self):
        cls = parser.parse_statement(
            tokenize("class [final] CustomArray(length: Int32, array: Int32[length])\n", "f")).value
        out = simple_classes.lower_simple_classes([cls])
        self.assertTrue(any(isinstance(x, s.ClassStatement) for x in out),
                        "array class must not be flattened to a struct")

    def test_plain_small_class_is_still_flattened(self):
        # Control: an ordinary 2-field class IS flattened away, so the guard
        # above is what keeps the array class, not some unrelated condition.
        cls = parser.parse_statement(tokenize("class Point(x: Int32, y: Int32)\n", "f")).value
        out = simple_classes.lower_simple_classes([cls])
        self.assertFalse(any(isinstance(x, s.ClassStatement) for x in out),
                         "a plain small class should be flattened to a struct")


class TestArrayConstruction(TestCase):
    """Construction: `Class(length, …, initFn)` allocates the trailing storage
    with `array_create(vtable, length)` and tabulates it by calling the
    `(Int32): Elem` init function for each index. Element read-back is a later
    stage, so these verify allocation + fill completion via the length field."""

    def test_value_element_array_constructs(self):
        rc, out = compile_and_run_stdlib_capture("""import System
class [final] IntArray(length: System::Int32, array: System::Int32[length])
fun main(): System::Int
  let a = IntArray(5i32, (i: System::Int32) => i)
  ret System::Int(a.length)
""", timeout=30)
        self.assertEqual(5, rc, f"int array construction failed; stdout:\n{out}")

    def test_pointer_element_array_constructs(self):
        # String elements exercise the GC write barrier in the fill store.
        rc, out = compile_and_run_stdlib_capture("""import System
class [final] StrArray(length: System::Int32, array: System::String[length])
fun main(): System::Int
  let a = StrArray(4i32, (i: System::Int32) => "x")
  ret System::Int(a.length)
""", timeout=30)
        self.assertEqual(4, rc, f"string array construction failed; stdout:\n{out}")

    def test_generic_array_class_monomorphises_per_element(self):
        # A generic array class must specialise per element type, each emitting
        # its own vtable (constraint: generics must work).
        rc, out = compile_and_run_stdlib_capture("""import System
class [final] Arr<T>(length: System::Int32, array: T[length])
fun main(): System::Int
  let a = Arr<System::Int32>(3i32, (i: System::Int32) => i)
  let b = Arr<System::String>(7i32, (i: System::Int32) => "y")
  ret System::Int(a.length) + System::Int(b.length)
""", timeout=30)
        self.assertEqual(10, rc, f"generic array construction failed; stdout:\n{out}")


class TestArrayAccess(TestCase):
    """Access: `obj.array(i)` reads element `i` (the "function out"), tabulated
    from the init function at construction, with a bounds check that aborts."""

    def test_reads_back_tabulated_value(self):
        rc, out = compile_and_run_stdlib_capture("""import System
class [final] IntArray(length: System::Int32, array: System::Int32[length])
fun main(): System::Int
  let a = IntArray(5i32, (i: System::Int32) => i * 2i32)
  ret System::Int(a.array(3i32))
""", timeout=30)
        self.assertEqual(6, rc, f"expected a.array(3) == 6; stdout:\n{out}")

    def test_reads_pointer_element(self):
        rc, out = compile_and_run_stdlib_capture("""import System
class [final] Holder(length: System::Int32, array: System::String[length])
fun main(): System::Int
  let a = Holder(3i32, (i: System::Int32) => "ab")
  ret System::length(a.array(1i32))
""", timeout=30)
        self.assertEqual(2, rc, f"expected length(a.array(1)) == 2; stdout:\n{out}")

    def test_reads_back_when_array_field_is_not_last(self):
        # The array field is declared before its length and a trailing scalar;
        # construction and access must still work (codegen moves storage last).
        rc, out = compile_and_run_stdlib_capture("""import System
class [final] IntArray(array: System::Int32[length], length: System::Int32, tag: System::Int32)
fun main(): System::Int
  let a = IntArray((i: System::Int32) => i * 2i32, 5i32, 99i32)
  ret System::Int(a.array(3i32)) + System::Int(a.tag)
""", timeout=30)
        self.assertEqual(105, rc, f"expected a.array(3) + a.tag == 6 + 99; stdout:\n{out}")

    def test_out_of_bounds_aborts(self):
        rc, out = compile_and_run_stdlib_capture("""import System
class [final] IntArray(length: System::Int32, array: System::Int32[length])
fun main(): System::Int
  let a = IntArray(5i32, (i: System::Int32) => i)
  ret System::Int(a.array(10i32))
""", timeout=30)
        self.assertNotEqual(0, rc, "out-of-bounds read must abort, not return normally")
