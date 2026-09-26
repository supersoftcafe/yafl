"""`merge(left, right, bindings, resolver)` — the one type merge.

docs/type-merge-design.md. LEFT is the receiver, RIGHT the value: left must be
assignable from right. The merge fills gaps and resolves hierarchy, never
widens, and returns (result, bindings, errors): the best correct answer it can
give (None when nothing merges), the bindings extended by what was learned,
and every contradiction found — the caller collects errors and carries on.

A HOLE is None, an unresolved name, or a placeholder that does not resolve in
scope. A placeholder named in `bindings` is a NAMED hole: unbound (None) it
binds once; bound, every further occurrence must agree — holes inside a
binding fill, nothing else changes it. Generic arguments are INVARIANT: they
merge by hole-filling only.
"""
from __future__ import annotations

import pyast.resolver as g
import pyast.statement as s
import pyast.typespec as t
from parsing.parser import parse
from parsing.tokenizer import LineRef, tokenize
from tests.testutil import TimedTestCase as TestCase

import compiler as c

lr = LineRef("m", 0, 0)
INT = t.BuiltinSpec(lr, "bigint")
STR = t.BuiltinSpec(lr, "str")
BOOL = t.BuiltinSpec(lr, "bool")
UNIT = t.TupleSpec(lr, ())
_SHAPE = ("Shape@1", ("Circle@1", "Square@1"))
_LIST = ("List@1", ("ListEmpty@1", "ListFull@1"))


def hole(name="T@free"):
    return t.GenericPlaceholderSpec(lr, name)


def enum(family, *args, leaves=None):
    root, all_leaves = family
    return t.EnumSpec(lr, root, frozenset(leaves or all_leaves), all_leaves, type_params=tuple(args))


def tup(*entries):
    return t.TupleSpec(lr, tuple(t.TupleEntrySpec(n, ty) for n, ty in entries))


def union(*members):
    return t.CombinationSpec(lr, tuple(members))


def fn(params, result):
    return t.CallableSpec(lr, tup(*[(None, p) for p in params]), result)


EMPTY = g.Resolver()


class TestHolesAndLeaves(TestCase):
    def test_a_hole_takes_the_other_side(self):
        for left, right in ((None, INT), (INT, None), (hole(), INT), (INT, hole())):
            with self.subTest(left=left, right=right):
                result, _b, errors = t.merge(left, right, {}, EMPTY)
                self.assertEqual(INT, result)
                self.assertEqual([], errors)

    def test_equal_leaves_merge(self):
        self.assertEqual((INT, {}, []), t.merge(INT, INT, {}, EMPTY))

    def test_different_leaves_are_a_contradiction(self):
        result, _b, errors = t.merge(INT, STR, {}, EMPTY)
        self.assertIsNone(result)
        self.assertEqual(1, len(errors))


class TestTuples(TestCase):
    def test_holes_fill_across_the_pair(self):
        result, _b, errors = t.merge(tup((None, INT), (None, None)), tup((None, None), (None, STR)), {}, EMPTY)
        self.assertEqual(tup((None, INT), (None, STR)), result)
        self.assertEqual([], errors)

    def test_a_contradicting_entry_is_reported(self):
        result, _b, errors = t.merge(tup((None, INT)), tup((None, STR)), {}, EMPTY)
        self.assertEqual(1, len(errors))


class TestEnumViews(TestCase):
    def test_the_root_receives_a_view(self):
        circle = enum(_SHAPE, leaves=("Circle@1",))
        self.assertEqual((enum(_SHAPE), {}, []), t.merge(enum(_SHAPE), circle, {}, EMPTY))

    def test_a_narrower_receiver_is_a_contradiction(self):
        circle = enum(_SHAPE, leaves=("Circle@1",))
        result, _b, errors = t.merge(circle, enum(_SHAPE), {}, EMPTY)
        self.assertIsNone(result)
        self.assertEqual(1, len(errors))

    def test_sibling_views_are_a_contradiction(self):
        circle = enum(_SHAPE, leaves=("Circle@1",))
        square = enum(_SHAPE, leaves=("Square@1",))
        result, _b, errors = t.merge(circle, square, {}, EMPTY)
        self.assertIsNone(result)
        self.assertEqual(1, len(errors))


