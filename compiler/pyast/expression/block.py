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
class BlockExpression(Expression):
    """A sequence of statements followed by a value expression.

    Used as the body of FunctionStatement and produced by the inliner
    when a call is substituted at expression position.
    """
    statements: list[s.Statement]
    value: Expression

    def _find_locals(self) -> Callable[[str], list[g.Resolved]]:
        def finder(query: str) -> list[g.Resolved]:
            lets = [g.Resolved(let.name, let, g.ResolvedScope.LOCAL)
                    for x in self.statements if isinstance(x, s.LetStatement)
                    for let in x.flatten() if g.name_matches(let.name, query)]
            funs = [g.Resolved(fun.name, fun, g.ResolvedScope.LOCAL)
                    for fun in self.statements if isinstance(fun, s.FunctionStatement) and g.name_matches(fun.name, query)]
            return lets + funs
        return finder

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver, Any], Any]) -> Expression:
        nested = g.ResolverData(resolver, self._find_locals())
        new_stmts = [x.search_and_replace(nested, replace) for x in self.statements]
        new_val = self.value.search_and_replace(nested, replace)
        return cast(Expression, replace(resolver, dataclasses.replace(self, statements=new_stmts, value=new_val)))

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        nested = g.ResolverData(resolver, self._find_locals())
        return self.value.get_type(nested)

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement]]:
        statements = s.collapse_else_if(self.statements)
        nested = g.ResolverData(resolver, self._find_locals())
        stmt_results = [x.compile(nested, expected_type) for x in statements]
        new_stmts = [r[0] for r in stmt_results if r[0]]
        glbs: list[s.Statement] = [glb for r in stmt_results for glb in r[1]]
        new_val, val_glbs = self.value.compile(nested, expected_type)
        return dataclasses.replace(self, statements=new_stmts, value=new_val), glbs + val_glbs

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        nested = g.ResolverData(resolver, self._find_locals())
        stmt_errs = [err for x in self.statements for err in x.check(nested, expected_type)]
        val_errs = self.value.check(nested, expected_type)
        if not val_errs and expected_type is not None:
            xtype = self.value.get_type(nested)
            if xtype is not None and t.trivially_assignable_equals(nested, expected_type, xtype) is False:
                val_errs = [Error(self.value.line_ref, "Incorrect type")]
        return stmt_errs + val_errs

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        nested = g.ResolverData(resolver, self._find_locals())
        bundle = g.OperationBundle()
        # Phase 1: hoist deferred-init stub allocations to block entry
        # so a forward reference inside one lazy body sees the
        # later-declared stub's slot already pointing at a real heap
        # object.  Block-local (not function-wide) — a deferred-init
        # let inside an if/match arm only allocates when that arm runs.
        for i, stmt in enumerate(self.statements):
            if (isinstance(stmt, s.LetStatement)
                    and stmt.is_deferred_init()
                    and stmt.declared_type is not None):
                bundle = bundle + stmt.generate_lazy_alloc(nested).with_prefix(f"alloc_s{i}")
        # Phase 2: walk statements in order.  Deferred-init lets emit
        # only the closure-population Move now — their stub allocation
        # was hoisted above.
        for i, stmt in enumerate(self.statements):
            if (isinstance(stmt, s.LetStatement)
                    and stmt.is_deferred_init()
                    and stmt.declared_type is not None):
                bundle = bundle + stmt.generate_lazy_populate(nested).with_prefix(f"s{i}")
            else:
                bundle = bundle + stmt.generate(nested, None).with_prefix(f"s{i}")
        return bundle + self.value.generate(nested)



