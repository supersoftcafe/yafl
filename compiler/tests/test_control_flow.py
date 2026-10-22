"""Control flow — what each op says about it (`Op.falls_through`,
`Op.branch_targets`), and the function-level CFG built from those answers.

Built by hand like tests/test_cleanup.py.
"""
from __future__ import annotations

import unittest

import codegen.typedecl as t
from codegen.ir import Function
from codegen.ops import (Abort, Call, Jump, JumpIf, Label, Move, Op, Return,
                         SwitchJump)
from codegen.param import GlobalFunction, Integer, NewStruct, StackVar

PTR = t.DataPointer()
INT = t.Int(32)
X = StackVar(INT, "x")


def fn(*ops: Op) -> Function:
    return Function(name="f", params=t.Struct((("this", PTR),)), result=INT,
                    stack_vars=t.Struct((("x", INT),)), ops=tuple(ops))


def musttail() -> Call:
    return Call(GlobalFunction("g"), NewStruct(()), musttail=True, result_type=INT)


class TestOpsAnswer(unittest.TestCase):

    def test_every_op_answers_both_questions_itself(self):
        """No op inherits an answer: a new variant must decide for itself."""
        def leaves(cls):
            subs = cls.__subclasses__()
            return [c for s in subs for c in leaves(s)] if subs else [cls]
        for cls in leaves(Op):
            for name in ("falls_through", "branch_targets"):
                self.assertIn(name, cls.__dict__, f"{cls.__name__}.{name}")

    def test_a_switch_never_falls_through(self):
        """Its C has `default: abort()`."""
        op = SwitchJump(X, ((1, "a"), (2, "b")))
        self.assertFalse(op.falls_through())
        self.assertEqual(op.branch_targets(), ("a", "b"))

    def test_a_musttail_call_never_falls_through(self):
        self.assertFalse(musttail().falls_through())
        self.assertTrue(Call(GlobalFunction("g"), NewStruct(()), register=X).falls_through())


class TestFunctionCfg(unittest.TestCase):

    def test_ops_after_an_abort_are_unreachable(self):
        f = fn(Abort("no"), Move(X, Integer(1, 32)), Return(X))
        self.assertEqual(f.strip_unused_operations().ops, (Abort("no"),))

    def test_a_switch_is_no_fall_through_predecessor(self):
        f = fn(Label("s"), SwitchJump(X, ((1, "b"),)), Label("a"), Return(X),
               Label("b"), Return(X))
        self.assertEqual(f.block_predecessors(), {"s": set(), "a": set(), "b": {"s"}})

    def test_a_musttail_call_is_no_fall_through_predecessor(self):
        f = fn(Label("s"), musttail(), Label("b"), Return(X))
        self.assertEqual(f.block_predecessors(), {"s": set(), "b": set()})

    def test_jumps_and_fall_through_are_predecessors(self):
        f = fn(JumpIf("b", X), Label("a"), Jump("b"), Label("b"), Return(X))
        self.assertEqual(f.block_predecessors(), {"a": {None}, "b": {None, "a"}})


if __name__ == "__main__":
    unittest.main()
