from unittest import TestCase

import codegen.typedecl as cg_t

import pyast.resolver as g
import pyast.statement as s
import pyast.typespec as t
import pyast.utils as u
from pyast.typespec import TupleEntrySpec

from tokenizer import LineRef


class Test(TestCase):
    def test_create_constructor(self):
        lr = LineRef("file", 1, 1)
        itype = t.BuiltinSpec(lr, "int32")
        params = s.DestructureStatement(lr, "_@9338i", None, {}, None, t.TupleSpec(lr, [
            TupleEntrySpec("first@123", itype),
            t.TupleSpec(lr, [
                TupleEntrySpec("second@123", itype),
                TupleEntrySpec("third@123", itype)
            ])
        ]), [
            s.LetStatement(lr, "first@123", None, {}, None, itype),
            s.DestructureStatement(lr, "_@84892", None, {}, None, t.TupleSpec(lr, [
                TupleEntrySpec("second@123", itype),
                TupleEntrySpec("third@123", itype)
            ]), [
                s.LetStatement(lr, "second@123", None, {}, None, itype),
                s.LetStatement(lr, "third@123", None, {}, None, itype)
            ])
        ])
        cls = s.ClassStatement(lr, "String@123", None, {}, params, [], [])
        func = u.create_constructor(cls)

        self.assertEqual("String@123", func.name)
        self.assertEqual(2, len(func.parameters.targets))
        self.assertEqual(3, len(func.parameters.flatten()))

        rawfunc = func.global_codegen(g.ResolverRoot([func, cls]))
        c = rawfunc.to_c_implement({})

        self.assertIsInstance(rawfunc.result, cg_t.DataPointer)
