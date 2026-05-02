from tests.testutil import TimedTestCase as TestCase

import codegen.param as e
import codegen.ops as o
import codegen.typedecl as t

from codegen.gen import Application
from codegen.things import Function, Object

import lowering.globalfuncs
import lowering.globalinit
import lowering.inlining
import lowering.deadstores
import lowering.async_lower as lowering_cps
import lowering.trim
import lowering.staticinit


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

    def test_async_lower_preserves_discriminators(self):
        result = lowering_cps.lower_async(self._app_with_discriminators())
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


class TestFlattenRParam(TestCase):
    """NewStruct.flatten and InitArray.flatten must return a flat list of RParam.

    The old implementations used `[item.flatten() for item in ...]` which produced
    nested sub-lists — e.g. `[NewStruct, [GlobalVar]]` instead of `[NewStruct, GlobalVar]`.
    globalinit iterates op.all_params() (which calls flatten()) looking for GlobalVar
    instances via isinstance(); a sub-list never matches, so globals nested inside
    NewStruct or InitArray parameters were silently skipped.
    """

    def _global_var(self) -> e.GlobalVar:
        return e.GlobalVar(t.DataPointer(), "some_global")

    def test_new_struct_flatten_is_flat(self):
        """NewStruct.flatten() must return a flat list with no nested sub-lists."""
        gv = self._global_var()
        ns = e.NewStruct((("x", gv),))
        result = ns.flatten()
        for item in result:
            self.assertIsInstance(
                item, e.RParam,
                f"flatten() returned a non-RParam element {type(item)}: {item!r}",
            )
        self.assertIn(
            gv,
            result,
            "flatten() must include the nested GlobalVar directly, not as a sub-list",
        )

    def test_init_array_flatten_is_flat(self):
        """InitArray.flatten() must return a flat list with no nested sub-lists."""
        gv = self._global_var()
        ia = e.InitArray(t.DataPointer(), (gv,))
        result = ia.flatten()
        for item in result:
            self.assertIsInstance(
                item, e.RParam,
                f"flatten() returned a non-RParam element {type(item)}: {item!r}",
            )
        self.assertIn(
            gv,
            result,
            "flatten() must include the nested GlobalVar directly, not as a sub-list",
        )


class TestPromoteStaticObjectsCounter(TestCase):
    def test_non_numeric_si_global_does_not_raise(self):
        """promote_static_objects must not crash when a global name starts with '$si$'
        but has a non-numeric suffix.

        The old implementation parsed existing global names with
        int(n.split("$si$")[1]), which raises ValueError for any name like
        '$si$bogus'.  The fix replaces the name-parsing counter with a
        module-level itertools.count() that never inspects global names.
        """
        from codegen.things import Global

        app = Application()
        app.globals["$si$bogus"] = Global(name="$si$bogus", type=t.DataPointer())

        # Must not raise ValueError
        try:
            lowering.staticinit.promote_static_objects(app)
        except ValueError as exc:
            self.fail(
                f"promote_static_objects raised ValueError on a non-numeric $si$ "
                f"global name: {exc}"
            )


class TestParallelCallDeadStore(TestCase):
    """eliminate_dead_stores must drop a ParallelCall whose outputs are never read,
    and must preserve one whose register is consumed by a subsequent op."""

    def _make_app(self, ops: tuple) -> Application:
        """Wrap ops in a minimal one-function Application."""
        app = Application()
        all_vars: list[tuple[str, t.Type]] = []
        for op in ops:
            _, writes = op.get_live_vars()
            for sv in writes:
                all_vars.append((sv.name, sv.get_type()))
        app.functions["__entrypoint__"] = Function(
            name="__entrypoint__",
            params=t.Struct(fields=(("this", t.DataPointer()),)),
            result=t.Void(),
            stack_vars=t.Struct(fields=tuple(all_vars)),
            ops=ops,
        )
        return app

    def test_dead_parallel_call_is_dropped(self):
        """A ParallelCall whose results are never read must be eliminated entirely."""
        r0 = e.StackVar(t.DataPointer(), "$r0")
        r1 = e.StackVar(t.DataPointer(), "$r1")
        pc = o.ParallelCall(
            calls=(e.GlobalFunction("fn_a"), e.GlobalFunction("fn_b")),
            results=(r0, r1),
            register=None,
        )
        app = self._make_app((pc, o.ReturnVoid()))
        result = lowering.deadstores.eliminate_dead_stores(app)
        fn_ops = result.functions["__entrypoint__"].ops
        self.assertFalse(
            any(isinstance(op, o.ParallelCall) for op in fn_ops),
            "Dead ParallelCall must be eliminated when its results are never read",
        )

    def test_live_parallel_call_is_kept(self):
        """A ParallelCall whose register is consumed by a subsequent op must be kept."""
        r0 = e.StackVar(t.DataPointer(), "$r0")
        reg = e.StackVar(t.DataPointer(), "$reg")
        pc = o.ParallelCall(
            calls=(e.GlobalFunction("fn_a"),),
            results=(r0,),
            register=reg,
        )
        app = self._make_app((pc, o.Return(reg)))
        result = lowering.deadstores.eliminate_dead_stores(app)
        fn_ops = result.functions["__entrypoint__"].ops
        self.assertTrue(
            any(isinstance(op, o.ParallelCall) for op in fn_ops),
            "ParallelCall must be kept when its register is read by a subsequent op",
        )
