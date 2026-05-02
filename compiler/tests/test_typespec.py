from tests.testutil import TimedTestCase as TestCase

import pyast.typespec as t
import pyast.resolver as g
import pyast.statement as s
from parsing.tokenizer import LineRef

glb = g.ResolverRoot([])
lr = LineRef("f", 0, 0)
int32 = t.BuiltinSpec(lr, "int32")

class TestTupleSpec(TestCase):
    def test_trivially_assignable_from(self):
        l = t.TupleSpec(lr, [t.TupleEntrySpec(None, int32), t.TupleEntrySpec(None, int32)])
        r = t.TupleSpec(lr, [t.TupleEntrySpec(None, int32), t.TupleEntrySpec(None, int32)])
        self.assertTrue(t.trivially_assignable_equals(glb, l, r))

    def test_fuzzy_assignable_from2(self):
        # This is the template from the call site.
        # Equivalent to having a let x:<left callable type> = <thing of right callable type>.
        l = t.CallableSpec(lr, t.TupleSpec(lr, [t.TupleEntrySpec(None, int32), t.TupleEntrySpec(None, int32)]), None)

        # Callable that I am loading. It represents a real function being loaded.
        r = t.CallableSpec(lr, t.TupleSpec(lr, [t.TupleEntrySpec("left", int32), t.TupleEntrySpec("right", int32)]), None)

        # Must be assignment compatible.
        result = t.trivially_assignable_equals(glb, l, r)
        self.assertIsNone(result)


class TestNamedSpec(TestCase):
    def test_check_resolved_returns_no_errors(self):
        # A NamedSpec whose name is present in the resolver should pass check() with no errors.
        alias = s.TypeAliasStatement(lr, "MyInt", None, {}, (), type=int32)
        resolver = g.ResolverRoot([alias])
        spec = t.NamedSpec(lr, "MyInt", ())
        errors = spec.check(resolver)
        self.assertEqual([], errors, "check() must return [] for a successfully resolved type")

    def test_check_unresolved_returns_error(self):
        # A NamedSpec whose name is absent from the resolver should still report an error.
        resolver = g.ResolverRoot([])
        spec = t.NamedSpec(lr, "Unknown", ())
        errors = spec.check(resolver)
        self.assertEqual(1, len(errors))
        self.assertIn("Unresolved", errors[0].message)


class TestCallableSpec(TestCase):
    def test_compile_with_none_result(self):
        # CallableSpec with result=None must not crash when compiled.
        params = t.TupleSpec(lr, [t.TupleEntrySpec(None, int32)])
        spec = t.CallableSpec(lr, params, None)
        compiled, stmts = spec.compile(glb)
        self.assertIsNone(compiled.result)
        self.assertEqual([], stmts)


class TestGenericPlaceholderSpec(TestCase):
    def test_same_name_assigns(self):
        # Two placeholders with the same name represent the same type variable.
        a = t.GenericPlaceholderSpec(lr, "T@h1")
        b = t.GenericPlaceholderSpec(lr, "T@h1")
        self.assertTrue(a.trivially_assignable_from(glb, b))

    def test_different_names_undecided(self):
        # Different placeholders may match after instantiation, so the answer
        # is "undecided" (None), not False — concrete safety is enforced when
        # the generic is monomorphised.
        a = t.GenericPlaceholderSpec(lr, "T@h1")
        b = t.GenericPlaceholderSpec(lr, "U@h2")
        self.assertIsNone(a.trivially_assignable_from(glb, b))

    def test_concrete_is_false(self):
        # A placeholder vs a concrete type is structurally False at this layer
        # (substitution happens in the generics pass, not here).
        a = t.GenericPlaceholderSpec(lr, "T@h1")
        self.assertFalse(a.trivially_assignable_from(glb, int32))
