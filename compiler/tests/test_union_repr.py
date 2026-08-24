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

from tests.testutil import BatchedTestCase as TestCase
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


class TestWideVariantBoxing(TestCase):
    """Per-variant boxing (the enum-encoding principle): a variant whose
    payload exceeds the value-struct threshold (8 words) becomes a heap
    object EVERYWHERE it appears — it contributes one pointer slot to the
    union pool instead of inflating every sibling with its fields. Variants
    at or under the threshold stay inline in the flat tagged struct.

    The boxed variant borrows the complex-enum leaf-object machinery, so the
    C-level pin is the presence (wide leaf) / absence (small leaves, at-
    threshold leaves) of the per-leaf heap Object typedef."""

    # 9 pointer fields = 72 bytes > 64 (8 words): boxes. (Top-level names are
    # unique across this class: batched compiles share one flat name pool.)
    _WIDE_SRC = """
namespace Main
import System
enum Shape
  enum Dot(dTag: Int)
  enum BigBox(s0: String, s1: String, s2: String, s3: String, s4: String,
              s5: String, s6: String, s7: String, s8: String)
fun mkShape(k: Int): Shape
  ret k == 0
    ? Dot(7)
    : BigBox("a", "bb", "ccc", "d", "ee", "fff", "g", "hh", "iii")
fun probeShape(k: Int): Int
  ret match(mkShape(k))
    (d: Dot)    => d.dTag
    (b: BigBox) => length(b.s0) + length(b.s2) + length(b.s8)
fun main(): System::Int
  println(String(probeShape(0)) + " " + String(probeShape(1)))
  ret 0
"""

    def test_wide_and_small_variants_roundtrip(self):
        rc, out = compile_and_run_stdlib_capture(self._WIDE_SRC)
        self.assertEqual(0, rc)
        self.assertEqual("7 7", out.strip())

    def test_wide_variant_boxes_to_heap_object(self):
        code = _c_for(self._WIDE_SRC)
        self.assertRegex(code, r"Main__BigBox\w*_t\b",
                         "9-word variant should lower to a heap leaf object")
        self.assertNotRegex(code, r"Main__Dot\w*_t\b",
                            "small variant must stay inline in the pool")

    def test_at_threshold_variant_stays_inline(self):
        # Exactly 8 pointer words = 64 bytes: the rule is strictly greater-
        # than, so this stays a flat tagged struct end to end.
        src = """
namespace Main
import System
enum Edge
  enum Empty0()
  enum Full8(f0: String, f1: String, f2: String, f3: String,
             f4: String, f5: String, f6: String, f7: String)
fun mkEdge(b: Bool): Edge
  ret b ? Full8("a", "b", "c", "d", "e", "f", "g", "h") : Empty0()
fun probeEdge(b: Bool): Int
  ret match(mkEdge(b))
    (f: Full8)  => length(f.f0) + length(f.f7)
    (n: Empty0) => 42
fun main(): System::Int
  println(String(probeEdge(true)) + " " + String(probeEdge(false)))
  ret 0
"""
        code = _c_for(src)
        self.assertNotRegex(code, r"Main__Full8\w*_t\b",
                            "an exactly-8-word variant must NOT box")
        rc, out = compile_and_run_stdlib_capture(src)
        self.assertEqual(0, rc)
        self.assertEqual("2 42", out.strip())

    def test_estimator_counts_collapsed_unions_as_one_word(self):
        # Width analysis must use TRUE layout widths. `Wrap|None` collapses
        # to a single pointer word (newtype over Int + NULL), so eight such
        # fields are exactly 64 bytes = at the threshold, NOT over it: the
        # variant stays inline. An estimator that charges collapsed unions
        # member+tag (16B) would wrongly box this leaf.
        src = """
namespace Main
import System
class Wrap(wVal: Int)
enum Edge2
  enum None2()
  enum Flat8(w0: Wrap|None, w1: Wrap|None, w2: Wrap|None, w3: Wrap|None,
             w4: Wrap|None, w5: Wrap|None, w6: Wrap|None, w7: Wrap|None)
fun mkEdge2(b: Bool): Edge2
  ret b ? Flat8(Wrap(1), None, Wrap(3), None, Wrap(5), None, Wrap(7), None) : None2()
fun readWrap(x: Wrap|None): Int
  ret match(x)
    (w: Wrap) => w.wVal
    (n: None) => 0 - 1
fun probeEdge2(b: Bool): Int
  ret match(mkEdge2(b))
    (f: Flat8) => readWrap(f.w0) + readWrap(f.w6)
    (n: None2) => 42
fun main(): System::Int
  println(String(probeEdge2(true)) + " " + String(probeEdge2(false)))
  ret 0
"""
        code = _c_for(src)
        self.assertNotRegex(code, r"Main__Flat8\w*_t\b",
                            "8 collapsed one-word unions = 64B = at the "
                            "threshold: must stay inline")
        rc, out = compile_and_run_stdlib_capture(src)
        self.assertEqual(0, rc)
        self.assertEqual("8 42", out.strip())

    def test_estimator_counts_nested_enum_pools_truly(self):
        # A nested flat enum value costs its pool: one pointer + a byte tag
        # here (9B), not pointer+word (16B). Six Strings + two such enums =
        # 66B > 64: boxes. Five Strings + two = 58B: stays inline. The pin
        # is the PAIR straddling the threshold under true arithmetic.
        src = """
namespace Main
import System
enum Duo
  enum DuoA(dPtr: String)
  enum DuoB()
enum Straddle
  enum Under5(u0: String, u1: String, u2: String, u3: String, u4: String,
              ua: Duo, ub: Duo)
  enum Over6(o0: String, o1: String, o2: String, o3: String, o4: String,
             o5: String, oa: Duo, ob: Duo)
fun mkS(k: Int): Straddle
  ret k == 0
    ? Under5("a", "b", "c", "d", "e", DuoA("x"), DuoB())
    : Over6("a", "b", "c", "d", "e", "f", DuoA("yy"), DuoB())
fun probeS(k: Int): Int
  ret match(mkS(k))
    (u: Under5) => match(u.ua)
      (a: DuoA) => length(a.dPtr)
      (b: DuoB) => 0 - 2
    (o: Over6) => match(o.oa)
      (a: DuoA) => length(a.dPtr) + length(o.o5)
      (b: DuoB) => 0 - 3
fun main(): System::Int
  println(String(probeS(0)) + " " + String(probeS(1)))
  ret 0
"""
        code = _c_for(src)
        self.assertNotRegex(code, r"Main__Under5\w*_t\b",
                            "58B true width must stay inline")
        self.assertRegex(code, r"Main__Over6\w*_t\b",
                         "66B true width must box")
        rc, out = compile_and_run_stdlib_capture(src)
        self.assertEqual(0, rc)
        self.assertEqual("1 3", out.strip())

    def test_boxed_variant_in_combination_roundtrips(self):
        # The enum (with its boxed variant) nested by value inside a
        # combination: the pool's pointer slot rides through the outer
        # union's slots, and reads go through the heap object.
        src = """
namespace Main
import System
enum Load
  enum Tiny(tVal: Int)
  enum Cargo(c0: String, c1: String, c2: String, c3: String, c4: String,
             c5: String, c6: String, c7: String, c8: String)
fun mkLoad(k: Int): Load
  ret k == 0
    ? Tiny(5)
    : Cargo("a", "bb", "ccc", "d", "ee", "fff", "g", "hh", "iii")
fun maybeLoad(k: Int): Load|None
  ret k < 0 ? None : mkLoad(k)
fun probeLoad(k: Int): Int
  ret match(maybeLoad(k))
    (l: Load) => match(l)
      (t: Tiny)  => t.tVal
      (c: Cargo) => length(c.c1)
    (n: None) => 0 - 1
fun main(): System::Int
  println(String(probeLoad(0 - 1)) + " " + String(probeLoad(0)) + " " + String(probeLoad(1)))
  ret 0
"""
        rc, out = compile_and_run_stdlib_capture(src)
        self.assertEqual(0, rc)
        self.assertEqual("-1 5 2", out.strip())


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
