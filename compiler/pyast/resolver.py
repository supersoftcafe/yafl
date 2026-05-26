from __future__ import annotations

from enum import Enum
from collections.abc import Callable
from dataclasses import dataclass

import codegen.typedecl as cg_t
import codegen.param as cg_p
import codegen.ops as cg_o

import pyast.statement as s
import pyast.typespec as t


class FunctionBuilder:
    stack_vars: dict[str, cg_t.Type]
    operations: list[cg_o.Op]

    def __init__(self):
        self.stack_vars = dict()
        self.operations = list()

    def add_op(self, op: cg_o.Op):
        self.operations.append(op)

    def add_var(self, vtype: cg_t.Type) -> str:
        name = f"var_{len(self.stack_vars)}"
        self.stack_vars[name] = vtype
        return name


@dataclass(frozen=True)
class OperationBundle:
    stack_vars: tuple[cg_p.StackVar, ...] = ()
    operations: tuple[cg_o.Op, ...] = ()
    result_var: cg_p.RParam|None = None

    def with_prefix(self, prefix: str|int) -> OperationBundle:
        """Mark this bundle as living at structural path component `prefix`
        relative to the surrounding bundle. Every internal StackVar and
        Label name gets `{prefix}/` prepended; externally-qualified names
        (containing '@') and `this` are left alone.

        The prefix is a *position*, not a counter. The same AST shape
        composed the same way produces the same names — no monotonic
        counter threads through generation. Integer prefixes are accepted
        for backward compatibility with call sites that previously passed
        position-as-int; they are rendered without further decoration.
        """
        if isinstance(prefix, int):
            prefix = str(prefix)
        if not prefix:
            # Empty prefix is a no-op: callers that previously passed "" to
            # collapse path structure into a flat `uvar_N` sequence are now
            # explicitly opting out of any structural mark.
            return self

        def attach(name: str) -> str:
            if "@" in name or name == "this":
                return name
            return f"{prefix}/{name}"

        var_renames = {sv.name: attach(sv.name) for sv in self.stack_vars}
        label_renames = {op.name: attach(op.name) for op in self.operations if isinstance(op, cg_o.Label)}
        renames = var_renames | label_renames
        if not renames:
            return self
        return OperationBundle(
            stack_vars=tuple(sv.rename_vars(renames) for sv in self.stack_vars),
            operations=tuple(op.rename_vars(renames) for op in self.operations),
            result_var=self.result_var and self.result_var.rename_vars(renames))

    def __add__(self, other: OperationBundle) -> OperationBundle:
        return OperationBundle(
            self.stack_vars + other.stack_vars,
            self.operations + other.operations,
            other.result_var)


class ResolvedScope(Enum):
    GLOBAL = 1
    MEMBER = 2
    LOCAL  = 3
    TRAIT  = 4   # Found an interface member that must be treated as a trait reference during lowering


@dataclass(frozen=True)
class Resolved[T]:
    unique_name: str
    statement: T
    scope: ResolvedScope
    trait_scope: t.TypeSpec|None = None     # We need this for mapping local types to target class types
    owner_class: s.ClassStatement|None = None    # We need this for the generic type declarations


class Resolver:
    def find_type(self, name: str) -> list[Resolved[s.TypeStatement]]:
        return []

    def find_data(self, name: str) -> list[Resolved[s.DataStatement]]:
        return []

    def get_traits(self) -> list[s.LetStatement]:
        return []

    def get_implicit_where_specs(self, scopes: set[str] | None = None) -> list[t.TypeSpec]:
        return []

    def get_discriminators(self) -> dict[str, int]:
        return {}

    def get_optimization_level(self) -> int:
        return 0


def simple_name(name: str) -> str:
    return name.rpartition('@')[0] or name

def match_name(left: str, right: str) -> bool:
    return simple_name(left) == simple_name(right)

# Match a candidate statement name (`candidate`) against a single lookup
# `query` — true if they're identical, or if `candidate` is a fully-qualified
# variant of `query` (i.e. starts with `query@`).
def name_matches(candidate: str, query: str) -> bool:
    return candidate == query or candidate.startswith(query + '@')


def _name_prefixes(name: str) -> list[str]:
    parts = name.split('@')
    return ['@'.join(parts[:i+1]) for i in range(len(parts))]