class TestGenericArguments(TestCase):
    def test_a_hole_argument_fills(self):
        self.assertEqual((enum(_LIST, INT), {}, []), t.merge(enum(_LIST, hole()), enum(_LIST, INT), {}, EMPTY))

    def test_arguments_are_invariant(self):
        # List<Circle> is not a List<Shape>, whichever way round.
        circle = enum(_SHAPE, leaves=("Circle@1",))
        for left, right in ((enum(_LIST, enum(_SHAPE)), enum(_LIST, circle)),
                            (enum(_LIST, circle), enum(_LIST, enum(_SHAPE)))):
            with self.subTest(left=left):
                result, _b, errors = t.merge(left, right, {}, EMPTY)
                self.assertIsNone(result)
                self.assertEqual(1, len(errors))

    def test_argument_holes_fill_from_either_side(self):
        pair = ("Pair@1", ("Pair@1",))
        result, _b, errors = t.merge(enum(pair, INT, hole()), enum(pair, hole(), STR), {}, EMPTY)
        self.assertEqual(enum(pair, INT, STR), result)
        self.assertEqual([], errors)

    def test_a_generic_spelled_without_arguments_is_a_shape(self):
        # The `rw` case: a leaf pattern `ListFull` names List with no
        # arguments — every argument a hole.
        full = enum(_LIST, leaves=("ListFull@1",))
        self.assertEqual((enum(_LIST, INT), {}, []),
                         t.merge(enum(_LIST, INT), enum(_LIST, INT, leaves=("ListFull@1",)), {}, EMPTY))
        self.assertEqual((enum(_LIST, INT), {}, []), t.merge(enum(_LIST, INT), enum(_LIST), {}, EMPTY))
        result, _b, errors = t.merge(enum(_LIST, INT), full, {}, EMPTY)
        self.assertEqual(enum(_LIST, INT), result)
        self.assertEqual([], errors)


class TestNamedHoles(TestCase):
    def test_an_unbound_name_binds(self):
        result, bindings, errors = t.merge(enum(_LIST, hole("T@c")), enum(_LIST, INT), {"T@c": None}, EMPTY)
        self.assertEqual(enum(_LIST, INT), result)
        self.assertEqual({"T@c": INT}, bindings)
        self.assertEqual([], errors)

    def test_a_bound_name_must_agree(self):
        result, bindings, errors = t.merge(tup((None, hole("T@c")), (None, hole("T@c"))),
                                           tup((None, INT), (None, STR)), {"T@c": None}, EMPTY)
        self.assertEqual(1, len(errors))
        self.assertEqual({"T@c": INT}, bindings)

    def test_holes_inside_a_binding_fill(self):
        bound = {"T@c": enum(_LIST, hole())}
        _r, bindings, errors = t.merge(hole("T@c"), enum(_LIST, INT), bound, EMPTY)
        self.assertEqual({"T@c": enum(_LIST, INT)}, bindings)
        self.assertEqual([], errors)

    def test_a_binding_is_never_widened(self):
        _r, bindings, errors = t.merge(hole("T@c"), union(INT, UNIT), {"T@c": INT}, EMPTY)
        self.assertEqual({"T@c": INT}, bindings)
        self.assertEqual(1, len(errors))

    def test_a_name_may_bind_to_another_scope_s_placeholder(self):
        # T@callee = T@caller: hash-qualified names never alias. The caller's
        # T is a real type where the merge happens (in scope there); out of
        # scope it would be an anonymous hole and carry nothing.
        class CallerScope(g.Resolver):
            def find_type(self, name):
                return g.Findings(("T@caller",)) if name == "T@caller" else g.EMPTY
        caller_t = hole("T@caller")
        _r, bindings, errors = t.merge(hole("T@callee"), caller_t, {"T@callee": None}, CallerScope())
        self.assertEqual({"T@callee": caller_t}, bindings)
        self.assertEqual([], errors)


