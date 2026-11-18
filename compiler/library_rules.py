"""The rules that let each library converge as a layer of its own (#136).

A library is settled before anything above it compiles, so nothing above it
may change how it compiles. Two rules are about WHERE code is declared, so
they live here in the driver, which knows which library each statement came
from (a statement alone does not: its file name is relative to its own
library's root):

  1. NAMESPACE OWNERSHIP — a library declares only into the namespaces its
     manifest lists; a program declares into none that a library lists.
  2. NO ORPHAN INSTANCES — Rust's rule. An instance of `Iface<T1..Tn>` must
     own the interface, or some Ti whose OUTERMOST type it owns, with no bare
     type parameter before that Ti. Ownership is by namespace alone: rule 1
     already gives every namespace exactly one owner.

The third rule, no cycles between libraries, is in the layer ordering
(compiler._library_layers). The port mirrors this file in
bootstrap/driver/library_rules.yafl.
"""
from __future__ import annotations

from dataclasses import dataclass

import pyast.resolver as g
import pyast.statement as s
import pyast.typespec as t
from parsing.parselib import Error


@dataclass(frozen=True)
class Owner:
    """Who declares a layer. A library owns the namespaces its manifest
    lists; the program (`library` None) owns every namespace that no library
    lists, `namespaces` then holding the libraries' ones."""
    library: str | None
    namespaces: frozenset[str]

    def owns(self, namespace: str) -> bool:
        listed = namespace in self.namespaces
        return listed if self.library is not None else not listed

    def described(self) -> str:
        return f"library '{self.library}'" if self.library is not None else "the program"


# ── rule 1: namespace ownership ──────────────────────────────────────────────

def library_namespace_errors(library: str, namespaces: frozenset[str],
                             statements: list[s.Statement]) -> list[Error]:
    """A library's statements outside its manifest's namespaces: one error per
    namespace, at its first statement."""
    return [Error(st.line_ref, f"'{ns}' is not a namespace of library '{library}'")
            for ns, st in _first_per_namespace(statements).items() if ns not in namespaces]


def program_namespace_errors(listed: dict[str, str],
                             statements: list[s.Statement]) -> list[Error]:
    """The program's statements in a namespace a library lists (`listed`:
    namespace -> library name): one error per namespace, at its first."""
    return [Error(st.line_ref, f"namespace '{ns}' belongs to library '{listed[ns]}'")
            for ns, st in _first_per_namespace(statements).items() if ns in listed]


def _first_per_namespace(statements: list[s.Statement]) -> dict[str, s.Statement]:
    first: dict[str, s.Statement] = {}
    for st in statements:
        name = getattr(st, "name", "")
        if name:
            first.setdefault(g.namespace_of(name), st)
    return first


# ── rule 2: no orphan instances ──────────────────────────────────────────────

def orphan_errors(owner: Owner, statements: list[s.Statement]) -> list[Error]:
    """Every converged instance in a layer that owns neither its interface nor
    an uncovered type argument. An interface still unresolved is check()'s
    to report."""
    return [Error(st.line_ref,
                  f"orphan instance of '{g.simple_name(st.pattern.name)}': {owner.described()} "
                  f"owns neither the interface nor the type it is implemented for")
            for st in statements
            if isinstance(st, s.TraitInstanceStatement) and isinstance(st.pattern, t.ClassSpec)
            and not _owned_instance(owner, st.pattern)]


def _owned_instance(owner: Owner, pattern: t.ClassSpec) -> bool:
    if owner.owns(g.namespace_of(pattern.name)):
        return True
    for arg in pattern.type_params:
        if isinstance(arg, t.GenericPlaceholderSpec):
            return False                    # uncovered: anyone's type could fill it
        outer = _outermost_name(arg)
        if outer is not None and owner.owns(g.namespace_of(outer)):
            return True
    return False


def _outermost_name(spec: t.TypeSpec) -> str | None:
    """The declaration a type is, at its outermost: `List<Mine>` is `List`.
    A builtin, tuple, union or function type is nobody's to own."""
    if isinstance(spec, t.ClassSpec):
        return spec.name
    if isinstance(spec, t.EnumSpec):
        return spec.root_name
    return None
