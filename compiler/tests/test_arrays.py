"""Array-as-final-class-attribute — step 1: parsing and representation.

An array is a trailing variable-length field of a `[final]` class, declared
`name: ElemType[lengthField]`, where `lengthField` names the Int32 field giving
the element count. This stage only covers parsing the syntax into an
`ArrayFieldSpec`, recording it on the class, and validating the structural rules
(`[final]`, a valid Int32 length field, at most one array field). Construction,
the generated accessor, and codegen come in later stages.

Runtime behaviour is checked by compiler/yafl_tests/arrays.yafl.
"""
from __future__ import annotations

from parsing.tokenizer import tokenize
import parsing.parser as parser
import pyast.typespec as t
import pyast.statement as s
import lowering.simple_classes as simple_classes

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture
from tests.testutil import compile_errors


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

    def _rejected(self, src: str, diagnostic: str) -> None:
        self.assertEqual(diagnostic + "\n", compile_errors(src, "t.yafl"))

    def test_non_final_array_class_is_rejected(self):
        self._rejected("""import System
class CustomArray(length: System::Int32, array: System::Int32[length])
fun main(): System::Int
  ret 0
""", "t.yafl[2:7] - a class with an array field must be [final]")

    def test_missing_length_field_is_rejected(self):
        self._rejected("""import System
class [final] CustomArray(label: System::String, array: System::Int32[length])
fun main(): System::Int
  ret 0
""", "t.yafl[2:50] - array length field 'length' is not a field of this class")

    def test_non_int32_length_field_is_rejected(self):
        self._rejected("""import System
class [final] CustomArray(length: System::Int, array: System::Int32[length])
fun main(): System::Int
  ret 0
""", "t.yafl[2:48] - array length field 'length' must be of type Int32")

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
        self._rejected(src, "t.yafl[2:7] - a class may have at most one array field")


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


class TestArrayAccess(TestCase):
    """Access: `obj.array(i)` reads element `i` (the "function out"), tabulated
    from the init function at construction, with a bounds check that aborts."""


    def test_out_of_bounds_aborts(self):
        rc, out = compile_and_run_stdlib_capture("""import System
class [final] IntArray(length: System::Int32, array: System::Int32[length])
fun main(): System::Int
  let a = IntArray(5i32, (i: System::Int32) => i)
  ret System::Int(a.array(10i32))
""", timeout=30)
        self.assertNotEqual(0, rc, "out-of-bounds read must abort, not return normally")
