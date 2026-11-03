"""Pointer-word union representation (tag-elimination phase 2).

A union whose members are all mutually-distinguishable pointer-words (heap
classes, tagged immediates, single-field newtype wrappers, complex enums) plus
at most one unit collapses to a single machine word — None is the NULL sentinel,
every other member dispatches by its pointer tag / vtable. Unions with a
multi-field/scalar payload, or two members sharing a runtime kind, stay a tagged
`{...,$tag}` struct.

These tests pin both the representation (collapsed `object_t*` vs tagged struct)
and the runtime behaviour (every arm dispatches to the right value).

Runtime behaviour is checked by compiler/yafl_tests/union_repr.yafl.
"""
from __future__ import annotations

import re

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture
from tests.testutil import compile_c
from tests.testutil import compile_errors
from pyast import union_repr


def _c_for(source: str) -> str:
    out = compile_c(source)
    assert out, "compilation produced no output"
    return out


class TestUnionRepresentation(TestCase):
    # ── behaviour: every arm of a collapsed union dispatches correctly ────────


    # ── representation: collapsed vs tagged in the generated C ────────────────

    def _ret_type(self, code: str, fn_substr: str) -> str:
        """The C return type of the function whose mangled name contains
        fn_substr: `object_t*` (collapsed to one word), `str_t` (collapsed,
        wide — a String member makes the one dispatch word a String value),
        or a tagged struct."""
        for line in code.splitlines():
            if fn_substr in line and "(object_t* this" in line and line.rstrip().endswith(";"):
                return line.lstrip().split(" ")[0]
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
        # Both collapse to ONE dispatch word; each carries a String member
        # (B is a newtype over String), so that word is a String value's head
        # and the union value is the String value, str_t.
        self.assertEqual("str_t", self._ret_type(code, "Main__ab_"),
                         "A|B|None should collapse to a String-value union")
        self.assertEqual("str_t", self._ret_type(code, "Main__isn_"),
                         "Int|String|None should collapse to a String-value union")
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


    def test_wide_variant_boxes_to_heap_object(self):
        code = _c_for(self._WIDE_SRC)
        self.assertRegex(code, r"Main__BigBox\w*_t\b",
                         "9-word variant should lower to a heap leaf object")
        self.assertNotRegex(code, r"Main__Dot\w*_t\b",
                            "small variant must stay inline in the pool")

    def test_at_threshold_variant_stays_inline(self):
        # Exactly 64 bytes — four 16-byte String values: the rule is strictly
        # greater-than, so this stays a flat tagged struct end to end.
        src = """
namespace Main
import System
enum Edge
  enum Empty0()
  enum Full8(f0: String, f1: String, f2: String, f3: String)
fun mkEdge(b: Bool): Edge
  ret b ? Full8("a", "b", "c", "d") : Empty0()
fun probeEdge(b: Bool): Int
  ret match(mkEdge(b))
    (f: Full8)  => length(f.f0) + length(f.f3)
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
        # A nested flat enum value costs its pool: here one String value
        # (16B) + a byte tag = 17B, not String + a whole tag word (24B).
        # Three such enums = 51B: stays inline (a per-word count says 72B and
        # would box it). One String + three = 67B > 64: boxes. The pin is the
        # PAIR straddling the threshold under true arithmetic.
        src = """
namespace Main
import System
enum Duo
  enum DuoA(dPtr: String)
  enum DuoB()
enum Straddle
  enum Under5(ua: Duo, ub: Duo, uc: Duo)
  enum Over6(o0: String, oa: Duo, ob: Duo, oc: Duo)
fun mkS(k: Int): Straddle
  ret k == 0
    ? Under5(DuoA("x"), DuoB(), DuoB())
    : Over6("f", DuoA("yy"), DuoB(), DuoB())
fun probeS(k: Int): Int
  ret match(mkS(k))
    (u: Under5) => match(u.ua)
      (a: DuoA) => length(a.dPtr)
      (b: DuoB) => 0 - 2
    (o: Over6) => match(o.oa)
      (a: DuoA) => length(a.dPtr) + length(o.o0)
      (b: DuoB) => 0 - 3
fun main(): System::Int
  println(String(probeS(0)) + " " + String(probeS(1)))
  ret 0
"""
        code = _c_for(src)
        self.assertNotRegex(code, r"Main__Under5\w*_t\b",
                            "51B true width must stay inline")
        self.assertRegex(code, r"Main__Over6\w*_t\b",
                         "67B true width must box")
        rc, out = compile_and_run_stdlib_capture(src)
        self.assertEqual(0, rc)
        self.assertEqual("1 3", out.strip())


class TestLeafConstructorTyping(TestCase):
    """A construction builds exactly one variant, so its TYPE is the leaf
    (USER RULING): `Dark(7, "d")` has type Dark, not Shade. Representation
    is unchanged — leaf-typed values carry the root's struct (common fields
    + discriminator) — so this is a type-system fact only: fresh
    constructions become legal wherever a leaf type is declared, and
    `ret Dark(...)` is exact where Dark is the declared result."""

    # A fresh construction feeding a leaf-typed FIELD and a leaf-typed
    # PARAMETER — the shapes that previously required a match bind.
    _HOLD_SRC = """
