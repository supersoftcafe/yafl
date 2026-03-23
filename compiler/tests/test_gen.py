from unittest import TestCase

import codegen.param as e
import codegen.ops as o
import codegen.typedecl as t

from codegen.gen import Application
from codegen.things import Function, Object

import lowering.globalfuncs
import lowering.globalinit
import lowering.inlining
import lowering.deadstores
import lowering.cps
import lowering.trim


class TestApplicationDiscriminatorPreservation(TestCase):
    """Lowering passes that rebuild Application must copy union_discriminators."""

    def _app_with_discriminators(self) -> Application:
        app = Application()
        app.union_discriminators = {"SomeType|None": 42}
        return app

    def test_globalfuncs_preserves_discriminators(self):
        result = lowering.globalfuncs.discover_global_function_calls(self._app_with_discriminators())
        self.assertEqual(result.union_discriminators, {"SomeType|None": 42})

    def test_inlining_preserves_discriminators(self):
        result = lowering.inlining.inline_small_functions(self._app_with_discriminators())
        self.assertEqual(result.union_discriminators, {"SomeType|None": 42})

    def test_deadstores_preserves_discriminators(self):
        result = lowering.deadstores.eliminate_dead_stores(self._app_with_discriminators())
        self.assertEqual(result.union_discriminators, {"SomeType|None": 42})

    def test_globalinit_preserves_discriminators(self):
        result = lowering.globalinit.add_ops_to_support_global_lazy_init(self._app_with_discriminators())
        self.assertEqual(result.union_discriminators, {"SomeType|None": 42})

    def test_cps_preserves_discriminators(self):
        result = lowering.cps.convert_application_to_cps(self._app_with_discriminators())
        self.assertEqual(result.union_discriminators, {"SomeType|None": 42})


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

