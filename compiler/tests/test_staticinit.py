"""Static initialisation — `inline_single_use_globals` folds a static object
into the lazy global that copies it, only when that copy is its one reference.

Built by hand like tests/test_cleanup.py.
"""
from __future__ import annotations

import unittest

import codegen.typedecl as t
from codegen.gen import Application
from codegen.ir import Function, Global
from codegen.ops import Jump, JumpIf, Label, Move, Op, Phi, Return
from codegen.param import GlobalVar, NewStruct, StackVar
from lowering.staticinit import inline_single_use_globals

PTR = t.DataPointer()
THIS = t.Struct((("this", PTR),))
X = StackVar(PTR, "x")
STATIC = GlobalVar(PTR, "$si$0")


def fn(name: str, *ops: Op) -> Function:
    return Function(name=name, params=THIS, result=PTR,
                    stack_vars=t.Struct((("x", PTR),)), ops=tuple(ops))


def app_reading_the_static_from(reader: Function) -> Application:
    """`$si$0` copied by the lazy init of `target`, and read by `reader`."""
    copy = fn("init_target", Move(GlobalVar(PTR, "target"), STATIC), Return(GlobalVar(PTR, "target")))
    return Application(
        functions={copy.name: copy, reader.name: reader},
        globals={
            "$si$0": Global("$si$0", PTR, init=NewStruct(()), object_name="obj_Foo"),
            "target": Global("target", PTR, lazy_init_function="init_target",
                             lazy_init_flag="target$flag"),
        })


class TestInlineSingleUseGlobals(unittest.TestCase):

    def test_a_static_read_by_a_phi_is_not_single_use(self):
        reader = fn("reader",
                    JumpIf("b", X),
                    Label("a"), Jump("j"),
                    Label("b"), Jump("j"),
                    Label("j"), Phi(X, (("a", STATIC), ("b", X))), Return(X))
        folded = inline_single_use_globals(app_reading_the_static_from(reader))
        self.assertIn("$si$0", folded.globals)

    def test_a_static_read_only_by_its_copy_is_folded(self):
        folded = inline_single_use_globals(app_reading_the_static_from(fn("reader", Return(X))))
        self.assertNotIn("$si$0", folded.globals)
        self.assertEqual(folded.globals["target"].object_name, "obj_Foo")


if __name__ == "__main__":
    unittest.main()
