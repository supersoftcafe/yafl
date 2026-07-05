"""FunctionStatement: signature resolution, call-site suggestion filling
(path 3), return-type refinement, and function codegen.
"""
from __future__ import annotations

from functools import reduce
from collections.abc import Sequence
from typing import Callable, Iterable, Any
from dataclasses import dataclass, field
import dataclasses
import pyast.rewrite as rw

from langtools import checked_cast
from parsing.tokenizer import LineRef
from parsing.parselib import Error

import codegen.ops as cg_o
import codegen.typedecl as cg_t
import codegen.ir as cg_ir

import pyast.resolver as g
import pyast.expression as e
import pyast.typespec as t

import pyast.utils as u

from pyast.statement.base import Statement, NamedStatement, DataStatement, ImportGroup
from pyast.statement.lets import LetStatement, DestructureStatement


@dataclass
class FunctionStatement(DataStatement):
    parameters: DestructureStatement
    body: e.Expression | None
    return_type: t.TypeSpec|None = None

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,Any],Any]) -> Statement:
        nested_resolver = g.ResolverData(resolver, self.__find_locals(resolver))
        return rw.rewrite(self, replace, nested_resolver,
            parameters=self.parameters.search_and_replace(resolver, replace),
            body=rw.opt(self.body, nested_resolver, replace),
            return_type=rw.opt(self.return_type, resolver, replace),
            trait_params=rw.seq(self.trait_params, resolver, replace))

    def get_type(self) -> t.TypeSpec|None:
        return t.CallableSpec(self.line_ref, self.parameters.get_type(), self.return_type)

    def __find_locals(self, resolver: g.Resolver) -> Callable[[str],list[g.Resolved[DataStatement]]]:
        def finder(query: str) -> list[g.Resolved[DataStatement]]:
            p = [g.Resolved(let.name, let, g.ResolvedScope.LOCAL)
                 for let in self.parameters.flatten()
                 if g.name_matches(let.name, query)]
            td = self._find_trait_data(resolver, query)
            return p + td
        return finder

    def __with_param_suggestion(self, resolver: g.Resolver) -> DestructureStatement:
        """Fill any UN-annotated parameter from the call-site suggestion gathered
        for this function (path 3). The per-parameter type lives on the TARGET, so
        a target with no declared type adopts the suggested one; a target that
        declares its own type always wins. This is per-parameter and so applies to
        generic functions too: `a` in `fun foo<N>(a: N, b)` declares `N` and ignores
        suggestions, while the untyped `b` is a plain hole filled like any other."""
        suggestion = resolver.get_param_suggestion(self.name)
        targets = self.parameters.targets
        if not isinstance(suggestion, t.TupleSpec) or len(suggestion.entries) != len(targets):
            return self.parameters
        def usable(typ: t.TypeSpec | None) -> bool:
            # A suggested type is usable here only if it resolves IN THIS scope. A
            # generic placeholder is a real type inside the scope that binds it and
            # a hole outside it (a caller's `N` means nothing in a callee that does
            # not share it), so an entry carrying an out-of-scope placeholder is a
            # hole and fills nothing — its concrete sibling entries still do.
            return typ is not None and not t.has_free_placeholders(typ, resolver)
        new_targets = [tgt if tgt.declared_type is not None or not usable(su.type)
                       else dataclasses.replace(tgt, declared_type=su.type)
                       for tgt, su in zip(targets, suggestion.entries)]
        if new_targets == list(targets):
            return self.parameters
        return dataclasses.replace(self.parameters, targets=new_targets)

    def compile(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> tuple[FunctionStatement | None, list[Statement]]:
        resolver = g.ResolverType(resolver, self._find_generic_types)
        rettype, rettype_glb = self.return_type.compile(resolver) if self.return_type else (None, [])
        prms, prms_glb = self.__with_param_suggestion(resolver).compile(resolver, None)
        trts, trts_glb = u.flatten_lists(tp.compile(resolver) for tp in self.trait_params)

        body_resolver = g.ResolverData(resolver, self.__find_locals(resolver))
        if self.body is not None:
            new_body, body_glb = self.body.compile(body_resolver, self.return_type)
            # An undeclared return type refines from the body each pass — the
            # same t.refine rule as an untyped let.
            rettype = t.refine(rettype, resolver, lambda: new_body.get_type(body_resolver))
        else:
            new_body, body_glb = None, []

        globals = body_glb + rettype_glb + prms_glb + trts_glb
        new_self = dataclasses.replace(self, trait_params=tuple(trts), parameters=prms, body=new_body, return_type=rettype)
        return new_self, globals

    def check(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> list[Error]:
        resolver = g.ResolverType(resolver, self._find_generic_types)
        body_resolver = g.ResolverData(resolver, self.__find_locals(resolver))
        err1 = self.return_type.check(resolver) if self.return_type else []
        err2 = self.parameters.check(resolver, None)
        err3 = self.body.check(body_resolver, self.return_type) if self.body is not None else []
        err4 = [e for x in self.trait_params for e in x.check(resolver)]

        if "foreign" in self.attributes:
            foreign_attr = self.attributes.get("foreign")
            if (not isinstance(foreign_attr, e.TupleExpression)
                    or len(foreign_attr.expressions) != 1
                    or not isinstance(foreign_attr.expressions[0].value, e.StringExpression)):
                foreign_err = [Error(self.line_ref, '[foreign] requires exactly one string argument: [foreign("symbol")]')]
            elif self.body is not None:
                foreign_err = [Error(self.line_ref, "[foreign] functions must have no body")]
            else:
                foreign_err = []
        else:
            foreign_err = []

        if "impure" in self.attributes:
            impure_err = [] if self.attributes.get("impure") is None else [Error(self.line_ref, "[impure] takes no arguments")]
        else:
            impure_err = []

        if "sync" in self.attributes:
            sync_err = [] if self.attributes.get("sync") is None else [Error(self.line_ref, "[sync] takes no arguments")]
        else:
            sync_err = []

        tail_err: list[Error] = []
        if "tail" in self.attributes:
            if self.attributes.get("tail") is not None:
                tail_err.append(Error(self.line_ref, "[tail] takes no arguments"))
            if self.body is None:
                tail_err.append(Error(self.line_ref, "[tail] cannot be applied to a foreign function"))

        terminal_err: list[Error] = []
        if "terminal" in self.attributes and self.attributes.get("terminal") is not None:
            terminal_err.append(Error(self.line_ref, "[terminal] takes no arguments"))

        return (err1 + err2 + err3 + err4 + foreign_err + impure_err + sync_err
                + tail_err + terminal_err + self.__unused_param_warnings())

    def __unused_param_warnings(self) -> list[Error]:
        # No value vanishes silently: a parameter the body never reads receives
        # a value that disappears. `this` is implicit (a method need not use
        # it); a `_`-prefixed name is the explicit opt-out (e.g. a trait-impl
        # signature obliged to accept an argument it doesn't need).
        if self.body is None:
            return []
        # `[terminal]` params are declared consumed-on-arrival (a terminus like
        # toString/discard) — not vanishing values.
        declared = [(let.name, let.line_ref) for let in self.parameters.flatten()
                    if not g.bare_name(let.name).startswith("_") and g.bare_name(let.name) != "this"
                    and "terminal" not in let.attributes]
        if not declared:
            return []
        referenced = u.referenced_names(self.body)
        return [Error.warning(lr, f"parameter '{g.bare_name(name)}' is never used")
                for name, lr in declared if name not in referenced]

    def global_codegen(self, resolver: g.Resolver) -> cg_ir.Function:
        resolver = g.ResolverType(resolver, self._find_generic_types)
        resolver = g.ResolverData(resolver, self.__find_locals(resolver))

        bundle = g.OperationBundle()
        for index, parameter in enumerate(self.parameters.targets):
            bundle = bundle + parameter.to_c_destructure(None).with_prefix(f"p{index}")
        if self.body is not None:
            body_bundle = self.body.generate_to(resolver, self.return_type)
            ret_bundle = g.OperationBundle((), (cg_o.Return(body_bundle.result_var),))
            bundle = bundle + (body_bundle + ret_bundle).with_prefix("body")

        params: list[tuple[str, cg_t.Type]] = [("this", cg_t.DataPointer())]
        for prm in self.parameters.targets:
            xname = str(prm.name)
            xtype = prm.declared_type.generate(resolver)
            params.append( (xname, xtype) )

        vars = []
        for sv in bundle.stack_vars:
            vars.append( (sv.name, sv.type) )

        foreign_attr = self.attributes.get("foreign")
        foreign_symbol = (foreign_attr.expressions[0].value.value
                          if isinstance(foreign_attr, e.TupleExpression)
                          and len(foreign_attr.expressions) == 1
                          and isinstance(foreign_attr.expressions[0].value, e.StringExpression)
                          else None)

        return cg_ir.Function(
            name = self.name,
            params = cg_t.Struct(fields = tuple(params)),
            result = self.return_type.generate(resolver),
            stack_vars = cg_t.Struct(fields = tuple(vars)),
            ops = tuple(bundle.operations),
            comment = self.name,
            foreign_symbol = foreign_symbol,
            sync = "sync" in self.attributes,
            tail = "tail" in self.attributes,
            # `[inline(always)]` — the inline attribute carrying an argument (vs the
            # bare `[inline]` hint). Forces inlining regardless of size.
            always_inline = self.attributes.get("inline") is not None,
        )