def _index_enum_variants(
    variants: list[s.EnumStatement],
    index: dict[str, list[Resolved[s.TypeStatement]]]
) -> None:
    for v in variants:
        resolved: Resolved[s.TypeStatement] = Resolved(v.name, v, ResolvedScope.GLOBAL)
        for key in _name_prefixes(v.name):
            index.setdefault(key, []).append(resolved)
        _index_enum_variants(v.variants, index)


_EMPTY_TYPE_RESULT: list[Resolved[s.TypeStatement]] = []
_EMPTY_DATA_RESULT: list[Resolved[s.DataStatement]] = []


class ResolverRoot(Resolver):
    __statements: list[s.Statement]
    __traits: list[s.LetStatement]
    __type_index: dict[str, list[Resolved[s.TypeStatement]]]
    __data_index: dict[str, list[Resolved[s.DataStatement]]]

    def __init__(self, statements: list[s.Statement]) -> None:
        self.__statements = statements
        self.__traits = [st for st in self.__statements if isinstance(st, s.LetStatement) and 'trait' in st.attributes]

        self.__type_index = {}
        for st in self.__statements:
            if isinstance(st, s.TypeStatement):
                resolved: Resolved[s.TypeStatement] = Resolved(st.name, st, ResolvedScope.GLOBAL)
                for key in _name_prefixes(st.name):
                    self.__type_index.setdefault(key, []).append(resolved)
            if isinstance(st, s.EnumStatement):
                _index_enum_variants(st.variants, self.__type_index)

        self.__data_index = {}
        for st in self.__statements:
            if isinstance(st, s.DataStatement):
                resolved_d: Resolved[s.DataStatement] = Resolved(st.name, st, ResolvedScope.GLOBAL)
                for key in _name_prefixes(st.name):
                    self.__data_index.setdefault(key, []).append(resolved_d)

    def find_type(self, name: str) -> list[Resolved[s.TypeStatement]]:
        return self.__type_index.get(name, _EMPTY_TYPE_RESULT)

    def find_data(self, name: str) -> list[Resolved[s.DataStatement]]:
        return self.__data_index.get(name, _EMPTY_DATA_RESULT)

    def get_traits(self) -> list[s.LetStatement]:
        return self.__traits

    def get_implicit_where_specs(self, scopes: set[str] | None = None) -> list[t.TypeSpec]:
        if not scopes:
            return []
        return [st.type for st in self.__statements
                if isinstance(st, s.TypeAliasStatement) and 'where' in st.attributes
                and isinstance(st.type, t.ClassSpec) and st.type.is_concrete()
                and st.name.rpartition('::')[0] in scopes]


class AddScopeResolution(Resolver):
    __parent: Resolver
    __scopes: tuple[str, ...]
    # Result caches — short-lived (this resolver lives for one statement-scope
    # walk) but a single walk does ~1k–10k lookups, most of them repeats.
    __type_cache: dict[str, list[Resolved[s.TypeStatement]]]
    __data_cache: dict[str, list[Resolved[s.DataStatement]]]

    def __init__(self, parent: Resolver, scopes: set[str] | s.ImportGroup | None):
        self.__parent = parent
        if scopes is None:
            self.__scopes = ()
        elif isinstance(scopes, s.ImportGroup):
            self.__scopes = tuple(x.path for x in scopes.imports)
        else:
            self.__scopes = tuple(scopes)
        self.__type_cache = {}
        self.__data_cache = {}

    def find_type(self, name: str) -> list[Resolved[s.TypeStatement]]:
        cached = self.__type_cache.get(name)
        if cached is not None:
            return cached
        result = self.__parent.find_type(name)
        if "::" not in name and "@" not in name:
            for scope in self.__scopes:
                result = result + self.__parent.find_type(f"{scope}::{name}")
        self.__type_cache[name] = result
        return result

    def find_data(self, name: str) -> list[Resolved[s.DataStatement]]:
        cached = self.__data_cache.get(name)
        if cached is not None:
            return cached
        result = self.__parent.find_data(name)
        if "::" not in name and "@" not in name:
            for scope in self.__scopes:
                result = result + self.__parent.find_data(f"{scope}::{name}")
        self.__data_cache[name] = result
        return result

    def get_traits(self) -> list[s.LetStatement]:
        return self.__parent.get_traits()

    def get_implicit_where_specs(self, scopes: set[str] | None = None) -> list[t.TypeSpec]:
        own = set(self.__scopes)
        merged = own if scopes is None else (own | scopes)
        return self.__parent.get_implicit_where_specs(merged)

    def get_discriminators(self) -> dict[str, int]:
        return self.__parent.get_discriminators()

    def get_optimization_level(self) -> int:
        return self.__parent.get_optimization_level()


