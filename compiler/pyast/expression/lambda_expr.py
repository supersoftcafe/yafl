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
import pyast.hints as h
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
        return rw.rewrite(self, replace, resolver,
            parameters=self.parameters.search_and_replace(resolver, replace),
            expression=self.expression.search_and_replace(nested_resolver, replace),
            return_type=rw.opt(self.return_type, resolver, replace))

    def get_type(self, resolver: g.Resolver) -> t.CallableSpec | None:
        return self.return_type

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement], h.Hints]:
        # Include parameters in data resolution hierarchy
        resolver = g.ResolverData(resolver, self._find_locals)

        # Compile the parameter types
        new_prm, new_prm_glb, _ = self.parameters.compile(resolver, None)

        # Compile the expression
        sub_expected_type = expected_type.result if isinstance(expected_type, t.CallableSpec) else None
        new_xpr, new_xpr_glb, body_hints = self.expression.compile(resolver, sub_expected_type)

        # An un-annotated parameter must fit its body's uses and accept what the
        # expected signature passes it.
        from pyast.statement.function import inferred_params
        new_prm = inferred_params(new_prm, h.merge(body_hints, self.__passed(expected_type)), resolver)

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
        # Report the parameter types the body was actually compiled against. When
        # the expected signature filled an undeclared `(x) =>` parameter, the
        # lambda's own type must reflect it so a sibling-dependent call site sees
        # the matching signature (e.g. `mapBox(b, (x) => x + 1)` once `T` is known
        # from `b`). Use the compiled `new_prm` ONLY when it is fully ground —
        # `as_unique_id_str()` is None exactly while a placeholder/unresolved name
        # remains — otherwise keep the original, which avoids reporting an
        # unresolved generic mid-resolution (the `?>`-chain `TOut` regression).
        threaded_params = new_prm.get_type()
        params_type = (threaded_params
                       if threaded_params is not None and threaded_params.as_unique_id_str() is not None
                       else self.parameters.get_type())
        new_ret = t.CallableSpec(self.line_ref, params_type, new_ret_result)

        own = {let.name for let in self.parameters.flatten()}
        return dataclasses.replace(
            self, parameters=new_prm, expression=new_xpr,
            return_type=new_ret), (new_prm_glb + new_xpr_glb), h.without(body_hints, own)

    def __passed(self, expected_type: t.TypeSpec | None) -> h.Hints:
        """What the expected signature passes each parameter: a LOWER hint."""
        if not (isinstance(expected_type, t.CallableSpec)
                and isinstance(expected_type.parameters, t.TupleSpec)
                and len(expected_type.parameters.entries) == len(self.parameters.targets)):
            return {}
        return h.merge(*(h.of(tgt.name, en.type, lower=True)
                         for tgt, en in zip(self.parameters.targets, expected_type.parameters.entries)
                         if en.type is not None))

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



