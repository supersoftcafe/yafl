"""Representation dedup — merging IR entities that are indistinguishable.

Each test builds a small Application by hand, so the shapes under test are
exact: what must merge, what must not, and that every reference to a merged
entity lands on the survivor.
"""
from __future__ import annotations

import unittest

import codegen.typedecl as t
from codegen.gen import Application
from codegen.ir import Function, Object
from codegen.ops import JumpIf, Label, NewObject, Return
from codegen.param import (GlobalFunction, IntEqConst, Integer, ObjVtableEq, StackVar,
                           VtableDiscriminator)
from lowering.representation_dedup import merge_identical_representations

PTR = t.DataPointer()
THIS = t.Struct((("this", PTR),))


def obj(name: str, *, extends: tuple[str, ...] = (), functions=(), discriminator: int = 0,
        extra: tuple = ()) -> Object:
    return Object(name=name, extends=extends, functions=functions,
                  fields=t.ImmediateStruct((("type", PTR),) + extra),
                  discriminator=discriminator)


def fn(name: str, *ops, local: str = "x") -> Function:
    return Function(name=name, params=THIS, result=PTR,
                    stack_vars=t.Struct(((local, PTR),)), ops=tuple(ops))


def allocates(name: str, cls: str, local: str = "x") -> Function:
    v = StackVar(PTR, local)
    return fn(name, NewObject(cls, v), Return(v), local=local)


def app(objects=(), functions=()) -> Application:
    return Application(objects={o.name: o for o in objects},
                       functions={f.name: f for f in functions})


def entry(*callees: str) -> Function:
    """An entry point that keeps every callee referenced."""
    ops = []
    for i, callee in enumerate(callees):
        ops.append(Return(GlobalFunction(callee)) if i == len(callees) - 1
                   else JumpIf(f"l{i}", GlobalFunction(callee)))
    return fn("__entrypoint__", *ops)


def _pair(f: str, g: str, literal: int) -> tuple[Function, Function]:
    """f calls g; g returns `literal` or calls f. Different shapes, so the
    pair only merges with another pair, never with itself."""
    return (fn(f, Return(GlobalFunction(g))),
            fn(g, JumpIf("l", Integer(literal, 32)), Return(GlobalFunction(f)),
               Label("l"), Return(Integer(literal, 32))))


class TestMerges(unittest.TestCase):

    def test_functions_equal_up_to_local_names_merge(self):
        a = app([obj("A")], [allocates("f", "A", "x_inl1"), allocates("g", "A", "x_inl2"),
                            entry("f", "g")])
        out = merge_identical_representations(a)
        self.assertEqual(["f", "__entrypoint__"], list(out.functions))
        self.assertEqual("f", out.functions["__entrypoint__"].ops[1].value.name)

    def test_cycle_merges(self):
        """A vtable whose method allocates that same vtable: a bottom-up
        merge can never start, refinement merges both pairs at once."""
        a = app([obj("A", functions=(("m", "fa"),)), obj("B", functions=(("m", "fb"),))],
                [allocates("fa", "A"), allocates("fb", "B"), entry("fa", "fb")])
        out = merge_identical_representations(a)
        self.assertEqual(["A"], list(out.objects))
        self.assertEqual(["fa", "__entrypoint__"], list(out.functions))
        self.assertEqual(NewObject("A", StackVar(PTR, "x")), out.functions["fa"].ops[0])

    def test_external_name_is_not_a_reference(self):
        """An external function's name is a C symbol: a merged function of
        the same name must not redirect it."""
        ext = fn("h", Return(GlobalFunction("g", external=True)))
        a = app([obj("A")], [allocates("f", "A"), allocates("g", "A"), ext,
                            entry("f", "g", "h")])
        out = merge_identical_representations(a)
        self.assertNotIn("g", out.functions)
        self.assertEqual("g", out.functions["h"].ops[0].value.name)

    def test_mutually_recursive_functions_merge(self):
        """f1 <-> g1 and f2 <-> g2 with no object in the cycle: each needs
        the other's group decided first, so only refinement merges them."""
        a = app([], [*_pair("f1", "g1", 1), *_pair("f2", "g2", 1), entry("f1", "f2")])
        out = merge_identical_representations(a)
        self.assertEqual(["f1", "g1", "__entrypoint__"], list(out.functions))
        self.assertEqual("f1", out.functions["__entrypoint__"].ops[1].value.name)

    def test_types_compare_by_their_own_equality(self):
        """FuncPointer.sync is a refinement that equality ignores."""
        a = app([obj("A", extra=(("f", t.FuncPointer(sync=True)),)),
                 obj("B", extra=(("f", t.FuncPointer(sync=False)),))],
                [allocates("f", "A"), allocates("g", "B"), entry("f", "g")])
        self.assertEqual(["A"], list(merge_identical_representations(a).objects))

    def test_leaves_of_different_enums_merge_and_dispatch_follows(self):
        a = app([obj("R1"), obj("R2"),
                 obj("R1.a", extends=("R1",), discriminator=1),
                 obj("R2.a", extends=("R2",), discriminator=2)],
                [allocates("f", "R1.a"), allocates("g", "R2.a"),
                 fn("test2", JumpIf("l", IntEqConst(VtableDiscriminator(StackVar(PTR, "x")), 2)),
                    Label("l"), Return(StackVar(PTR, "x"))),
                 entry("f", "g", "test2")])
        out = merge_identical_representations(a)
        self.assertEqual(["R1", "R1.a"], list(out.objects))
        self.assertEqual(1, out.functions["test2"].ops[0].condition.const_val)


