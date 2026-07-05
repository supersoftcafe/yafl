"""Direct tests for `typespec.meet` — the partial-type refinement primitive.

`meet` is the read-through "single derivation, a refinement of possibly multiple
hints" that lets the inference fixpoint reconcile a freshly arg-derived binding
with a stale, hole-bearing expected-type view of the same slot instead of
colliding to a hard failure (the deadlock fixed in test_fully_inferred_pipeline).

These cases exercise paths the end-to-end suite does not reach but that are
plainly possible in the language — a generic enum (`Result<T,E>`, the element of
every stream `next`) and an order-independent union (every error channel `E`) —
so they are pinned directly rather than left to chance compile coverage. The two
soundness traps: EnumSpec excludes `type_params` from equality (so a leaf `==`
would keep a hole), and a union's `types` tuple is not canonically ordered (so a
positional meet would misalign members)."""
from tests.testutil import TimedTestCase as TestCase

import pyast.typespec as t
from parsing.tokenizer import LineRef

lr = LineRef("f", 0, 0)
i32 = t.BuiltinSpec(lr, "int32")
i64 = t.BuiltinSpec(lr, "int64")
boolt = t.BuiltinSpec(lr, "bool")
strt = t.BuiltinSpec(lr, "str")


def hole(name="E@h"):
    return t.GenericPlaceholderSpec(lr, name)


def cls(name, *params):
    return t.ClassSpec(lr, name, tuple(params))


def enum(root, *params, leaves=("Ok@1", "Err@2")):
    return t.EnumSpec(lr, root, frozenset(leaves), tuple(leaves),
                      all_fields=(), type_params=tuple(params))


def union(*members):
    return t.CombinationSpec(lr, tuple(members))


class TestMeetLeavesAndHoles(TestCase):
    def test_hole_refines_to_ground_either_order(self):
        self.assertIs(t.meet(hole(), i32), i32)
        self.assertIs(t.meet(i32, hole()), i32)

    def test_two_holes_meet_to_a_hole(self):
        # No information either way -> None (a hole), not a conflict.
        self.assertIsNone(t.meet(None, None))

    def test_ground_leaves_must_be_equal(self):
        self.assertEqual(i32, t.meet(i32, i32))
        self.assertIs(t.meet(i32, boolt), t._CONFLICT)


class TestMeetClass(TestCase):
    def test_class_arg_hole_refines_to_ground(self):
        # The deadlock case: Box<_> (stale) meet Box<int32> (fresh) -> Box<int32>.
        self.assertEqual(cls("Box@b", i32), t.meet(cls("Box@b", hole()), cls("Box@b", i32)))

    def test_class_arg_ground_conflict(self):
        self.assertIs(t.meet(cls("Box@b", i32), cls("Box@b", boolt)), t._CONFLICT)

    def test_different_classes_conflict(self):
        self.assertIs(t.meet(cls("Box@b", i32), cls("Bag@g", i32)), t._CONFLICT)


class TestMeetGenericEnum(TestCase):
    def test_enum_type_param_hole_refines_not_kept(self):
        # EnumSpec equality excludes type_params, so a leaf `==` would call these
        # equal and return the hole-bearing one. meet must descend and refine.
        a = enum("Result@r", i32, hole())
        b = enum("Result@r", i32, boolt)
        got = t.meet(a, b)
        self.assertIsInstance(got, t.EnumSpec)
        self.assertEqual((i32, boolt), got.type_params)

    def test_enum_type_param_ground_conflict(self):
        a = enum("Result@r", i32, boolt)
        b = enum("Result@r", i32, i64)
        self.assertIs(t.meet(a, b), t._CONFLICT)

    def test_non_generic_enum_equal(self):
        a = enum("Never@n", leaves=())
        b = enum("Never@n", leaves=())
        self.assertEqual(a, t.meet(a, b))


class TestMeetUnion(TestCase):
    def test_union_is_set_not_positional(self):
        # a's hole sits where b's ground member does NOT line up positionally:
        # [bool, E] vs [int32, bool]. A positional meet would conflict bool/int32;
        # the set-based meet absorbs E into the leftover int32 -> int32|bool.
        a = union(boolt, hole())
        b = union(i32, boolt)
        self.assertEqual(b, t.meet(a, b))

    def test_union_ground_member_absent_conflicts(self):
        # a carries `bool`, which the fully-ground b (int32|str) lacks.
        a = union(boolt, hole())
        b = union(i32, strt)
        self.assertIs(t.meet(a, b), t._CONFLICT)

    def test_two_ground_unions_same_set_any_order(self):
        a = union(i32, boolt)
        b = union(boolt, i32)
        self.assertEqual(a.as_unique_id_str(), t.meet(a, b).as_unique_id_str())

    def test_two_ground_unions_different_set_conflict(self):
        self.assertIs(t.meet(union(i32, boolt), union(i32, strt)), t._CONFLICT)
