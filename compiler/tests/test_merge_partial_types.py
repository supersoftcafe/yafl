"""`merge` over PARTIAL types — the refinement the inference fixpoint relies on.

A stored slot RECEIVES a fresh derivation: a stale, hole-bearing view of the
slot (`Box<_>`) and a freshly argument-derived one (`Box<Int32>`) reconcile
instead of colliding to a hard failure (the deadlock fixed in
test_fully_inferred_pipeline).

These cases exercise paths the end-to-end suite does not reach but that are
plainly possible in the language — a generic enum (`Result<T,E>`, the element of
every stream `next`) and an order-independent union (every error channel `E`) —
so they are pinned directly rather than left to chance compile coverage. The two
soundness traps: EnumSpec once excluded `type_params` from equality (so a leaf
`==` would keep a hole), and a union's `types` tuple is not canonically ordered
(so a positional merge would misalign members)."""
from tests.testutil import TimedTestCase as TestCase

import pyast.resolver as g
import pyast.typespec as t
from parsing.tokenizer import LineRef

lr = LineRef("f", 0, 0)
i32 = t.BuiltinSpec(lr, "int32")
i64 = t.BuiltinSpec(lr, "int64")
boolt = t.BuiltinSpec(lr, "bool")
strt = t.BuiltinSpec(lr, "str")
EMPTY = g.Resolver()


def hole(name="E@h"):
    return t.GenericPlaceholderSpec(lr, name)


def cls(name, *params):
    return t.ClassSpec(lr, name, tuple(params))


def enum(root, *params, leaves=("Ok@1", "Err@2")):
    return t.EnumSpec(lr, root, frozenset(leaves), tuple(leaves),
                      type_params=tuple(params))


def union(*members):
    return t.CombinationSpec(lr, tuple(members))


def merged(a, b):
    """The merged type, or None when the merge found a contradiction."""
    result, _b, errors = t.merge(a, b, {}, EMPTY)
    return None if errors else result


def contradicts(a, b) -> bool:
    return bool(t.merge(a, b, {}, EMPTY)[2])


class TestLeavesAndHoles(TestCase):
    def test_hole_refines_to_ground_either_order(self):
        self.assertIs(merged(hole(), i32), i32)
        self.assertIs(merged(i32, hole()), i32)

    def test_two_holes_merge_to_a_hole(self):
        # No information either way -> None (a hole), not a contradiction.
        self.assertEqual((None, {}, []), t.merge(None, None, {}, EMPTY))

    def test_ground_leaves_must_be_equal(self):
        self.assertEqual(i32, merged(i32, i32))
        self.assertTrue(contradicts(i32, boolt))


class TestClass(TestCase):
    def test_class_arg_hole_refines_to_ground(self):
        # The deadlock case: Box<_> (stale) receives Box<int32> (fresh) -> Box<int32>.
        self.assertEqual(cls("Box@b", i32), merged(cls("Box@b", hole()), cls("Box@b", i32)))

    def test_class_arg_ground_conflict(self):
        self.assertTrue(contradicts(cls("Box@b", i32), cls("Box@b", boolt)))

    def test_different_classes_conflict(self):
        self.assertTrue(contradicts(cls("Box@b", i32), cls("Findings@g", i32)))


class TestGenericEnum(TestCase):
    def test_enum_type_param_hole_refines_not_kept(self):
        # A leaf `==` that ignored type_params would call these equal and keep
        # the hole-bearing one. The merge must descend and refine.
        got = merged(enum("Result@r", i32, hole()), enum("Result@r", i32, boolt))
        self.assertIsInstance(got, t.EnumSpec)
        self.assertEqual((i32, boolt), got.type_params)

    def test_enum_type_param_ground_conflict(self):
        self.assertTrue(contradicts(enum("Result@r", i32, boolt), enum("Result@r", i32, i64)))

    def test_non_generic_enum_equal(self):
        a = enum("Never@n", leaves=())
        self.assertEqual(a, merged(a, enum("Never@n", leaves=())))


class TestUnion(TestCase):
    def test_union_is_set_not_positional(self):
        # a's hole sits where b's ground member does NOT line up positionally:
        # [bool, E] vs [int32, bool]. A positional merge would conflict
        # bool/int32; the set-based one fills E with the leftover int32.
        got = merged(union(boolt, hole()), union(i32, boolt))
        self.assertEqual({i32, boolt}, set(got.repr_members()))

    def test_a_value_member_the_receiver_lacks_conflicts(self):
        # b carries `bool`, which the fully-ground receiver (int32|str) lacks.
        self.assertTrue(contradicts(union(i32, strt), union(boolt, hole())))

    def test_two_ground_unions_same_set_any_order(self):
        a = union(i32, boolt)
        self.assertEqual(a.as_unique_id_str(), merged(a, union(boolt, i32)).as_unique_id_str())

    def test_two_ground_unions_different_set_conflict(self):
        self.assertTrue(contradicts(union(i32, boolt), union(i32, strt)))

    def test_identical_holey_union_merges_with_itself(self):
        # merge(x, x) = x. A union whose members hold a template's own
        # placeholder (`Leaf<T> | Branch<T>`) has no ground id; a type param
        # bound twice to that same union (from an argument and from the
        # expected result) must still infer.
        u = union(cls("Leaf@1", hole("T@1")), cls("Branch@2", hole("T@1")))
        self.assertEqual(u, merged(u, union(cls("Leaf@1", hole("T@1")),
                                            cls("Branch@2", hole("T@1")))))