class TestUnions(TestCase):
    def test_a_union_receives_a_member(self):
        self.assertEqual((union(INT, UNIT), {}, []), t.merge(union(INT, UNIT), INT, {}, EMPTY))

    def test_a_union_member_hole_fills(self):
        result, _b, errors = t.merge(union(enum(_LIST, hole()), UNIT), enum(_LIST, INT), {}, EMPTY)
        self.assertEqual(union(enum(_LIST, INT), UNIT), result)
        self.assertEqual([], errors)

    def test_a_hole_member_takes_what_no_other_member_holds(self):
        # `A | ?` receiving `A | B` is `A | B`: the hole stands for the rest.
        result, _b, errors = t.merge(union(INT, hole()), union(INT, STR), {}, EMPTY)
        self.assertEqual({INT, STR}, set(result.repr_members()))
        self.assertEqual([], errors)

    def test_a_value_the_union_cannot_hold_is_a_contradiction(self):
        result, _b, errors = t.merge(union(INT, UNIT), STR, {}, EMPTY)
        self.assertEqual(1, len(errors))

    def test_a_union_value_must_fit_member_by_member(self):
        result, _b, errors = t.merge(union(INT, STR, UNIT), union(INT, UNIT), {}, EMPTY)
        self.assertEqual(union(INT, STR, UNIT), result)
        self.assertEqual([], errors)
        result, _b, errors = t.merge(INT, union(INT, UNIT), {}, EMPTY)
        self.assertEqual(1, len(errors))


class TestCallables(TestCase):
    def test_parameters_reverse_direction(self):
        # A (Shape): Int receives a (Circle): Int? No — the value would be
        # handed Shapes it cannot take. The reverse is fine.
        circle = enum(_SHAPE, leaves=("Circle@1",))
        ok = t.merge(fn([circle], INT), fn([enum(_SHAPE)], INT), {}, EMPTY)
        self.assertEqual([], ok[2])
        bad = t.merge(fn([enum(_SHAPE)], INT), fn([circle], INT), {}, EMPTY)
        self.assertEqual(1, len(bad[2]))

    def test_holes_fill_through_a_callable(self):
        result, _b, errors = t.merge(fn([None], None), fn([INT], BOOL), {}, EMPTY)
        self.assertEqual(fn([INT], BOOL), result)
        self.assertEqual([], errors)


_HIERARCHY = """\
namespace H
interface Automobile<Y>
class Car<X, Y>() : Automobile<Y>
"""


class TestHierarchy(TestCase):
    """A value lifts to the receiver's head along the class's own recorded
    ancestor spelling — `Car<X,Y>` records `Automobile<Y>`."""

    @classmethod
    def setUpClass(cls):
        statements, resolver, _passes = c.__dict__["__converge"](parse(tokenize(_HIERARCHY, "h")).value)
        cls.resolver = resolver
        names = {st.name.split("@")[0]: st.name for st in statements if isinstance(st, s.ClassStatement)}
        cls.car, cls.auto = names["H::Car"], names["H::Automobile"]

    def test_a_value_lifts_to_its_ancestor(self):
        result, _b, errors = t.merge(t.ClassSpec(lr, self.auto, (hole(),)),
                                     t.ClassSpec(lr, self.car, (INT, STR)), {}, self.resolver)
        self.assertEqual(t.ClassSpec(lr, self.auto, (STR,)), result)
        self.assertEqual([], errors)

    def test_an_ancestor_does_not_fit_a_descendant(self):
        result, _b, errors = t.merge(t.ClassSpec(lr, self.car, (hole(), hole())),
                                     t.ClassSpec(lr, self.auto, (STR,)), {}, self.resolver)
        self.assertIsNone(result)
        self.assertEqual(1, len(errors))


