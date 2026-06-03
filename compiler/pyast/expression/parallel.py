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


@dataclass
class ParallelExpression(Expression):
    exprs: list[Expression]

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver, Any], Any]) -> Expression:
        return cast(Expression, replace(resolver, dataclasses.replace(
            self,
            exprs=[e.search_and_replace(resolver, replace) for e in self.exprs])))

    def get_type(self, resolver: g.Resolver) -> t.TupleSpec | None:
        entries = []
        for expr in self.exprs:
            fn_type = expr.get_type(resolver)
            if not isinstance(fn_type, t.CallableSpec) or fn_type.result is None:
                return None
            entries.append(t.TupleEntrySpec(None, fn_type.result))
        return t.TupleSpec(self.line_ref, entries)

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement]]:
        new_exprs, new_stmts = [], []
        for expr in self.exprs:
            new_e, stmts = expr.compile(resolver, None)
            new_exprs.append(new_e)
            new_stmts.extend(stmts)
        return dataclasses.replace(self, exprs=new_exprs), new_stmts

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        bad_arg = "__parallel__ argument must be a zero-parameter function"
        errors = []
        for expr in self.exprs:
            errors.extend(expr.check(resolver, None))
            fn_type = expr.get_type(resolver)
            if fn_type is None:
                errors.append(Error(expr.line_ref, "__parallel__ argument type is unknown"))
            elif not isinstance(fn_type, t.CallableSpec) or fn_type.parameters.entries:
                errors.append(Error(expr.line_ref, bad_arg))
        return errors

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        fn_bundles = [expr.generate(resolver).with_prefix(f"par{i}") for i, expr in enumerate(self.exprs)]
        result_types = [cast(t.CallableSpec, expr.get_type(resolver)).result for expr in self.exprs]
        result_vars = tuple(cg_p.StackVar(rt.generate(resolver), f"$par{i}") for i, rt in enumerate(result_types))
        register = cg_p.StackVar(self.get_type(resolver).generate(resolver), "$par_result")
        parallel_op = cg_o.ParallelCall(
            calls=tuple(b.result_var for b in fn_bundles),
            results=result_vars,
            register=register,
        )
        parallel_bundle = g.OperationBundle(
            (register,) + result_vars,
            (parallel_op,),
            register,
        )
        return reduce(lambda x, y: y + x, reversed(fn_bundles), parallel_bundle)



