from unittest import TestCase

import pyast.typespec as t
import pyast.resolver as g
from tokenizer import LineRef

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