_GENERIC = """\
namespace G
enum Box<T>
  enum Full(value: T)
  enum Empty()
"""


class TestRefineFillsAMissingArgumentList(TestCase):
    """A generic spelled without its arguments is a shape — every argument a
    hole — so a stored type like that is still refinable, and refining it is
    a merge. (A `with` over a match binder stored the bare `ListFull` on a
    pass before the arm was stamped with its arguments, and nothing ever
    reopened it: codegen then met an un-monomorphised template.)"""

    @classmethod
    def setUpClass(cls):
        statements, resolver, _passes = c.__dict__["__converge"](parse(tokenize(_GENERIC, "gb")).value)
        cls.resolver = resolver
        box = next(st for st in statements if isinstance(st, s.EnumStatement))
        cls.bare = box.get_type()
        cls.of_int = t.EnumSpec(lr, cls.bare.root_name, cls.bare.valid_leaf_names,
                                cls.bare.all_leaf_names, type_params=(INT,))

    def test_a_bare_generic_refines_to_its_instantiation(self):
        self.assertEqual(self.of_int, t.refine(self.bare, self.resolver, lambda: self.of_int))

    def test_an_instantiation_is_settled(self):
        self.assertEqual(self.of_int, t.refine(self.of_int, self.resolver,
                                               lambda: self.fail("a settled type must not re-infer")))


class TestWidenViews(TestCase):
    """A STORED inference holding a narrowed view is provisional — the view
    widens with its right-hand side (`put(acc, k, MMissing())` first stores
    `Dict<?, Out{MMissing}>`; later `Dict<String, Out>`). That is `refine`'s
    one use of `merge(…, widen_views=True)`; everywhere else views stay
    distinct types."""

    def test_a_provisional_view_widens_inside_an_argument(self):
        missing = enum(_SHAPE, leaves=("Circle@1",))
        dct = ("Dict@1", ("Dict@1",))
        stored, fresh = enum(dct, hole(), missing), enum(dct, STR, enum(_SHAPE))
        result, _b, errors = t.merge(stored, fresh, {}, EMPTY, widen_views=True)
        self.assertEqual(enum(dct, STR, enum(_SHAPE)), result)
        self.assertEqual([], errors)
        _r, _b, strict = t.merge(stored, fresh, {}, EMPTY)
        self.assertEqual(1, len(strict))


class TestWideningNeverAdoptsHoles(TestCase):
    """`refine_widening` adopts a fresh type strictly wider than the stored
    one — but a fresh type still holding a hole (`T | () | X`, a call that
    has not bound its T yet) is not wider, only less finished; adopted, the
    hole outlives every later answer."""

    def test_a_holey_fresh_type_is_not_adopted(self):
        stored = union(UNIT, INT)
        fresh = union(hole(), UNIT, INT)
        self.assertEqual(stored, t.refine_widening(stored, EMPTY, lambda: fresh))

    def test_a_complete_wider_type_still_is(self):
        stored = union(UNIT, INT)
        fresh = union(UNIT, INT, STR)
        self.assertEqual(fresh, t.refine_widening(stored, EMPTY, lambda: fresh))