namespace Main
import System
enum Payload
  enum Pay1(p0: String, p1: String)
  enum Pay2(pTiny: Int)
enum Host
  enum Hold(hPay: Pay1)
  enum Empty1()
fun sizeOfPay(p: Pay1): Int
  ret length(p.p0) + length(p.p1)
fun mkHost(b: Bool): Host
  ret b ? Hold(Pay1("a", "bb")) : Empty1()
fun probeHost(b: Bool): Int
  ret match(mkHost(b))
    (h: Hold)   => sizeOfPay(h.hPay)
    (e: Empty1) => 42
fun main(): System::Int
  println(String(probeHost(true)) + " " + String(probeHost(false)))
  ret 0
"""


    def test_root_still_rejected_where_leaf_declared(self):
        # The ruling types CONSTRUCTIONS as leaves; a root-typed VALUE is
        # still not assignable to a leaf-typed parameter.
        src = """
namespace Main
import System
enum Shade
  enum Dark(dLevel: Int)
  enum Light(lLevel: Int)
fun wantsDark(d: Dark): Int
  ret d.dLevel
fun probe(s: Shade): Int
  ret wantsDark(s)
fun main(): System::Int
  ret probe(Dark(1))
"""
        self.assertEqual("rootleaf.yafl[10:17] - Parameters are not assignment compatible\n",
                         compile_errors(src, "rootleaf.yafl"))


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




class TestNullPatternDiscrimination(TestCase):
    """A flat enum carries no `$tag` when its slots already say which variant
    a value holds (#75): a never-NULL word (a heap class, an Int, a complex
    enum, a String's first word, a function's code pointer) in one variant
    against the same slot left NULL — unused — by another. The tag stays
    whenever two variants cannot be told apart that way: a nullable field, a
    scalar payload, or two variants whose never-NULL words share a slot.

    Runtime behaviour is checked by compiler/yafl_tests/union_repr.yafl."""

    _SRC = """
namespace Main
import System
class Node(next: Node|None, v: Int)
enum NpList
  enum NpEmpty()
  enum NpFull(head: Node, tail: Node, count: Int)
enum NpTree
  enum NpNil()
  enum NpLeaf(a: Node)
  enum NpPair(l: Node, r: Node)
enum NpSame
  enum NpA(x: Node)
  enum NpB(y: Node)
enum NpMaybe
  enum NpNothing()
  enum NpHeld(m: Node|None)
enum NpScalar
  enum NpZero()
  enum NpNum(n: Int32)
enum NpOpt<T>
  enum NpNone()
  enum NpSome(value: T)
enum NpCount
  enum NpNoCount()
  enum NpHasCount(n: Int)
enum NpText
  enum NpNoText()
  enum NpHasText(s: String)
enum NpMaybeText
  enum NpNoMaybeText()
  enum NpHasMaybeText(s: String|None)
enum NpFn
  enum NpNoFn()
  enum NpHasFn(f: (:Int): Int)
enum NpMaybeFn
  enum NpNoMaybeFn()
  enum NpHasMaybeFn(f: ((:Int): Int)|None)
fun [inline(never)] mkList(k: Int): NpList
  let n = Node(None, k)
  ret k == 0 ? NpEmpty() : NpFull(n, n, k)
fun [inline(never)] mkTree(k: Int): NpTree
  ret k == 0 ? NpNil() : (k == 1 ? NpLeaf(Node(None, 1)) : NpPair(Node(None, 1), Node(None, 2)))
fun [inline(never)] mkSame(k: Int): NpSame
  ret k == 0 ? NpA(Node(None, 1)) : NpB(Node(None, 2))
fun [inline(never)] mkMaybe(k: Int): NpMaybe
  ret k == 0 ? NpNothing() : NpHeld(None)
fun [inline(never)] mkScalar(k: Int): NpScalar
  ret k == 0 ? NpZero() : NpNum(7i32)
fun [inline(never)] mkOptNode(k: Int): NpOpt<Node>
  ret k == 0 ? NpNone<Node>() : NpSome<Node>(Node(None, 1))
fun [inline(never)] mkOptI32(k: Int): NpOpt<Int32>
  ret k == 0 ? NpNone<Int32>() : NpSome<Int32>(1i32)
fun [inline(never)] mkCount(k: Int): NpCount
  ret k == 0 ? NpNoCount() : NpHasCount(k)
fun [inline(never)] mkText(k: Int): NpText
  ret k == 0 ? NpNoText() : NpHasText("")
fun [inline(never)] mkMaybeText(k: Int): NpMaybeText
  ret k == 0 ? NpNoMaybeText() : NpHasMaybeText("m")
