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
class LambdaExpression(Expression):
    parameters: s.DestructureStatement
    expression: Expression
    return_type: t.CallableSpec | None = None

    def _find_locals(self, query: str) -> list[g.Resolved[s.DataStatement]]:
        p = [g.Resolved(let.name, let, g.ResolvedScope.LOCAL)
             for let in self.parameters.flatten()
             if g.name_matches(let.name, query)]
        return p

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver, Any],Any]) -> Expression:
        nested_resolver = g.ResolverData(resolver, self._find_locals)
        return cast(Expression, replace(resolver, dataclasses.replace(
            self,
            parameters=cast(s.DestructureStatement, self.parameters.search_and_replace(resolver, replace)),
            expression=self.expression.search_and_replace(nested_resolver, replace),
            return_type=self.return_type.search_and_replace(resolver, replace) if self.return_type else None)))

    def get_type(self, resolver: g.Resolver) -> t.CallableSpec | None:
        return self.return_type

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement]]:
        # Include parameters in data resolution hierarchy
        resolver = g.ResolverData(resolver, self._find_locals)

        # Infer untyped parameters from the expected callable's parameter types:
        # a lambda flowing into a slot of known signature lets an undeclared
        # `(n) =>` adopt that parameter's type. Threading the expected parameter
        # tuple as the destructure's type reuses DestructureStatement's existing
        # propagation to fill each still-untyped target; explicitly-typed params
        # are left untouched. Re-thread on every pass (rather than only when no
        # type is present): across compile iterations the expected signature can
        # arrive empty before it arrives concrete, so a one-shot gate would lock
        # in the empty one. Two guards: matching arity (a mismatch is left for
        # the call's parameter check to report), and *concreteness* — the
        # expected types are re-compiled in this lambda's scope, so a callee
        # generic param (`T`) that has not yet been substituted would resolve to
        # an unresolved name here; wait for the concrete signature.
        params = self.parameters
        if (isinstance(expected_type, t.CallableSpec)
                and isinstance(expected_type.parameters, t.TupleSpec)
                and expected_type.parameters.is_concrete()
                and len(expected_type.parameters.entries) == len(params.targets)):
            params = dataclasses.replace(params, declared_type=expected_type.parameters)

        # Compile the parameter types
        new_prm, new_prm_glb = params.compile(resolver, None)

        # Compile the expression
        sub_expected_type = expected_type.result if isinstance(expected_type, t.CallableSpec) else None
        new_xpr, new_xpr_glb = self.expression.compile(resolver, sub_expected_type)

        # Calculate the return type. Prefer the expected result type from the
        # enclosing call site — that way a lambda whose body is narrower than
        # the declared parameter widens via boxing, and the call's parameter
        # check sees matching types.
        body_type = new_xpr.get_type(resolver)
        if (sub_expected_type is not None
                and body_type is not None
                and sub_expected_type.is_concrete()
                and sub_expected_type.trivially_assignable_from(resolver, body_type) is True):
            new_ret_result = sub_expected_type
        else:
            new_ret_result = body_type
        new_ret = t.CallableSpec(self.line_ref, self.parameters.get_type(), new_ret_result)

        return dataclasses.replace(
            self, parameters=new_prm, expression=new_xpr,
            return_type=new_ret), (new_prm_glb + new_xpr_glb)

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        # Include parameters in data resolution hierarchy
        resolver = g.ResolverData(resolver, self._find_locals)

        sub_expected_type = expected_type.result if isinstance(expected_type, t.CallableSpec) else None
        prm_err = self.parameters.check(resolver, None)
        xpr_err = self.expression.check(resolver, sub_expected_type)
        ret_err = self.return_type.check(resolver) if self.return_type else [Error(self.line_ref, "Lambda return type is unknown")]
        return prm_err + xpr_err + ret_err

    def generate(self, glb: g.Resolver) -> g.OperationBundle:
        raise ValueError("Lambda code generation is not directly supported. Code lowering should have got rid of this. Look there and keep this error.")



