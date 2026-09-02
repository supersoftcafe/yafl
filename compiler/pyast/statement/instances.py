"""TraitInstanceStatement — the `instance` statement as a first-class AST
node (user mandate: the parse-time desugar was an interim shape, not the
design).

    instance [ambient]<T> Interface<Pattern> where Constraint<T>
      fun member(...): ...

The node survives the whole front half of the pipeline — convergence,
checking, drops, linearity — carrying its identity: the interface PATTERN it
implements, its own type params, its `where` clause, the ambient flag, and
the member functions. Resolution reads ambient availability and constraint
discharge directly from these nodes. Only after checking does
lowering/instances.py lower each one to the witness class + `[trait]` record
let that monomorphisation and codegen already understand.

Anonymous at the surface (a synthesized `instance$<tag>` name exists only
for statement indexing/namespacing and never appears in diagnostics — errors
speak of the pattern). Members are vtable slots: they declare neither type
params nor `where` clauses (parse-rejected); their bodies compile and check
under a transient copy carrying THIS statement's `where` clause, exactly as
class members do.
"""
from __future__ import annotations

from typing import Callable, ClassVar, Any
from dataclasses import dataclass
import dataclasses

import pyast.rewrite as rw
import pyast.resolver as g
import pyast.typespec as t
import pyast.utils as u

from parsing.parselib import Error
from pyast.statement.base import NamedStatement, Statement
from pyast.statement.function import FunctionStatement


@dataclass
class TraitInstanceStatement(NamedStatement):
    _KNOWN_ATTRIBUTES: ClassVar[frozenset[str]] = frozenset({"ambient", "trait"})

    pattern: t.TypeSpec                      # the implemented interface, as written
    ambient: bool                            # [ambient] — availability opt-in
    statements: list[Statement]              # the member functions

    def __member_with_wheres(self, x: Statement) -> Statement:
        if isinstance(x, FunctionStatement) and self.trait_params:
            return dataclasses.replace(x, trait_params=self.trait_params)
        return x

    def __member_stripped(self, original: Statement, new_x: Statement) -> Statement:
        if isinstance(original, FunctionStatement) and self.trait_params \
                and isinstance(new_x, FunctionStatement):
            return dataclasses.replace(new_x, trait_params=())
        return new_x

    def __scope(self, resolver: g.Resolver) -> g.Resolver:
        return g.ResolverType(resolver, self._find_generic_types)

    def compile(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> tuple[Statement | None, list[Statement]]:
        scoped = self.__scope(resolver)
        new_pattern, pat_stmts = self.pattern.compile(scoped)
        trts, trt_stmts = u.flatten_lists(x.compile(scoped) for x in self.trait_params)
        members, mem_stmts = self.__compile_members(scoped)
        new_self = dataclasses.replace(
            self, pattern=new_pattern, trait_params=tuple(trts), statements=members)
        return new_self, pat_stmts + trt_stmts + mem_stmts

    def __compile_members(self, scoped: g.Resolver):
        out: list[Statement] = []
        extra: list[Statement] = []
        for m in self.statements:
            new_m, m_stmts = self.__member_with_wheres(m).compile(scoped, None)
            out.append(self.__member_stripped(m, new_m))
            extra.extend(m_stmts)
        return out, extra

    def check(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> list[Error]:
        scoped = self.__scope(resolver)
        errs = self.pattern.check(scoped)
        errs += [e for tp in self.trait_params for e in tp.check(scoped)]
        # The pattern must be an interface once resolved.
        if isinstance(self.pattern, t.ClassSpec):
            found = resolver.find_type(self.pattern.name)
            if len(found) == 1 and getattr(found[0].statement, 'is_interface', None) is False:
                errs.append(Error(self.line_ref,
                                  "an instance implements an interface, not a class"))
        for m in self.statements:
            errs += self.__member_with_wheres(m).check(scoped, None)
        # NO unknown-attribute check here, deliberately: the port's
        # PsTraitInstance keeps only `tiAmbient: Bool` (its parser discards the
        # attribute list), so it cannot see an unknown attribute on an instance
        # at all. Checking it here alone would have this compiler reject a
        # program the port accepts. Closing the gap needs a `tiAttrs` field on
        # the port node — a positional AST-node change wanting a tree-wide
        # enumeration of construction sites first.
        return errs

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver, Any], Any]) -> Statement:
        scoped = self.__scope(resolver)
        return rw.rewrite(self, replace, resolver,
            pattern=self.pattern.search_and_replace(scoped, replace),
            trait_params=rw.seq(self.trait_params, scoped, replace),
            statements=rw.seq(self.statements, scoped, replace))
