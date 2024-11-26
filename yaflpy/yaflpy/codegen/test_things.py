from __future__ import annotations

from unittest import TestCase

from codegen.param import StackVar
from codegen.ops import Return
from codegen.things import Function, Object
from codegen.typedecl import Struct, Int, DataPointer, FuncPointer, Array


class TestFunction(TestCase):
    def test_constructor_ok(self):
        Function(
            name="test",
            params=Struct((("this", DataPointer()),)),
            result=Int(),
            stack_vars=Struct(()),
            ops=())

    def test_constructor_fail(self):
        self.assertRaisesRegex(ValueError, "require a first parameter", Function,
                               name="test",
                               params=Struct(()),
                               result=Int(),
                               stack_vars=Struct(()),
                               ops=())

    def test_to_c(self):
        type_cache = {}
        lr = StackVar("something")
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
        fields=Struct((("type", DataPointer()), ("ref", FuncPointer()), ("length", Int(32)), ("array", Array(Int(16), 0)))),
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

