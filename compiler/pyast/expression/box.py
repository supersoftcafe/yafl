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
class BoxExpression(Expression):
    """Widen a value of a variant type into its enclosing union type."""
    inner: Expression
    union_spec: t.CombinationSpec

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver, Any], Any]) -> Expression:
        return cast(Expression, replace(resolver, dataclasses.replace(self,
            inner=self.inner.search_and_replace(resolver, replace),
            union_spec=cast(t.CombinationSpec, self.union_spec.search_and_replace(resolver, replace)))))

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec:
        return self.union_spec

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement]]:
        inner, stmts = self.inner.compile(resolver, None)
        union_spec, spec_stmts = self.union_spec.compile(resolver)
        return dataclasses.replace(self, inner=inner, union_spec=cast(t.CombinationSpec, union_spec)), stmts + spec_stmts

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        return self.inner.check(resolver, None)

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        # Boxing is now a generation-sink concern: `generate_to` pushes the union
        # type into the inner expression (so a nested match/ternary sizes its
        # result slot to the union and coerces each arm) and then coerces the
        # result. This subsumes the recursion the old boxing pass performed
        # before `generate`. The node survives only as an inliner-inserted marker
        # that pins `get_type` to the callee's union return type.
        return self.inner.generate_to(resolver, self.union_spec)