class TestArgumentsOutrankTheExpectedType(TestCase):
    """At a call site the ARGUMENTS bind the callee's params; the expected
    result then fills only what is still unbound — it is the receiver of the
    callee's result, a merge. A contradiction there is the receiver's to
    report, and must not erase what the arguments proved (`head(kept)` with
    `kept: List<Spec>` against a stored `() | Spec{SCombination}` lost
    `T = Spec` entirely, and the call never bound)."""

    def test_an_expected_result_that_contradicts_leaves_the_argument_binding(self):
        from types import SimpleNamespace
        import pyast.inference as inf
        T = hole("T@head")
        stmt = SimpleNamespace(type_params=[SimpleNamespace(name="T@head")], trait_params=())
        declared = t.CallableSpec(lr, tup((None, enum(_LIST, T))), union(T, UNIT))
        circle = enum(_SHAPE, leaves=("Circle@1",))
        expected = t.CallableSpec(lr, tup((None, enum(_LIST, enum(_SHAPE)))), union(UNIT, circle))
        mapping = inf._infer_type_params(stmt, declared, expected, g.ResolverRoot([]))
        self.assertEqual({"T@head": enum(_SHAPE)}, mapping)

    def test_an_unbound_param_fills_from_the_expected_union_member(self):
        from types import SimpleNamespace
        import pyast.inference as inf
        T = hole("T@list")
        stmt = SimpleNamespace(type_params=[SimpleNamespace(name="T@list")], trait_params=())
        declared = t.CallableSpec(lr, tup(), enum(_LIST, T))
        expected = t.CallableSpec(lr, tup(), union(enum(_LIST, INT), UNIT))
        mapping = inf._infer_type_params(stmt, declared, expected, g.ResolverRoot([]))
        self.assertEqual({"T@list": INT}, mapping)


class TestABindingIsTheCallersType(TestCase):
    """A bound value comes from the reference site: its placeholders are the
    CALLER's types, never the callee's named holes. A self-recursive generic
    binds its own params to themselves (`S@drain = S@drain`, a real type in
    scope there); reading that binding as a named hole again recursed
    forever."""

    def test_a_self_binding_does_not_recurse(self):
        class InScope(g.Resolver):
            def find_type(self, name):
                return g.Findings((name,)) if name == "S@drain" else g.EMPTY
        s_ = hole("S@drain")
        result, bindings, errors = t.merge(enum(_LIST, s_), enum(_LIST, s_), {"S@drain": s_}, InScope())
        self.assertEqual(enum(_LIST, s_), result)
        self.assertEqual({"S@drain": s_}, bindings)
        self.assertEqual([], errors)


class TestNamedHolesLiveOnTheCalleeSide(TestCase):
    """The callee's params are holes only in the CALLEE's own spelling. On
    the other side the same name is the reference site's: its own type when
    in scope, otherwise a leaked unbound placeholder — an anonymous hole.
    (`put(acc, k, put(Dict(), ns, f))`: the inner call's expected type is the
    outer call's unbound V — the same name as the inner V; binding them made
    V := Dict<K, V>.)"""

    def test_a_same_named_placeholder_on_the_reference_side_is_not_the_callee_s(self):
        v = hole("V@put")
        dict_kv = enum(("Dict@1", ("Dict@1",)), hole("K@put"), v)
        _r, bindings, errors = t.merge(v, dict_kv, {"K@put": None, "V@put": None}, EMPTY,
                                       callee_left=False)
        self.assertEqual({"K@put": None, "V@put": None}, bindings)
        self.assertEqual([], errors)

    def test_the_callee_side_flips_through_callable_parameters(self):
        # callee `(:T): Bool` on the right receives nothing; its params flip
        # to the left of the parameter merge, where T is still the callee's.
        _r, bindings, errors = t.merge(fn([INT], BOOL), fn([hole("T@c")], BOOL), {"T@c": None},
                                       EMPTY, callee_left=False)
        self.assertEqual({"T@c": INT}, bindings)
        self.assertEqual([], errors)


