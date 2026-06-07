from tests.testutil import TimedTestCase as TestCase

import codegen.param as e
import codegen.ops as o
import codegen.typedecl as t

from codegen.gen import Application
from codegen.things import Function, Object

import lowering.globalfuncs
import lowering.lower_lazy_lets
import lowering.inlining
import lowering.deadstores
import lowering.async_lower as async_lower
import lowering.sync_inference
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

    def test_lower_lazy_lets_preserves_discriminators(self):
        result = lowering.lower_lazy_lets.lower_lazy_lets([])  # statement-list pass; empty input is fine
        self.assertEqual(result, [])  # sanity: no statements in, no statements out

    def test_async_lower_preserves_discriminators(self):
        result = async_lower.lower_async(self._app_with_discriminators())
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


class TestSyncInferenceTaggedTaskReturn(TestCase):
    """A function that returns a tagged task (e.g. the `[tail]` wrapper)
    must never be classified as sync — its callers see PTR_IS_TASK and
    must enter the async path.  Without this rule, sync_inference's
    "no non-tail Call ops" heuristic auto-classifies the wrapper as
    sync, then propagation marks its recursive caller sync, then the
    caller's IS_TASK check on the recursive return aborts."""

    def _wrapper_like(self) -> Function:
        """Mimic the shape of the `[tail]` wrapper: side-effecting
        Invoke-via-Move ops (no `Call` op), then `Return(TagTask(...))`."""
        sv_state = e.StackVar(t.DataPointer(), "$state")
        sv_discard = e.StackVar(t.DataPointer(), "$sv_tail_discard")
        return Function(
            name="loop_wrapper",
            params=t.Struct(fields=(("this", t.DataPointer()),)),
            result=t.DataPointer(),
            stack_vars=t.Struct(fields=(("$state", t.DataPointer()),
                                        ("$sv_tail_discard", t.DataPointer()))),
            ops=(
                o.NewObject("loop$tailstate", sv_state),
                o.Move(sv_discard,
                       e.Invoke("thread_dispatch",
                                e.NewStruct((("action",
                                              e.GlobalFunction("loop$tailcallback", sv_state)),)),
                                t.DataPointer()),
                       keep=True),
                o.Return(e.TagTask(sv_state, t.DataPointer())),
            ),
            sync=False,
        )

    def test_tagged_task_return_excluded_from_sync_set(self):
        app = Application()
        app.functions["loop_wrapper"] = self._wrapper_like()
        result = lowering.sync_inference.infer_sync(app)
        self.assertFalse(
            result.functions["loop_wrapper"].sync,
            "A function returning TagTask(...) must not be classified as sync",
        )

    def test_caller_of_tagged_task_returner_is_not_sync(self):
        """Propagation must also see that the wrapper is async — a caller
        whose only non-tail Call targets the wrapper must stay async."""
        app = Application()
        app.functions["loop_wrapper"] = self._wrapper_like()
        sv_result = e.StackVar(t.DataPointer(), "$r")
        app.functions["loop_tailimpl"] = Function(
            name="loop_tailimpl",
            params=t.Struct(fields=(("this", t.DataPointer()),)),
            result=t.DataPointer(),
            stack_vars=t.Struct(fields=(("$r", t.DataPointer()),)),
            ops=(
                o.Call(function=e.GlobalFunction("loop_wrapper"),
                       parameters=e.NewStruct(()),
                       register=sv_result),
                o.Return(sv_result),
            ),
            sync=False,
        )
        result = lowering.sync_inference.infer_sync(app)
        self.assertFalse(
            result.functions["loop_tailimpl"].sync,
            "A function whose only callee returns a tagged task must stay async",
        )
