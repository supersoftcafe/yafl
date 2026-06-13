from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase

from codegen.param import StackVar, Integer, ObjectField
from codegen.ops import Return, Move
from codegen.things import Function, Object
from codegen.typedecl import ImmediateStruct, Struct, Int, DataPointer, FuncPointer, Array


class TestFunction(TestCase):
    def test_constructor_ok(self):
        Function(
            name="test",
            params=Struct((("this", DataPointer()),)),
            result=DataPointer(),
            stack_vars=Struct(()),
            ops=())

    def test_constructor_fail(self):
        self.assertRaisesRegex(ValueError, "require a first parameter", Function,
                               name="test",
                               params=Struct(()),
                               result=DataPointer(),
                               stack_vars=Struct(()),
                               ops=())

    def test_to_c(self):
        type_cache = {}
        lr = StackVar(FuncPointer(), "something")
        function = Function("testfun", Struct( (("this", DataPointer()), ("something", FuncPointer())) ), Int(32), Struct(()), (Return(lr),))

        str = function.to_c_prototype(type_cache)
        print(str)

        str = function.to_c_implement(type_cache)
        print(str)


class TestObject(TestCase):
    cache = {}
    target = Object(
        name="test",
        extends=(),
        functions=(),
        fields=ImmediateStruct((("type", DataPointer()), ("ref", FuncPointer()), ("length", Int(32)), ("array", Array(Int(16), 0)))),
        length_field="length")

    def construct_with_fields(self, fields: Struct):
        return Object(
            name="test",
            extends=(),
            functions=(),
            fields=fields)

    def test_empty_fields_is_not_allowed(self):
        def create():
            self.construct_with_fields(Struct( fields = () ))
        self.assertRaises(ValueError, create)

    def test_array_type(self):
        self.assertEqual(Int(16), self.target.array_type)

    def test_get_pointer_mask(self):
        mask = self.target.get_pointer_mask(self.cache)
        self.assertRegex(mask, r'\(0\|maskof\(')
        self.assertRegex(mask, r'\.ref')
        self.assertRegex(mask, r'\.ref\.o')
        self.assertNotRegex(mask, r'array')
        self.assertNotRegex(mask, r'type')

    def test_get_array_pointer_mask(self):
        mask = self.target.get_array_pointer_mask(self.cache)
        self.assertEqual("(0)", mask)


class TestCseHeapInvalidation(TestCase):
    """Common-subexpression elimination must treat a heap dereference
    (ObjectField / ArrayElement) as invalidated by any intervening heap write.

    Regression: an async state object's coalesced array slot is read, then
    overwritten with a different logical variable, then read again. CSE used to
    cache the first read and reuse it for the second, substituting the slot's
    previous occupant for its current one (e.g. a path string where a line
    number belonged). See codegen.things.eliminate_common_subexpressions.
    """

    def _slot(self):
        state = StackVar(DataPointer(), "$state")
        return ObjectField(DataPointer(), state, "S", "array", Integer(3, 32))

    def test_no_reuse_across_intervening_heap_write(self):
        slot = self._slot()
        x   = StackVar(DataPointer(), "x")
        y   = StackVar(DataPointer(), "y")
        src = StackVar(DataPointer(), "src")
        fn = Function(
            name="t",
            params=Struct((("$state", DataPointer()),)),
            result=DataPointer(),
            stack_vars=Struct((("x", DataPointer()), ("y", DataPointer()), ("src", DataPointer()))),
            ops=(Move(x, slot), Move(slot, src), Move(y, slot), Return(y)))
        out = fn.eliminate_common_subexpressions()
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
        x = StackVar(DataPointer(), "x")
        y = StackVar(DataPointer(), "y")
        fn = Function(
            name="t",
            params=Struct((("$state", DataPointer()),)),
            result=DataPointer(),
            stack_vars=Struct((("x", DataPointer()), ("y", DataPointer()))),
            ops=(Move(x, slot), Move(y, slot), Return(y)))
        out = fn.eliminate_common_subexpressions()
        ret = next(op for op in out.ops if isinstance(op, Return))
        self.assertEqual(ret.value, x, "CSE should still coalesce a genuine duplicate heap read")

