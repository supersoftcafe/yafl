"""Cleanup — the one per-function cleanup chain, before dedup and emission.

Built by hand like tests/test_canonicalise.py: what the stage removes, the
locals it leaves unused, and that dedup then merges what it could not.
"""
from __future__ import annotations

import unittest

import codegen.typedecl as t
from codegen.gen import Application
from codegen.ir import Function, Object
from codegen.ops import Jump, Label, Move, NewObject, Return
from codegen.param import GlobalFunction, Integer, NewStruct, ObjectField, StackVar
from lowering.cleanup import clean_functions
from lowering.representation_dedup import merge_identical_representations

PTR = t.DataPointer()
THIS = t.Struct((("this", PTR),))


def obj(name: str) -> Object:
    return Object(name=name, extends=(), functions=(), fields=t.ImmediateStruct((("type", PTR),)))


def fn(name: str, *ops, locals_: tuple = (("x", PTR),)) -> Function:
    return Function(name=name, params=THIS, result=PTR,
                    stack_vars=t.Struct(locals_), ops=tuple(ops))


def app(objects=(), functions=()) -> Application:
    return Application(objects={o.name: o for o in objects},
                       functions={f.name: f for f in functions})


def entry(*callees: str) -> Function:
    return fn("__entrypoint__", Return(NewStruct(tuple((f"_{i}", GlobalFunction(c))
                                                       for i, c in enumerate(callees)))))


class TestDebris(unittest.TestCase):

    def test_locals_left_unused_by_the_cleanups_are_dropped(self):
        """copy_propagate removes `y = x`; y is then declared for nothing."""
        x, y = StackVar(PTR, "x"), StackVar(PTR, "y")
        f = fn("f", NewObject("A", x), Move(y, x), Return(y), locals_=(("x", PTR), ("y", PTR)))
        out = clean_functions(app([obj("A")], [f]))
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
        self.assertEqual(2, len(merge_identical_representations(clean_functions(a)).functions))



class TestEveryLevel(unittest.TestCase):

    def test_profile_is_cleaned_too(self):
        """Emission no longer cleans, so this stage must run under --profile."""
        x, y = StackVar(PTR, "x"), StackVar(PTR, "y")
        a = app([obj("A")], [fn("f", NewObject("A", x), Move(y, x), Return(y),
                                locals_=(("x", PTR), ("y", PTR)))])
        a.profile = True
        self.assertEqual((NewObject("A", x), Return(x)), clean_functions(a).functions["f"].ops)


class TestCseHeapInvalidation(unittest.TestCase):
    """Common-subexpression elimination must treat a heap dereference
    (ObjectField / ArrayElement) as invalidated by any intervening heap write.

    Regression: an async state object's coalesced array slot is read, then
    overwritten with a different logical variable, then read again. CSE used to
    cache the first read and reuse it for the second, substituting the slot's
    previous occupant for its current one (e.g. a path string where a line
    number belonged). The CSE lives in lowering/cleanup.py; tested through the stage.
    """

    def _slot(self):
        state = StackVar(PTR, "$state")
        return ObjectField(PTR, state, "S", "array", Integer(3, 32))

    def test_no_reuse_across_intervening_heap_write(self):
        slot = self._slot()
        x   = StackVar(PTR, "x")
        y   = StackVar(PTR, "y")
        src = StackVar(PTR, "src")
        fn = Function(
            name="t",
            params=t.Struct((("$state", PTR),)),
            result=PTR,
            stack_vars=t.Struct((("x", PTR), ("y", PTR), ("src", PTR))),
            ops=(Move(x, slot), Move(slot, src), Move(y, slot), Return(y)))
        out = clean_functions(Application(functions={"t": fn})).functions["t"]
        # y's read of the slot must survive (not collapsed into x), because the
        # slot was rewritten between the two reads.
        y_reads = [op for op in out.ops
                   if isinstance(op, Move) and isinstance(op.target, StackVar)
                   and op.target.name == "y"]
        self.assertTrue(y_reads, "y = slot was wrongly eliminated across a heap write")
        self.assertEqual(y_reads[0].source, slot)
        ret = next(op for op in out.ops if isinstance(op, Return))
        self.assertEqual(ret.value, y)

    def test_reuse_when_no_intervening_write(self):
        # Sanity: a genuine duplicate heap read (no write between) is still
        # coalesced, so the fix is precise rather than disabling CSE.
        slot = self._slot()
        x = StackVar(PTR, "x")
        y = StackVar(PTR, "y")
        fn = Function(
            name="t",
            params=t.Struct((("$state", PTR),)),
            result=PTR,
            stack_vars=t.Struct((("x", PTR), ("y", PTR))),
            ops=(Move(x, slot), Move(y, slot), Return(y)))
        out = clean_functions(Application(functions={"t": fn})).functions["t"]
        ret = next(op for op in out.ops if isinstance(op, Return))
        self.assertEqual(ret.value, x, "CSE should still coalesce a genuine duplicate heap read")


if __name__ == "__main__":
    unittest.main()