class TestUnionHolesSolveBySetDifference(TestCase):
    """A union is a SET: a callee's `E | X` against `A | X` solves E by set
    difference — the ground members pair up first, and the one named hole
    takes what is left (the error-growing stream pattern
    `Stream<Lexer<S,E>, T, E | ParseError>`). Two holes have no partition and
    stay unbound."""

    def test_a_value_side_hole_takes_the_unmatched_receiver_members(self):
        e = hole("E@c")
        _r, bindings, errors = t.merge(union(INT, UNIT), union(e, UNIT), {"E@c": None}, EMPTY,
                                       callee_left=False)
        self.assertEqual({"E@c": INT}, bindings)
        self.assertEqual([], errors)
        _r, bindings, errors = t.merge(union(INT, STR, UNIT), union(e, UNIT), {"E@c": None}, EMPTY,
                                       callee_left=False)
        self.assertEqual({INT, STR}, set(bindings["E@c"].repr_members()))
        self.assertEqual([], errors)

    def test_a_receiver_side_hole_takes_the_unplaced_value_members(self):
        e = hole("E@c")
        _r, bindings, errors = t.merge(union(e, UNIT), union(INT, STR, UNIT), {"E@c": None}, EMPTY)
        self.assertEqual({INT, STR}, set(bindings["E@c"].repr_members()))
        self.assertEqual([], errors)

    def test_a_bound_value_side_hole_contributes_its_binding(self):
        # `Stream<Pretty<S,E>, String, E | ParseError>`: E is bound by the
        # first argument to `Int | ParseError` (spelt STR here); the union's
        # E then contributes those members, which cover the receiver's rest.
        e = hole("E@c")
        _r, bindings, errors = t.merge(union(STR, INT), union(e, STR), {"E@c": union(INT, STR)},
                                       EMPTY, callee_left=False)
        self.assertEqual([], errors)
        # A bound member the receiver cannot hold is a contradiction.
        _r, _b, errors = t.merge(union(STR, INT), union(e, STR), {"E@c": union(INT, BOOL)},
                                 EMPTY, callee_left=False)
        self.assertEqual(1, len(errors))

    def test_a_bound_receiver_side_hole_holds_the_unplaced_members(self):
        e = hole("E@c")
        _r, _b, errors = t.merge(union(e, UNIT), union(INT, UNIT), {"E@c": union(INT, STR)}, EMPTY)
        self.assertEqual([], errors)
        _r, _b, errors = t.merge(union(e, UNIT), union(BOOL, UNIT), {"E@c": union(INT, STR)}, EMPTY)
        self.assertEqual(1, len(errors))

    def test_a_bound_receiver_member_pairs_and_the_other_takes_the_rest(self):
        # `?>`'s `value: TIn | E` against `Int | Oops` once the lambda has
        # bound TIn = Int: Int pairs with TIn, E takes Oops.
        _r, bindings, errors = t.merge(union(hole("T@c"), hole("E@c")), union(INT, STR),
                                       {"T@c": INT, "E@c": None}, EMPTY)
        self.assertEqual([], errors)
        self.assertEqual(STR, bindings["E@c"])

    def test_two_holes_have_no_partition(self):
        _r, bindings, _e = t.merge(union(INT, STR), union(hole("A@c"), hole("B@c")),
                                   {"A@c": None, "B@c": None}, EMPTY, callee_left=False)
        self.assertEqual({"A@c": None, "B@c": None}, bindings)


class TestNoBindingToAnUnresolvedSpelling(TestCase):
    """A raw NamedSpec only means something in its declaring scope: a named
    hole never binds to a type still holding one (it would carry the raw
    name into the caller's type arguments). The fixpoint retries once it
    resolves."""

    def test_a_named_hole_waits_for_an_unresolved_argument(self):
        raw = enum(_LIST, t.NamedSpec(lr, "Foo"))
        _r, bindings, errors = t.merge(hole("T@c"), raw, {"T@c": None}, EMPTY)
        self.assertEqual({"T@c": None}, bindings)
        self.assertEqual([], errors)


class TestReceives(TestCase):
    """`receives`: the value fits the receiver as it stands — nothing
    contradicts and nothing is filled (converge's widest type, the hints'
    bounds)."""

    def test_a_view_fits_its_wider_view(self):
        circle = enum(_SHAPE, leaves=("Circle@1",))
        self.assertTrue(t.receives(enum(_SHAPE), circle, EMPTY))
        self.assertFalse(t.receives(circle, enum(_SHAPE), EMPTY))

    def test_filling_a_hole_is_not_fitting(self):
        self.assertFalse(t.receives(enum(_LIST, hole()), enum(_LIST, INT), EMPTY))

    def test_a_union_fits_itself_in_any_order(self):
        self.assertTrue(t.receives(union(INT, STR), union(STR, INT), EMPTY))
        self.assertTrue(t.receives(union(INT, STR, UNIT), INT, EMPTY))


