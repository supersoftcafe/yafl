"""Canonicalise — spelling equal code equally before representation dedup.

Each test builds a small Application by hand: what the stage rewrites, what it
must leave alone, and that dedup then merges what it could not before.
"""
from __future__ import annotations

import unittest

import codegen.typedecl as t
from codegen.gen import Application
from codegen.ir import Function, Global, Object
from codegen.ops import Jump, Label, Move, NewObject, Return
from codegen.param import ArrayElement, GlobalFunction, Integer, NewStruct, ObjectField, StackVar
from lowering.canonicalise import canonicalise
from lowering.representation_dedup import merge_identical_representations

PTR = t.DataPointer()
I64 = t.Int(64)
THIS = t.Struct((("this", PTR),))


def obj(name: str, *fields, foreign: bool = False, length_field: str | None = None) -> Object:
    return Object(name=name, extends=(), functions=(), is_foreign=foreign,
                  fields=t.ImmediateStruct((("type", PTR),) + fields), length_field=length_field)


def fn(name: str, *ops, locals_: tuple = (("x", PTR),)) -> Function:
    return Function(name=name, params=THIS, result=PTR,
                    stack_vars=t.Struct(locals_), ops=tuple(ops))


def app(objects=(), functions=(), globals_=()) -> Application:
    return Application(objects={o.name: o for o in objects},
                       functions={f.name: f for f in functions},
                       globals={g.name: g for g in globals_})


def entry(*callees: str) -> Function:
    return fn("__entrypoint__", Return(NewStruct(tuple((f"_{i}", GlobalFunction(c))
                                                       for i, c in enumerate(callees)))))


class TestDebris(unittest.TestCase):

    def test_locals_left_unused_by_the_cleanups_are_dropped(self):
        """copy_propagate removes `y = x`; y is then declared for nothing."""
        x, y = StackVar(PTR, "x"), StackVar(PTR, "y")
        f = fn("f", NewObject("A", x), Move(y, x), Return(y), locals_=(("x", PTR), ("y", PTR)))
        out = canonicalise(app([obj("A")], [f]))
        self.assertEqual((("x", PTR),), out.functions["f"].stack_vars.fields)
        self.assertEqual((NewObject("A", x), Return(x)), out.functions["f"].ops)

    def test_debris_no_longer_keeps_instances_apart(self):
        """A copy and a jump to the next label: the emitter would remove both,
        so after this stage the two instances are the same function."""
        x, y = StackVar(PTR, "x"), StackVar(PTR, "y")
        f = fn("f", NewObject("A", x), Return(x))
        g = fn("g", NewObject("A", x), Jump("l"), Label("l"), Move(y, x), Return(y),
               locals_=(("x", PTR), ("y", PTR)))
        a = app([obj("A")], [f, g, entry("f", "g")])
        self.assertEqual(3, len(merge_identical_representations(a).functions))
        self.assertEqual(2, len(merge_identical_representations(canonicalise(a)).functions))


class TestObjectFields(unittest.TestCase):

    def test_fields_and_every_access_become_positional(self):
        x = StackVar(PTR, "x")
        read = ObjectField(I64, x, "A", "v@abcdef", None)
        f = fn("f", NewObject("A", x), Return(read))
        out = canonicalise(app([obj("A", ("v@abcdef", I64))], [f]))
        self.assertEqual((("type", PTR), ("$f1", I64)), out.objects["A"].fields.fields)
        self.assertEqual("$f1", out.functions["f"].ops[1].value.field)

    def test_array_objects_keep_array_and_rename_their_length(self):
        x = StackVar(PTR, "x")
        arr = obj("B", ("len@abcdef", t.Int(32)), ("array", t.Array(PTR, 0)), length_field="len@abcdef")
        elem = ArrayElement(PTR, x, "B", "array", "len@abcdef", Integer(0, 32))
        out = canonicalise(app([arr], [fn("f", Return(elem))]))
        self.assertEqual("$f1", out.objects["B"].length_field)
        self.assertEqual("array", out.objects["B"].fields.fields[-1][0])
        self.assertEqual(("array", "$f1"), (out.functions["f"].ops[0].value.field,
                                            out.functions["f"].ops[0].value.length_field))

    def test_foreign_objects_keep_their_names(self):
        task = obj("task", ("state", I64), foreign=True)
        self.assertEqual(task, canonicalise(app([task])).objects["task"])

    def test_static_instances_follow_their_object(self):
        g = Global("s", PTR, init=NewStruct((("v@abcdef", Integer(7, 64)),)), object_name="A")
        out = canonicalise(app([obj("A", ("v@abcdef", I64))], globals_=[g]))
        self.assertEqual((("$f1", Integer(7, 64)),), out.globals["s"].init.values)

    def test_same_layout_under_different_names_now_merges(self):
        x = StackVar(PTR, "x")
        fa = fn("fa", NewObject("A", x), Return(ObjectField(I64, x, "A", "v@aaaaaa", None)))
        fb = fn("fb", NewObject("B", x), Return(ObjectField(I64, x, "B", "w@bbbbbb", None)))
        a = app([obj("A", ("v@aaaaaa", I64)), obj("B", ("w@bbbbbb", I64))], [fa, fb, entry("fa", "fb")])
        self.assertEqual(2, len(merge_identical_representations(a).objects))
        merged = merge_identical_representations(canonicalise(a))
        self.assertEqual(["A"], list(merged.objects))
        self.assertEqual(["fa", "__entrypoint__"], list(merged.functions))


class TestProfile(unittest.TestCase):

    def test_profile_is_untouched(self):
        a = app([obj("A", ("v@abcdef", I64))])
        a.profile = True
        self.assertIs(a, canonicalise(a))


if __name__ == "__main__":
    unittest.main()
