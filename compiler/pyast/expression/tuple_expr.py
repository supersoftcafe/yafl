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


def _unwrap_one_tuple(expr: "Expression") -> "Expression":
    """A bracketed expression `(x)` parses to a 1-element TupleExpression.
    YAFL treats a 1-tuple as equivalent to its sole value, so in value
    positions we collapse the wrap. Only unnamed entries are unwrapped —
    `(name = value)` is a named 1-tuple and may be load-bearing for
    destructuring/type checks elsewhere.
    """
    while (isinstance(expr, TupleExpression)
            and len(expr.expressions) == 1
            and expr.expressions[0].name is None):
        expr = expr.expressions[0].value
    return expr



@dataclass
class TupleEntryExpression:
    name: str|None
    value: Expression

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,Any],Any]) -> TupleEntryExpression:
        return dataclasses.replace(self,
            value=self.value.search_and_replace(resolver, replace))

    def get_type(self, resolver: g.Resolver) -> t.TupleSpec | None:
        return self.value.get_type(resolver)

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[TupleEntryExpression, list[s.Statement]]:
        new_value, new_statements = self.value.compile(resolver, expected_type)
        new_value = _unwrap_one_tuple(new_value)
        return dataclasses.replace(self, value=new_value), new_statements

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        return self.value.check(resolver, expected_type)

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        return self.value.generate(resolver)



@dataclass
class TupleExpression(Expression):
    expressions: list[TupleEntryExpression]

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,Any],Any]) -> Expression:
        return cast(Expression, replace(resolver, dataclasses.replace(self,
            expressions=[x.search_and_replace(resolver, replace) for x in self.expressions])))

    def get_type(self, resolver: g.Resolver) -> t.TupleSpec | None:
        entries = [t.TupleEntrySpec(x.name, x.get_type(resolver)) for x in self.expressions]
        return t.TupleSpec(self.line_ref, entries = entries)

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement]]:
        expected_entries = expected_type.entries if isinstance(expected_type, t.TupleSpec) else []
        def entry_expected(i: int) -> t.TypeSpec | None:
            return expected_entries[i].type if i < len(expected_entries) else None
        p = [x.compile(resolver, entry_expected(i)) for i, x in enumerate(self.expressions)]
        new_expressions, new_statements_lists = zip(*p) if p else ([], [])
        expr = dataclasses.replace(self, expressions=list(new_expressions))
        return expr, list(x for l in new_statements_lists for x in l)

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        # TODO: Breakdown expected_type and pass it into the check function
        errors = [e for x in self.expressions for e in x.check(resolver, None)]
        return errors or []

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        param_bundles = [expr.generate(resolver).with_prefix(f"e{index}") for index, expr in enumerate(self.expressions)]
        # NewStruct field-name → result_var mapping is pinned to declared positions,
        # so the resulting tuple value is unaffected by any reordering of evaluation below.
        value = cg_p.NewStruct(tuple(((f"_{idx}", x.result_var) for idx, x in enumerate(param_bundles))))
        final_bundle = g.OperationBundle((), (), value)
        # At -O0, randomise the order in which children's side-effects fire so that
        # any code accidentally relying on left-to-right tuple evaluation surfaces.
        # Seed deterministically from the source location: same .yafl in → same .c out,
        # but order varies across tuple sites within a program.
        eval_bundles = param_bundles
        if resolver.get_optimization_level() == 0 and len(eval_bundles) > 1:
            rng = random.Random(f"{self.line_ref.filename}:{self.line_ref.line}:{self.line_ref.offset}")
            eval_bundles = list(param_bundles)
            rng.shuffle(eval_bundles)
        total_bundle = reduce(lambda x, y: y + x, reversed(eval_bundles), final_bundle)
        return total_bundle

    def trim_left(self, amount: int) -> TupleExpression:
        return dataclasses.replace(self, expressions=self.expressions[amount:])



