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
        """Generate this expression for a sink expecting `expected_type`.

        NO conversion happens here — generate never converts: the converged AST
        is the absolute source of truth for program correctness, so every
        required representation change was inserted during compile as a
        ConvertExpression (see expression.converted). This wrapper only (a)
        lets slot-sized nodes thread the expected type down (ternary/match size
        their merge slot, block defers to its value — they override this), and
        (b) asserts the invariant: a conversion still needed here is an
        upstream bug, reported loudly rather than silently emitted."""
        from pyast.expression.conversion import needs_conversion
        bundle = self.generate(resolver)
        own = self.get_type(resolver)
        if needs_conversion(own, expected_type, resolver):
            raise RuntimeError(
                f"conversion required at generate — compile failed to insert a "
                f"ConvertExpression ({type(self).__name__} at {self.line_ref}: "
                f"{own.as_unique_id_str()} -> {expected_type.as_unique_id_str()})")
        return bundle

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,Any],Any]) -> Expression:
        return replace(resolver, self)



