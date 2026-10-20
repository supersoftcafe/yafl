from tests.testutil import TimedTestCase as TestCase

import codegen.typedecl as t
from codegen.gen import Application

import lowering.lazy_thunks as lt
from codegen.ops import Return


class TestLazyThunks(TestCase):
    """Sanity checks: stub class shape, fetch and gate generation, and dedup
    via ensure_lazy_machinery. Programs using them are compiled and run by
    yafl_tests/lazy_lets.yafl."""

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
        """The fetch is ordinary pre-async code: async_lower converts it like
        any function, so it declares the value type and has one Return."""
        fn = lt.make_fetch_function(t.DataPointer())
        self.assertEqual(fn.name, "lazy_fetch$ptr")
        self.assertEqual(fn.result, t.DataPointer())
        self.assertFalse(fn.bypass_async)
        self.assertEqual(tuple(n for n, _ in fn.params.fields), ("this",))
        self.assertEqual(1, sum(isinstance(op, Return) for op in fn.ops))

    def test_fetch_function_int32_declares_value_type(self):
        """async_lower, not the fetch, wraps a non-pointer result."""
        fn = lt.make_fetch_function(t.Int(32))
        self.assertEqual(fn.name, "lazy_fetch$i32")
        self.assertEqual(fn.result, t.Int(32))

    def test_fetch_is_ssa(self):
        """Every variable is written once, so inlining keeps a caller SSA."""
        fn = lt.make_fetch_function(t.Int(32))
        writes = [v.name for op in fn.ops for v in op.get_live_vars()[1]]
        self.assertEqual(len(writes), len(set(writes)))

    def test_gate_functions_are_foreign(self):
        """lazy_acquire may suspend; lazy_release never does."""
        acquire = lt.make_gate_function(lt.ACQUIRE, False)
        release = lt.make_gate_function(lt.RELEASE, True)
        self.assertEqual(acquire.foreign_symbol, "lazy_acquire")
        self.assertEqual(release.foreign_symbol, "lazy_release")
        self.assertFalse(acquire.sync)
        self.assertTrue(release.sync)

    def test_ensure_is_idempotent(self):
        app = Application()
        cls1 = lt.ensure_lazy_machinery(app, t.DataPointer())
        cls2 = lt.ensure_lazy_machinery(app, t.DataPointer())
        self.assertEqual(cls1, cls2)
        self.assertEqual(cls1, "Lazy$ptr")
        # One object (the stub), four functions (fetch, the [future] worker
        # runner, and the runtime's two gate functions).
        self.assertIn("Lazy$ptr",       app.objects)
        self.assertIn("lazy_fetch$ptr", app.functions)
        self.assertIn("future_run$ptr", app.functions)
        self.assertIn("lazy_acquire",   app.functions)
        self.assertIn("lazy_release",   app.functions)
        self.assertEqual(len(app.objects),   1)
        self.assertEqual(len(app.functions), 4)

    def test_unsupported_value_type_raises(self):
        # An Int of non-standard precision has no lazy mangle (FuncPointer is
        # now supported — a callable value memoises like any other).
        with self.assertRaises(NotImplementedError):
            lt.make_stub_object(t.Int(24))
        with self.assertRaises(NotImplementedError):
            lt.make_fetch_function(t.Int(24))

    def test_ir_mangle_roundtrip(self):
        for ty in (t.DataPointer(), t.FuncPointer(),
                   t.Int(8), t.Int(16), t.Int(32), t.Int(64),
                   t.Float(32), t.Float(64)):
            self.assertEqual(lt.ir_mangle_to_type(lt._ir_mangle(ty)), ty)

    def test_object_pointer_mask_includes_pointer_fields(self):
        """The stub's GC pointer mask must mark flag, closure.o, and value
        (when value is a pointer type) so the GC keeps the waiter chain, the
        captured init env, and the cached value alive."""
        obj = lt.make_stub_object(t.DataPointer())
        # get_pointer_paths returns the GC-traversal paths within the
        # struct (excluding the leading vtable `type` field).
        paths = []
        for name, ft in obj.fields.fields[1:]:
            paths.extend(ft.get_pointer_paths(name))
        self.assertIn("flag",      paths)   # the waiter chain's root
        self.assertIn("closure.o", paths)   # captured env in init closure
        self.assertIn("value",     paths)   # for DataPointer value type
