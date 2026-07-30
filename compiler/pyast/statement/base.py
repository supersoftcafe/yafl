"""The Statement protocol and shared bases (see docs/compiler-internals.md §1),
plus the structural statements (imports, namespace) that have no behaviour of
their own. Concrete statement kinds live in the sibling modules.
"""
from __future__ import annotations

from functools import reduce
from collections.abc import Sequence
from typing import Callable, Iterable, Any, TYPE_CHECKING
from dataclasses import dataclass, field
import dataclasses
import pyast.rewrite as rw

if TYPE_CHECKING:  # annotation-only; a real import would cycle (see __init__)
    from pyast.statement.types import TypeAliasStatement

from langtools import checked_cast
from parsing.tokenizer import LineRef
from parsing.parselib import Error


import pyast.classtools as c
import pyast.resolver as g
import pyast.expression as e
import pyast.typespec as t

import pyast.utils as u


@dataclass
class ImportGroup:
    imports: tuple[ImportStatement, ...]


@dataclass
class Statement:
    line_ref: LineRef

    def compile(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> tuple[Statement | None, list[Statement]]:
        raise NotImplementedError()

    def check(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> list[Error]:
        raise NotImplementedError()

    def generate(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> g.OperationBundle:
        return g.OperationBundle()

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,Any],Any]) -> Statement:
        return replace(resolver, self)


