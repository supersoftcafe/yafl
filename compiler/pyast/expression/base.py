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


@dataclass
class Expression:
    line_ref: LineRef

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        raise NotImplementedError()

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement]]:
        raise NotImplementedError()

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        return []

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        raise NotImplementedError()

    def generate_to(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> g.OperationBundle:
        """Generate this expression, then coerce its result to `expected_type`
        (union boxing/widening). The generation *sinks* — return, let, call
        argument, `[tail]` recur, and the per-branch merge of ternary/match —
        call this instead of `generate`, so a narrow value is widened at the
        point it flows into a wider-typed slot. Replaces the old AST-level
        boxing pass.

        The base implementation generates then coerces by the expression's own
        `get_type`. Nodes whose result *slot* cannot be sized without the
        expected type (ternary/match pick an arbitrary branch type; block defers
        to its value) override this to thread the type down instead."""
        import pyast.coerce as cc
        bundle = self.generate(resolver)
        return bundle + cc.coerce(bundle.result_var, self.get_type(resolver), expected_type, resolver)

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,Any],Any]) -> Expression:
        return cast(Expression, replace(resolver, self))