class ResolverType(Resolver):
    __parent: Resolver
    __find: Callable[[str], list[Resolved[s.TypeStatement]]]
    __cache: dict[str, list[Resolved[s.TypeStatement]]]

    def __init__(self, parent: Resolver, find: Callable[[str], list[Resolved[s.TypeStatement]]]):
        self.__parent = parent
        self.__find = find
        self.__cache = {}

    def find_type(self, name: str) -> list[Resolved[s.TypeStatement]]:
        cached = self.__cache.get(name)
        if cached is not None:
            return cached
        result = self.__parent.find_type(name) + self.__find(name)
        self.__cache[name] = result
        return result

    def find_data(self, name: str) -> list[Resolved[s.DataStatement]]:
        return self.__parent.find_data(name)

    def get_traits(self) -> list[s.LetStatement]:
        return self.__parent.get_traits()

    def get_implicit_where_specs(self, scopes: set[str] | None = None) -> list[t.TypeSpec]:
        return self.__parent.get_implicit_where_specs(scopes)

    def get_discriminators(self) -> dict[str, int]:
        return self.__parent.get_discriminators()

    def get_optimization_level(self) -> int:
        return self.__parent.get_optimization_level()


class ResolverData(Resolver):
    __parent: Resolver
    __find: Callable[[str], list[Resolved[s.DataStatement]]]
    __cache: dict[str, list[Resolved[s.DataStatement]]]

    def __init__(self, parent: Resolver, find: Callable[[str], list[Resolved[s.DataStatement]]]):
        self.__parent = parent
        self.__find = find
        self.__cache = {}

    def find_type(self, name: str) -> list[Resolved[s.TypeStatement]]:
        return self.__parent.find_type(name)

    def find_data(self, name: str) -> list[Resolved[s.DataStatement]]:
        cached = self.__cache.get(name)
        if cached is not None:
            return cached
        # Lexical shadowing: a name bound at this scope hides the same name
        # in any enclosing scope. Without this, a lambda parameter named `io`
        # inside a function with a parameter also named `io` triggers an
        # ambiguity error ("Resolved too many io") instead of shadowing.
        own = self.__find(name)
        result = own if own else self.__parent.find_data(name)
        self.__cache[name] = result
        return result

    def get_traits(self) -> list[s.LetStatement]:
        return self.__parent.get_traits()

    def get_implicit_where_specs(self, scopes: set[str] | None = None) -> list[t.TypeSpec]:
        return self.__parent.get_implicit_where_specs(scopes)

    def get_discriminators(self) -> dict[str, int]:
        return self.__parent.get_discriminators()

    def get_optimization_level(self) -> int:
        return self.__parent.get_optimization_level()


class ResolverDiscriminators(Resolver):
    __parent: Resolver
    __discriminators: dict[str, int]
    __optimization_level: int

    def __init__(self, parent: Resolver, discriminators: dict[str, int], optimization_level: int = 0):
        self.__parent = parent
        self.__discriminators = discriminators
        self.__optimization_level = optimization_level

    def find_type(self, name: str) -> list[Resolved[s.TypeStatement]]:
        return self.__parent.find_type(name)

    def find_data(self, name: str) -> list[Resolved[s.DataStatement]]:
        return self.__parent.find_data(name)

    def get_traits(self) -> list[s.LetStatement]:
        return self.__parent.get_traits()

    def get_implicit_where_specs(self, scopes: set[str] | None = None) -> list[t.TypeSpec]:
        return self.__parent.get_implicit_where_specs(scopes)

    def get_discriminators(self) -> dict[str, int]:
        return self.__discriminators

    def get_optimization_level(self) -> int:
        return self.__optimization_level

