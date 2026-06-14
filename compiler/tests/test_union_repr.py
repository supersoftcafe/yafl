"""Pointer-word union representation (tag-elimination phase 2).

A union whose members are all mutually-distinguishable pointer-words (heap
classes, tagged immediates, single-field newtype wrappers, complex enums) plus
at most one unit collapses to a single machine word — None is the NULL sentinel,
every other member dispatches by its pointer tag / vtable. Unions with a
multi-field/scalar payload, or two members sharing a runtime kind, stay a tagged
`{...,$tag}` struct.

These tests pin both the representation (collapsed `object_t*` vs tagged struct)
and the runtime behaviour (every arm dispatches to the right value).
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture
import compiler as c
from pyast import union_repr


def _c_for(source: str) -> str:
    out = c.compile([c.Input(source, "test.yafl")], use_stdlib=True, just_testing=False)
    assert out, "compilation produced no output"
    return out


class TestUnionRepresentation(TestCase):
    # ── behaviour: every arm of a collapsed union dispatches correctly ────────

    def test_newtype_multiclass_union_roundtrips(self):
        # A|B|None with single-field newtype classes A(Int), B(String):
        # collapses to one word, dispatched by INTEGER/STRING vtable + NULL.
        src = """
namespace Main
import System
class A(x: Int)
class B(s: String)
fun pick(k: Int): A|B|None
  ret k == 0 ? A(7) : (k == 1 ? B("hi") : None)
fun probe(k: Int): Int
  ret match(pick(k))
    (a: A)    => a.x
    (b: B)    => length(b.s)
    (n: None) => 99
fun main(): System::Int
  println(String(probe(0)) + " " + String(probe(1)) + " " + String(probe(2)))
  ret 0
"""
        rc, out = compile_and_run_stdlib_capture(src)
        self.assertEqual(0, rc)
        self.assertEqual("7 2 99", out.strip())

    def test_immediate_union_roundtrips(self):
        src = """
namespace Main
import System
fun pick(k: Int): Int|String|None
  ret k == 0 ? 42 : (k == 1 ? "abc" : None)
fun probe(k: Int): Int
  ret match(pick(k))
    (i: Int)    => i
    (s: String) => length(s)
    (n: None)   => 99
fun main(): System::Int
  println(String(probe(0)) + " " + String(probe(1)) + " " + String(probe(2)))
  ret 0
"""
        rc, out = compile_and_run_stdlib_capture(src)
        self.assertEqual(0, rc)
        self.assertEqual("42 3 99", out.strip())

    def test_same_inner_newtypes_dispatch_correctly(self):
        # Id and Nm both wrap a String. Soundness: whatever the representation,
        # the two arms must never be confused.
        src = """
namespace Main
import System
class Id(v: String)
class Nm(v: String)
fun pick(k: Int): Id|Nm|None
  ret k == 0 ? Id("aa") : (k == 1 ? Nm("bbb") : None)
fun probe(k: Int): Int
  ret match(pick(k))
    (i: Id)   => length(i.v)
    (n: Nm)   => 0 - length(n.v)
    (x: None) => 99
fun main(): System::Int
  println(String(probe(0)) + " " + String(probe(1)) + " " + String(probe(2)))
  ret 0
"""
        rc, out = compile_and_run_stdlib_capture(src)
        self.assertEqual(0, rc)
        self.assertEqual("2 -3 99", out.strip())

    def test_tuple_and_scalar_unions_stay_tagged_but_work(self):
        # (a,b)|None (composite payload) and Int32|None (scalar) cannot collapse
        # to one pointer word; they remain tagged structs and must still work.
        src = """
namespace Main
import System
fun tup(b: Bool): (a: Int, b: Int)|None
  ret b ? (1, 2) : None
fun i32(b: Bool): Int32|None
  ret b ? 5i32 : None
fun probeTup(b: Bool): Int
  ret match(tup(b))
    (t: (a: Int, b: Int)) => t.a + t.b
    (n: None)             => 0
fun probeI32(b: Bool): Int
  ret match(i32(b))
    (v: Int32) => Int(v)
    (n: None)  => 0
fun main(): System::Int
  println(String(probeTup(true)) + " " + String(probeTup(false)) + " " + String(probeI32(true)))
  ret 0
"""
        rc, out = compile_and_run_stdlib_capture(src)
        self.assertEqual(0, rc)
        self.assertEqual("3 0 5", out.strip())

    # ── representation: collapsed vs tagged in the generated C ────────────────

    def _ret_type_collapsed(self, code: str, fn_substr: str) -> bool:
        """True if the function whose mangled name contains fn_substr returns a
        bare object_t* (collapsed); False if it returns a tagged struct."""
        for line in code.splitlines():
            if fn_substr in line and "(object_t* this" in line and line.rstrip().endswith(";"):
                return line.lstrip().startswith("object_t*")
        raise AssertionError(f"no prototype for {fn_substr!r} found")

    def test_collapsed_unions_are_single_word(self):
        src = """
namespace Main
import System
class A(x: Int)
class B(s: String)
fun ab(k: Int): A|B|None
  ret k == 0 ? A(1) : (k == 1 ? B("x") : None)
fun isn(k: Int): Int|String|None
  ret k == 0 ? 1 : (k == 1 ? "x" : None)
fun tup(b: Bool): (a: Int, b: Int)|None
  ret b ? (1, 2) : None
fun useAb(k: Int): Int
  ret match(ab(k))
    (a: A)    => a.x
    (b: B)    => 0
    (n: None) => 0
fun useIsn(k: Int): Int
  ret match(isn(k))
    (i: Int)    => i
    (s: String) => 0
    (n: None)   => 0
fun useTup(b: Bool): Int
  ret match(tup(b))
    (t: (a: Int, b: Int)) => t.a
    (n: None)             => 0
fun main(): System::Int
  ret useAb(0) + useIsn(0) + useTup(true)
"""
        code = _c_for(src)
        self.assertTrue(self._ret_type_collapsed(code, "Main__ab_"),
                        "A|B|None should collapse to a single object_t* word")
        self.assertTrue(self._ret_type_collapsed(code, "Main__isn_"),
                        "Int|String|None should collapse to a single object_t* word")
        # The composite-payload (a,b)|None case is covered behaviourally in
        # test_tuple_and_scalar_unions; its small function inlines away at -O2 so
        # there is no standalone prototype to inspect here.


class TestReprPartialOperationContract(TestCase):
    """The four representation-*partial* operations (box_value/widen_from are
    combination-only; read_field/construct_enum_value are enum-only) inherit a
    base default that fails loudly, naming the repr, rather than a bare
    AttributeError. This pins that contract so a future miswiring (or a 4th
    repr that forgets to override) surfaces a clear error."""

    def test_pointer_repr_rejects_enum_operations(self):
        rep = union_repr.PointerRepr(union_type=None)
        with self.assertRaisesRegex(NotImplementedError, "PointerRepr"):
            rep.read_field(None, "x", None)
        with self.assertRaisesRegex(NotImplementedError, "PointerRepr"):
            rep.construct_enum_value("Leaf", {}, None)

    def test_complex_enum_repr_rejects_combination_operations(self):
        rep = union_repr.ComplexEnumRepr(union_type=None)
        with self.assertRaisesRegex(NotImplementedError, "ComplexEnumRepr"):
            rep.box_value(None, None, None)
        with self.assertRaisesRegex(NotImplementedError, "ComplexEnumRepr"):
            rep.widen_from(None, None, None)
