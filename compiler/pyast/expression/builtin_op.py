from __future__ import annotations

from typing import Callable, Any
import dataclasses
import pyast.rewrite as rw
from dataclasses import dataclass, field
from functools import reduce

from langtools import checked_cast
from parsing.tokenizer import LineRef
from parsing.parselib import Error

import codegen.ops as cg_o
import codegen.param as cg_p
import codegen.typedecl as cg_t

import pyast.resolver as g
import pyast.statement as s
import pyast.typespec as t
import pyast.utils as u
from pyast.expression.base import Expression
from pyast.expression.literal import BoolExpression, IntegerExpression
from pyast.expression.tuple_expr import TupleExpression


@dataclass
class BuiltinOpExpression(Expression):
    type: t.BuiltinSpec
    op: StringExpression
    params: Expression

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,Any],Any]) -> Expression:
        return rw.rewrite(self, replace, resolver,
            type=self.type.search_and_replace(resolver, replace),
            params=self.params.search_and_replace(resolver, replace))

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        return self.type

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) ->  tuple[Expression, list[s.Statement]]:
        new_params, new_statements = self.params.compile(resolver, None)
        expr = dataclasses.replace(self, params=new_params)
        # A primitive op owns its conversion to the receiver — its result
        # boxing into a union slot (`string_parse_int`'s bigint into `Int|None`).
        from pyast.expression.conversion import converted
        folded = expr._fold_const_compare()
        return (folded if folded is not None else converted(expr, expected_type, resolver)), list(new_statements)

    # An integer comparison of two bigint literals (the body of Int's `==`/`<`/
    # `>`) folds to a Bool literal. The language has no true/false token, so
    # this fold is what makes a constant Bool fold to a literal and inline.
    _INT_COMPARE = {
        "integer_test_eq": lambda a, b: a == b,
        "integer_test_lt": lambda a, b: a < b,
        "integer_test_gt": lambda a, b: a > b,
    }

    def _fold_const_compare(self) -> "BoolExpression | None":
        if self.type.type_name != "bool":
            return None
        predicate = BuiltinOpExpression._INT_COMPARE.get(self.op.value)
        if predicate is None or not isinstance(self.params, TupleExpression):
            return None
        operands = [entry.value for entry in self.params.expressions]
        if len(operands) != 2 or not all(
                isinstance(o, IntegerExpression) and o.precision == 0 for o in operands):
            return None
        return BoolExpression(self.line_ref, predicate(operands[0].value, operands[1].value))

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        return self.params.check(resolver, None)

    # The hash/identity internals are REPRESENTATION-AWARE: on a boxed enum
    # they are the real runtime calls; on a value representation there is no
    # object, so peek is the constant 0 (never cached), ref_eq is the constant
    # false (no identity to compare), and store just normalises the computed
    # hash (the 0-is-reserved contract holds either way). This is what lets
    # derived/wrapped code contain the shortcut UNCONDITIONALLY while the
    # boxing decision stays the compiler's.
    _REPR_AWARE = frozenset({"yafl_hash_peek", "yafl_hash_store", "yafl_ref_eq"})

    def __repr_aware(self, resolver: g.Resolver) -> "g.OperationBundle | None":
        if self.op.value not in BuiltinOpExpression._REPR_AWARE:
            return None
        if not isinstance(self.params, TupleExpression) or not self.params.expressions:
            return None
        subject_type = self.params.expressions[0].value.get_type(resolver)
        if (isinstance(subject_type, t.EnumSpec)
                and resolver.is_complex_root(subject_type.root_name)):
            return None    # boxed: the generic path emits the runtime call
        if self.op.value == "yafl_hash_peek":
            return g.OperationBundle((), (), cg_p.Integer(0, 32))
        if self.op.value == "yafl_ref_eq":
            return g.OperationBundle((), (), cg_p.Integer(0, 8))
        # store: the subject has no slot — evaluate ONLY the hash operand and
        # normalise it. The subject is a plain reference in all emitted code,
        # so skipping it drops no effects.
        h = self.params.expressions[1].value.generate(resolver)
        inv = cg_p.RuntimeInvoke("yafl_hash_norm",
                                 cg_p.NewStruct((("h", h.result_var),)),
                                 cg_t.Int(32))
        return h + g.OperationBundle((), (), inv)

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        special = self.__repr_aware(resolver)
        if special is not None:
            return special
        params_bundle = self.params.generate(resolver)
        if params_bundle.result_var is None:
            raise ValueError("BuiltinOpExpression has no parameters")
        ptype = params_bundle.result_var.get_type()
        if not isinstance(ptype, cg_t.Struct):
            raise ValueError("BuiltinOpExpression parameters must be tuple")

        xtype = self.type.generate(resolver)
        xexpr = cg_p.RuntimeInvoke(self.op.value, params_bundle.result_var, xtype)
        final_bundle = g.OperationBundle( (), (), xexpr )

        return params_bundle + final_bundle



