from unittest import TestCase

import codegen.param as e
import codegen.ops as o
import codegen.typedecl as t

from codegen.gen import Application
from codegen.things import Function, Object


class TestApplication(TestCase):
    app = Application()

    # def test_gen(self):
    #     g = Application()
    #     g.functions["fun_dosomething"] = Function(
    #         name = "fun_dosomething",
    #         params = t.Struct(fields = ( ("this", t.DataPointer()), ) ),
    #         result = t.Int(32),
    #         stack_vars= t.Struct(fields = ()),
    #         ops = (
    #             o.Return(e.Integer(-1, 32)),
    #         )
    #     )
    #     g.functions["__entrypoint__"] = Function(
    #         name = "__entrypoint__",
    #         params = t.Struct(fields = ( ("this", t.DataPointer()), ) ),
    #         result = t.Int(32),
    #         stack_vars= t.Struct(fields = (("pointer", t.DataPointer()), ("result", t.Int(32)))),
    #         ops = (
    #             o.Move(e.StackVar(t.DataPointer(), "pointer"), e.NewObject("obj_leaf")),
    #             o.Call(
    #                 function = e.VirtualFunction("dosomething", e.StackVar(t.DataPointer(), "pointer")),
    #                 parameters = e.NewStruct(t.Struct( () ), () ),
    #                 register = e.StackVar(t.Int(32), "result" )),
    #             o.Return(e.StackVar(t.Int(32), "result")),
    #         )
    #     )
    #     g.objects["obj_leaf"] = Object(
    #         name = "obj_leaf",
    #         extends = (),
    #         functions = ( ("dosomething", "fun_dosomething"), ),
    #         fields = t.Struct( fields = (("type", t.DataPointer()), ) )
    #     )
    #
    #     code = g.gen()
    #     print(code)