class TestAgreementTakesThePositionsVariance(TestCase):
    """A bound named hole agrees with what it meets under that POSITION's
    variance: invariant inside generic arguments, a plain fit elsewhere. A
    lambda's `(String | ()) => …` takes the bound `T = String` of
    `map(xs: List<T>, f: (:T): U)`; T stays String."""

    def test_a_bound_hole_fits_a_wider_callable_parameter(self):
        declared = tup((None, enum(_LIST, hole("T@c"))), (None, fn([hole("T@c")], hole("U@c"))))
        actual = tup((None, enum(_LIST, STR)), (None, fn([union(STR, UNIT)], INT)))
        _r, bindings, errors = t.merge(declared, actual, {"T@c": STR, "U@c": None}, EMPTY)
        self.assertEqual([], errors)
        self.assertEqual(STR, bindings["T@c"])
        self.assertEqual(INT, bindings["U@c"])

    def test_a_callable_parameter_still_fills_the_bindings_holes(self):
        # fold(xs, (Dict(), 0), (acc: (d: Dict<Int>, i: Int), x) => ...): A is
        # bound to the init's holey, unnamed tuple; the lambda's parameter
        # fills its holes and names.
        holey = tup((None, enum(_LIST, hole("K@free"))), (None, INT))
        full = tup(("d", enum(_LIST, INT)), ("i", INT))
        _r, bindings, errors = t.merge(fn([hole("A@c")], BOOL), fn([full], BOOL),
                                       {"A@c": holey}, EMPTY)
        self.assertEqual([], errors)
        self.assertEqual(full, bindings["A@c"])

    def test_a_callable_parameter_never_widens_the_binding(self):
        # map(circles, (v) => Named(v)): the lambda takes a Shape, T stays
        # Circle — a callable parameter never widens, even in a widening merge.
        circle = enum(_SHAPE, leaves=("Circle@1",))
        declared = tup((None, enum(_LIST, hole("T@c"))), (None, fn([hole("T@c")], BOOL)))
        actual = tup((None, enum(_LIST, circle)), (None, fn([enum(_SHAPE)], BOOL)))
        _r, bindings, errors = t.merge(declared, actual, {"T@c": None}, EMPTY, widen_views=True)
        self.assertEqual([], errors)
        self.assertEqual(circle, bindings["T@c"])

    def test_inside_a_generic_argument_agreement_is_exact(self):
        _r, _b, errors = t.merge(enum(_LIST, hole("T@c")), enum(_LIST, union(STR, UNIT)),
                                 {"T@c": STR}, EMPTY)
        self.assertEqual(1, len(errors))


class TestAHoleThatTookTheRestIsMatched(TestCase):
    def test_an_invariant_union_binds_its_hole_by_set_difference(self):
        # Stream<Grow<S>, Int, E | Bool> against Stream<…, Int, Never | Bool>:
        # inside generic arguments the union is invariant, and E, which took
        # the Never, is a matched member.
        never = enum(("Never@1", ()), leaves=())
        _r, bindings, errors = t.merge(enum(_LIST, union(hole("E@c"), BOOL)), enum(_LIST, union(never, BOOL)),
                                       {"E@c": None}, EMPTY)
        self.assertEqual([], errors)
        self.assertEqual(never, bindings["E@c"])


class TestAnUnknownMemberLeavesThePartitionOpen(TestCase):
    """A value union holding a member not known yet (an unresolved name) has
    no set difference: the receiver's hole stays unbound — no guess, no
    error — until the name resolves."""

    def test_the_hole_waits(self):
        raw = t.NamedSpec(lr, "Spec")
        _r, bindings, errors = t.merge(union(hole("T@c"), BOOL), union(raw, INT, BOOL),
                                       {"T@c": None}, EMPTY)
        self.assertEqual([], errors)
        self.assertEqual({"T@c": None}, bindings)