@dataclass
class NamedStatement(Statement):
    name: str
    imports: ImportGroup|None
    attributes: dict[str, e.Expression|None]
    type_params: tuple[TypeAliasStatement, ...]     # SomeClass<TValue1, TValue1>
    trait_params: tuple[t.TypeSpec, ...] = field(default=(), kw_only=True)   # SomeClass<TValue>() where Numeric<TValue>

    def _find_trait_data(self, resolver: g.Resolver, query: str) -> "g.Bag[g.Resolved[DataStatement]]":
        # Deferred: base ← classdef would be an import cycle (ClassStatement IS
        # a NamedStatement); this method only runs long after both initialise.
        from pyast.statement.classdef import ClassStatement

        def find_in_class(tp: t.ClassSpec | t.NamedSpec,
                          instance_params: tuple[str, ...] = ()) -> "g.Bag[g.Resolved[DataStatement]]":
            found = [rs.statement for rs in resolver.find_type(tp.name)]
            match found:
                case [ClassStatement() as cls]:
                    if len(tp.type_params) != len(cls.type_params):
                        return g.EMPTY
                    # Direct members first (the by-name index is a dict hit).
                    direct = cls.member_index()[query]
                    if direct:
                        return g.Bag(tuple(g.Resolved(x.name, x, g.ResolvedScope.TRAIT, tp, cls,
                                                      instance_params) for x in direct))
                    # Recurse into each parent interface with type params
                    # substituted (Math<TVal> : Plus<TVal>, tp Math<Int> ⇒
                    # Plus<Int>). `implements` is already a flat list of
                    # individual interfaces — the parser split any `A | B`
                    # inheritance spelling — so there is never a union here.
                    mapping = {p.name: c for p, c in zip(cls.type_params, tp.type_params)}
                    result = g.EMPTY
                    for parent_type in cls.implements:
                        parent = t.substitute_placeholders(parent_type, mapping, resolver)
                        # A parent whose name — or any type arg — is still a
                        # NamedSpec has not grounded: its operators aren't
                        # knowable yet, so this whole search is incomplete.
                        if isinstance(parent, t.NamedSpec) or any(isinstance(a, t.NamedSpec) for a in parent.type_params):
                            result = result + g.INCOMPLETE
                        else:
                            result = result + find_in_class(parent, instance_params)
                    return result
                case []:
                    return g.INCOMPLETE  # interface name not resolved yet — blocked, not absent
                case _:
                    raise LookupError(f"Failed to find class {tp.name!r}: got {[type(f).__name__ for f in found]}")
        specs: set[tuple[t.ClassSpec, tuple[str, ...]]] = set()
        ordered_specs: list[tuple[t.ClassSpec, tuple[str, ...]]] = []
        blocked = False
        def add(tp: t.ClassSpec, own: tuple[str, ...]) -> None:
            if (tp, own) not in specs:
                specs.add((tp, own))
                ordered_specs.append((tp, own))
        for tp in self.trait_params:
            if isinstance(tp, t.ClassSpec) and tp.is_concrete():
                add(tp, ())
            elif isinstance(tp, t.NamedSpec):
                # A where constraint whose type is still a NamedSpec:
                # unresolved, so the trait set is not yet complete.
                blocked = True
        # `instance [ambient]` records join the SAME search — availability,
        # not constraint. A concrete instance's interface spec enters exactly
        # like a where-clause spec; a GENERIC one enters as the interface
        # PATTERN whose own placeholders the use site may bind. The patterns
        # are precomputed per pass on the root (get_ambient_patterns).
        amb_entries, amb_blocked = resolver.get_ambient_patterns()
        blocked = blocked or amb_blocked
        for parent, own in amb_entries:
            add(parent, own)
        result = g.INCOMPLETE if blocked else g.EMPTY
        for tp, own in ordered_specs:
            result = result + find_in_class(tp, own)
        return result

    def _find_generic_types(self, query: str) -> list[g.Resolved[TypeStatement]]:
        return [g.Resolved(tp.name, tp, g.ResolvedScope.LOCAL) for tp in self.type_params if g.name_matches(tp.name, query)]

    def _initialiser_resolver(self, resolver: g.Resolver,
                              local_lets: Sequence[DataStatement] = ()) -> g.Resolver:
        """Resolver for a body or initialiser: this statement's generic type
        params, any local lets (a function's parameters), and the trait /
        interface methods — operators included — that are in scope. Function
        bodies and global-let initialisers share it so operators resolve the
        same in each."""
        typed = g.ResolverType(resolver, self._find_generic_types)
        # Trait / interface operators JOIN this scope (only a local shadows), and
        # this scope is established ONCE, here, for a top-level function or let.
        # Inner functions carry no `where`: they do not call this and never add
        # their own trait scope, inheriting this one lexically from their owner.
        joined = g.ResolverTraitData(typed, self._find_trait_data)
        if not local_lets:
            return joined
        def find_locals(query: str) -> list[g.Resolved[DataStatement]]:
            return [g.Resolved(let.name, let, g.ResolvedScope.LOCAL)
                    for let in local_lets if g.name_matches(let.name, query)]
        return g.ResolverData(joined, find_locals)

    def add_namespace(self, path: str):
        return dataclasses.replace(self, name=f"{path}{self.name}")

    def check_caller_type_params(self, resolver: g.Resolver, caller_type_params: Sequence[t.TypeSpec], line_ref: LineRef) -> list[Error]:
        if len(caller_type_params) > len(self.type_params):
            return [Error(line_ref, "Excess type parameters")]
        if len(caller_type_params) < len(self.type_params):
            return [Error(line_ref, "Not enough type parameters")]

        # replace type_params with real types in a temporary type ref
        type_params = [dataclasses.replace(tp, type=ct) for ct, tp in zip(caller_type_params, self.type_params)]
        resolver = g.ResolverType(resolver, lambda query:
            [g.Resolved(tp.name, tp, g.ResolvedScope.LOCAL) for tp in type_params if g.name_matches(tp.name, query)])

        # for each trait_param
        #   temporary compile, to resolve real type parameters
        #   find one trait that is assignment compatible
        trait_providers = resolver.get_traits()
        for trait_param in self.trait_params:
            compiled, extra = trait_param.compile(resolver)
            if extra: # Skip if compilation is still producing new statements
                return [Error(line_ref, f"Compile steps incomplete for '{trait_param.name}'. Seeing this message indicates a compiler error.")]
            tp_found = [tp for tp in trait_providers if t.trivially_assignable_equals(resolver, compiled, tp.declared_type)]
            if len(tp_found) == 0:
                return [Error(line_ref, f"Trait parameter '{trait_param.name}' does not match any trait")]

        return []


@dataclass
class TypeStatement(NamedStatement):
    def get_type(self) -> t.TypeSpec|None:
        raise NotImplementedError()


@dataclass
class DataStatement(NamedStatement):
    def compile(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> tuple[DataStatement, list[Statement]]:
        raise NotImplementedError()

    def get_type(self) -> t.TypeSpec|None:
        raise NotImplementedError()


@dataclass
class ImportStatement(Statement):
    path: str

    def compile(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> tuple[Statement | None, list[Statement]]:
        return self, []

    def check(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> list[Error]:
        return []


@dataclass
class NamespaceStatement(Statement):
    path: str

    def compile(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> tuple[Statement | None, list[Statement]]:
        return self, []

    def check(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> list[Error]:
        return []
