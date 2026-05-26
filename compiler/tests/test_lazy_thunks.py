from tests.testutil import TimedTestCase as TestCase

import codegen.typedecl as t
from codegen.gen import Application

import lowering.lazy_thunks as lt


class TestLazyThunks(TestCase):
    """Step-1 sanity checks: stub class shape, fetch + finisher generation,
    and dedup via ensure_lazy_machinery.

    Wiring `[lazy]` lets to these helpers is Step 2 — those tests will
    actually compile and run programs.
    """

    def test_stub_object_layout(self):
        obj = lt.make_stub_object(t.DataPointer())
        self.assertEqual(obj.name, "Lazy$ptr")
        names = [n for n, _ in obj.fields.fields]
        self.assertEqual(names, ["type", "flag", "closure", "value"])
        type_map = dict(obj.fields.fields)
        self.assertEqual(type_map["type"],    t.DataPointer())
        self.assertEqual(type_map["flag"],    t.DataPointer())
        self.assertEqual(type_map["closure"], t.FuncPointer())
        self.assertEqual(type_map["value"],   t.DataPointer())

    def test_fetch_function_basic_shape(self):
        fn = lt.make_fetch_function(t.DataPointer())
        self.assertEqual(fn.name, "lazy_fetch$ptr")
        # DataPointer wraps to itself — no TaskWrapper.
        self.assertEqual(fn.result, t.DataPointer())
        self.assertTrue(fn.bypass_async)
        self.assertEqual(tuple(n for n, _ in fn.params.fields), ("this",))

    def test_fetch_function_int32_uses_wrapped_return(self):
        """Non-pointer values get wrap_return_type → TaskWrapper(T)."""
        fn = lt.make_fetch_function(t.Int(32))
        self.assertEqual(fn.name, "lazy_fetch$i32")
        self.assertIsInstance(fn.result, t.TaskWrapper)
        self.assertEqual(fn.result.inner, t.Int(32))

    def test_waiter_subtype_name_matches_async_lower(self):
        """The waiter task subtype shares its name with the one
        async_lower auto-emits for the fetch function's wrapped return
        type — so ObjectField casts on a completed task land on the
        actual struct, not a layout-twin."""
        from lowering.task_abi import task_subtype_name, wrap_return_type
        # DataPointer values share the runtime-defined task_obj.
        self.assertEqual(lt.waiter_subtype_name(t.DataPointer()), "task_obj")
        # Scalar values get a per-precision subtype.
        self.assertEqual(lt.waiter_subtype_name(t.Int(32)), "task$Int32")
        # The name matches what async_lower would assign to the fetch
        # function's wrapped result.
        for ty in (t.DataPointer(), t.Int(32), t.Float(64)):
            self.assertEqual(lt.waiter_subtype_name(ty),
                             task_subtype_name(wrap_return_type(ty)))

    def test_finisher_function_basic_shape(self):
        fn = lt.make_finisher_function(t.DataPointer())
        self.assertEqual(fn.name, "lazy_finish$ptr")
        self.assertEqual(fn.result, t.DataPointer())
        self.assertTrue(fn.bypass_async)
        self.assertEqual(
            tuple(n for n, _ in fn.params.fields),
            ("this", "completed"),
        )

    def test_ensure_is_idempotent(self):
        app = Application()
        cls1 = lt.ensure_lazy_machinery(app, t.DataPointer())
        cls2 = lt.ensure_lazy_machinery(app, t.DataPointer())
        self.assertEqual(cls1, cls2)
        self.assertEqual(cls1, "Lazy$ptr")
        # Three objects (stub + foreign task base + canonical waiter
        # task subtype), three functions (fetch + finisher + drain).
        # The waiter subtype is registered under its async_lower-shared
        # name (`task_obj` for DataPointer) so ObjectField casts on a
        # completed task land on the actual emitted struct.
        self.assertIn("Lazy$ptr",            app.objects)
        self.assertIn("task",                app.objects)
        self.assertIn("task_obj",            app.objects)
        self.assertIn("lazy_fetch$ptr",      app.functions)
        self.assertIn("lazy_finish$ptr",    app.functions)
        self.assertIn("lazy_drain$ptr",      app.functions)
        self.assertEqual(len(app.objects),   3)
        self.assertEqual(len(app.functions), 3)

    def test_unsupported_value_type_raises(self):
        with self.assertRaises(NotImplementedError):
            lt.make_stub_object(t.FuncPointer())
        with self.assertRaises(NotImplementedError):
            lt.make_fetch_function(t.FuncPointer())

    def test_ir_mangle_roundtrip(self):
        for ty in (t.DataPointer(),
                   t.Int(8), t.Int(16), t.Int(32), t.Int(64),
                   t.Float(32), t.Float(64)):
            self.assertEqual(lt.ir_mangle_to_type(lt._ir_mangle(ty)), ty)

    def test_object_pointer_mask_includes_pointer_fields(self):
        """The stub's GC pointer mask must mark flag, closure.o, and value
        (when value is a pointer type) so the GC keeps waiter chains, the
        captured init env, and the cached value alive."""
        obj = lt.make_stub_object(t.DataPointer())
        # get_pointer_paths returns the GC-traversal paths within the
        # struct (excluding the leading vtable `type` field).
        paths = []
        for name, ft in obj.fields.fields[1:]:
            paths.extend(ft.get_pointer_paths(name))
        self.assertIn("flag",      paths)   # the chain root
        self.assertIn("closure.o", paths)   # captured env in init closure
        self.assertIn("value",     paths)   # for DataPointer value type
