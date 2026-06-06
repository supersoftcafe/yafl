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
class CallExpression(Expression):
    function: Expression
    parameter: Expression

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver, Any],Any]) -> Expression:
        return cast(Expression, replace(resolver, dataclasses.replace(self,
            function=self.function.search_and_replace(resolver, replace),
            parameter=self.parameter.search_and_replace(resolver, replace))))

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        func_type = self.function.get_type(resolver)
        return func_type.result if isinstance(func_type, t.CallableSpec) else None

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) ->  tuple[Expression, list[s.Statement]]:
        func_type = self.function.get_type(resolver)
        prtr_type = self.parameter.get_type(resolver)

        if not isinstance(prtr_type, t.TupleSpec):
            return self, []

        function , fglb = self.function.compile(resolver, t.CallableSpec(self.line_ref, prtr_type, expected_type))
        parameter, pglb = self.parameter.compile(resolver, func_type.parameters if isinstance(func_type, t.CallableSpec) else None)

        expr = dataclasses.replace(self, function=function, parameter=parameter)
        return expr, fglb+pglb

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        # TODO: Figure out what expected type to pass in
        err = self.function.check(resolver, None) + self.parameter.check(resolver, None)
        if err:
            return err

        ptype = self.parameter.get_type(resolver)
        if not isinstance(ptype, t.TupleSpec):
            return [Error(self.line_ref, "parameter expression must be of TupleType")]

        ftype = self.function.get_type(resolver)
        if not isinstance(ftype, t.CallableSpec):
            return [Error(self.line_ref, "Callable must be of type CallableSpec")]

        if ftype.parameters.trivially_assignable_from(resolver, ptype) is False:
            return [Error(self.line_ref, "Parameters are not assignment compatible")]

        return []

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        ftype = self.function.get_type(resolver)
        xtype = cast(t.CallableSpec, ftype)

        fun_op_bundle = self.function.generate(resolver).with_prefix("fn")
        # Coerce each argument to its declared parameter type — a narrow argument
        # flowing into a union-typed parameter is boxed here. `self.parameter` is
        # a tuple, so generate_to widens the matching fields (see coerce._coerce_tuple).
        prm_op_bundle = self.parameter.generate_to(resolver, xtype.parameters).with_prefix("args")

        fun_ref = fun_op_bundle.result_var
        impure = isinstance(fun_ref, cg_p.GlobalFunction) and fun_ref.impure

        result_var = cg_p.StackVar(xtype.result.generate(resolver), "result")
        call_bundle = g.OperationBundle(
            (result_var,),
            (cg_o.Call(fun_ref, prm_op_bundle.result_var, result_var, impure=impure),),
            result_var
        )

        return fun_op_bundle + prm_op_bundle + call_bundle



