from __future__ import annotations

from typing import Callable, Any
import dataclasses
import random
from dataclasses import dataclass, field
from functools import reduce

from langtools import cast
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
        return cast(Expression, replace(resolver, dataclasses.replace(self,
            type=self.type.search_and_replace(resolver, replace),
            params=self.params.search_and_replace(resolver, replace))))

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        return self.type

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) ->  tuple[Expression, list[s.Statement]]:
        new_params, new_statements = self.params.compile(resolver, None)
        expr = dataclasses.replace(self, params=new_params)
        return expr._fold_const_compare() or expr, list(new_statements)

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

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        params_bundle = self.params.generate(resolver)
        if params_bundle.result_var is None:
            raise ValueError("BuiltinOpExpression has no parameters")
        ptype = params_bundle.result_var.get_type()
        if not isinstance(ptype, cg_t.Struct):
            raise ValueError("BuiltinOpExpression parameters must be tuple")

        xtype = self.type.generate(resolver)
        xexpr = cg_p.Invoke(self.op.value, params_bundle.result_var, xtype)
        final_bundle = g.OperationBundle( (), (), xexpr )

        return params_bundle + final_bundle