fun [inline(never)] mkFn(k: Int): NpFn
  ret k == 0 ? NpNoFn() : NpHasFn((i: Int) => i + k)
fun [inline(never)] mkMaybeFn(k: Int): NpMaybeFn
  ret k == 0 ? NpNoMaybeFn() : NpHasMaybeFn(None)
fun main(): System::Int
  let a = match(mkList(1))
    (e: NpEmpty) => 0
    (f: NpFull)  => 1
  let b = match(mkTree(1))
    (e: NpNil)  => 0
    (f: NpLeaf) => 1
    (p: NpPair) => 2
  let c = match(mkSame(1))
    (x: NpA) => 0
    (y: NpB) => 1
  let d = match(mkMaybe(1))
    (x: NpNothing) => 0
    (y: NpHeld)    => 1
  let e = match(mkScalar(1))
    (x: NpZero) => 0
    (y: NpNum)  => 1
  let f = match(mkOptNode(1))
    (x: NpNone) => 0
    (y: NpSome) => 1
  let g = match(mkOptI32(1))
    (x: NpNone) => 0
    (y: NpSome) => 1
  let h = match(mkCount(1))
    (x: NpNoCount)  => 0
    (y: NpHasCount) => y.n
  let i = match(mkText(1))
    (x: NpNoText)  => 0
    (y: NpHasText) => length(y.s)
  let j = match(mkMaybeText(1))
    (x: NpNoMaybeText)  => 0
    (y: NpHasMaybeText) => 1
  let k = match(mkFn(1))
    (x: NpNoFn)  => 0
    (y: NpHasFn) => y.f(1)
  let l = match(mkMaybeFn(1))
    (x: NpNoMaybeFn)  => 0
    (y: NpHasMaybeFn) => 1
  ret a + b + c + d + e + f + g + h + i + j + k + l
"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.code = _c_for(cls._SRC)

    def _fields(self, fn_substr: str) -> list[str]:
        """The C field declarations of the enum struct returned by the
        function whose mangled name contains fn_substr — looking through the
        task wrapper a pointer-free result travels in."""
        ret = next(line.split(" ")[0] for line in self.code.splitlines()
                   if re.match(rf"\S+ {fn_substr}\w*\(object_t\* this", line)
                   and line.rstrip().endswith(";"))
        fields = self._typedef_fields(ret)
        if len(fields) == 2 and fields[1] == "object_t* task;":
            fields = self._typedef_fields(fields[0].split(" ")[0])
        return fields

    def _typedef_fields(self, name: str) -> list[str]:
        lines = self.code.splitlines()
        end = next(i for i, line in enumerate(lines)
                   if line.startswith("}") and line.rstrip().endswith(f" {name};"))
        start = max(i for i in range(end) if lines[i].startswith("typedef struct"))
        return [line.strip() for line in lines[start + 1:end]]

    def test_unit_and_data_variant_drop_the_tag(self):
        self.assertEqual(["object_t* _s0;", "object_t* _s1;", "object_t* _s2;"],
                         self._fields("Main__mkList_"))

    def test_null_pattern_tells_data_variants_apart(self):
        self.assertEqual(["object_t* _s0;", "object_t* _s1;"],
                         self._fields("Main__mkTree_"))

    def test_generic_instantiation_over_a_class_drops_the_tag(self):
        self.assertEqual(["object_t* _s0;"], self._fields("Main__mkOptNode_"))

    def test_int_field_drops_the_tag(self):
        # 0 is the tagged word 0x2: an Int is never NULL.
        self.assertEqual(["object_t* _s0;"], self._fields("Main__mkCount_"))

    def test_string_field_drops_the_tag(self):
        # A String's first word is never NULL — even "" is a tagged word.
        self.assertEqual(["str_t _s0;"], self._fields("Main__mkText_"))

    def test_function_field_drops_the_tag(self):
        # A function's code pointer is never NULL; its environment may be.
        self.assertEqual(["object_t* _s0;", "intptr_t _s1;"], self._fields("Main__mkFn_"))

    def test_nullable_string_and_function_fields_keep_the_tag(self):
        # `|None` puts NULL in the very word that would tell them apart.
        self.assertIn("int8_t _tag;", self._fields("Main__mkMaybeText_"))
        self.assertIn("int8_t _tag;", self._fields("Main__mkMaybeFn_"))

    def test_variants_sharing_a_never_null_slot_keep_the_tag(self):
        self.assertIn("int8_t _tag;", self._fields("Main__mkSame_"))

    def test_nullable_field_keeps_the_tag(self):
        self.assertIn("int8_t _tag;", self._fields("Main__mkMaybe_"))

    def test_scalar_payload_keeps_the_tag(self):
        self.assertIn("int8_t _tag;", self._fields("Main__mkScalar_"))
        self.assertIn("int8_t _tag;", self._fields("Main__mkOptI32_"))