class TestKeepsApart(unittest.TestCase):

    def test_different_literals(self):
        a = app([], [fn("f", Return(Integer(1, 32))), fn("g", Return(Integer(2, 32))),
                     entry("f", "g")])
        self.assertEqual(3, len(merge_identical_representations(a).functions))

    def test_discriminator_test_is_not_a_plain_test(self):
        """`v->vtable->discriminator == 19` is not `v == 19`, even when 19
        names no leaf."""
        sv = StackVar(PTR, "x")
        a = app([], [fn("f", Return(IntEqConst(VtableDiscriminator(sv), 19))),
                     fn("g", Return(IntEqConst(sv, 19))), entry("f", "g")])
        self.assertEqual(3, len(merge_identical_representations(a).functions))

    def test_difference_travels_round_a_cycle(self):
        """g2 differs from g1 only in a literal; f2 differs from f1 only in
        which of them it calls. Refinement must split both pairs."""
        a = app([], [*_pair("f1", "g1", 1), *_pair("f2", "g2", 2), entry("f1", "f2")])
        self.assertEqual(5, len(merge_identical_representations(a).functions))

    def test_different_layouts(self):
        a = app([obj("A"), obj("B", extra=(("n", t.Int(32)),))],
                [allocates("f", "A"), allocates("g", "B"), entry("f", "g")])
        out = merge_identical_representations(a)
        self.assertEqual(["A", "B"], list(out.objects))
        self.assertEqual(3, len(out.functions))

    def test_instance_tested_object(self):
        """`is A` must stay false for a B."""
        test = fn("t", Return(ObjVtableEq(StackVar(PTR, "x"), class_name="A")))
        a = app([obj("A"), obj("B")],
                [allocates("f", "A"), allocates("g", "B"), test, entry("f", "g", "t")])
        self.assertEqual(["A", "B"], list(merge_identical_representations(a).objects))

    def test_sibling_leaves(self):
        """Two leaves of one enum with the same layout: a dispatch over the
        enum tells them apart by discriminator."""
        a = app([obj("R"), obj("R.a", extends=("R",), discriminator=1),
                 obj("R.b", extends=("R",), discriminator=2)],
                [allocates("f", "R.a"), allocates("g", "R.b"), entry("f", "g")])
        out = merge_identical_representations(a)
        self.assertEqual(["R", "R.a", "R.b"], list(out.objects))

    def test_stray_discriminator_read_blocks_leaf_merges(self):
        """A discriminator read outside a comparison hides which integers are
        leaf ids, so no leaf may merge."""
        stray = fn("s", Return(VtableDiscriminator(StackVar(PTR, "x"))))
        a = app([obj("R1"), obj("R2"),
                 obj("R1.a", extends=("R1",), discriminator=1),
                 obj("R2.a", extends=("R2",), discriminator=2)],
                [allocates("f", "R1.a"), allocates("g", "R2.a"), stray, entry("f", "g", "s")])
        out = merge_identical_representations(a)
        self.assertIn("R1.a", out.objects)
        self.assertIn("R2.a", out.objects)

    def test_entry_point_survives(self):
        a = app([], [fn("a", Return(Integer(0, 32))), fn("__entrypoint__", Return(Integer(0, 32)))])
        self.assertIn("__entrypoint__", merge_identical_representations(a).functions)

    def test_profile_is_untouched(self):
        a = app([obj("A")], [allocates("f", "A"), allocates("g", "A"), entry("f", "g")])
        a.profile = True
        self.assertIs(a, merge_identical_representations(a))


if __name__ == "__main__":
    unittest.main()
