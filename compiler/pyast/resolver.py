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
    def find_type(self, names: set[str]) -> list[Resolved[s.TypeStatement]]:
        return []

    def find_data(self, names: set[str]) -> list[Resolved[s.DataStatement]]:
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

def match_names(name: str, matches: set[str]) -> bool:
    return any(m for m in matches if m == name or name.startswith(m + '@'))


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

    def find_type(self, names: set[str]) -> list[Resolved[s.TypeStatement]]:
        seen: set[int] = set()
        results: list[Resolved[s.TypeStatement]] = []
        for name in names:
            for resolved in self.__type_index.get(name, []):
                rid = id(resolved)
                if rid not in seen:
                    seen.add(rid)
                    results.append(resolved)
        return results

    def find_data(self, names: set[str]) -> list[Resolved[s.DataStatement]]:
        seen: set[int] = set()
        results: list[Resolved[s.DataStatement]] = []
        for name in names:
            for resolved in self.__data_index.get(name, []):
                rid = id(resolved)
                if rid not in seen:
                    seen.add(rid)
                    results.append(resolved)
        return results

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
    __scopes: set[str]

    def __init__(self, parent: Resolver, scopes: set[str] | s.ImportGroup | None):
        self.__parent = parent
        self.__scopes = set() if scopes is None else\
                set(x.path for x in scopes.imports) if isinstance(scopes, s.ImportGroup) else\
                scopes

    def __expand_names(self, names: set[str]) -> set[str]:
        def expand_names(name: str) -> list[str]:
            if "::" in name or "@" in name:
                return [name]
            else:
                return [name] + [f"{scope}::{name}" for scope in self.__scopes]
        result = set(new_name for name in names for new_name in expand_names(name))
        return result

    def find_type(self, names: set[str]) -> list[Resolved[s.TypeStatement]]:
        return self.__parent.find_type(self.__expand_names(names))

    def find_data(self, names: set[str]) -> list[Resolved[s.DataStatement]]:
        return self.__parent.find_data(self.__expand_names(names))

    def get_traits(self) -> list[s.LetStatement]:
        return self.__parent.get_traits()

    def get_implicit_where_specs(self, scopes: set[str] | None = None) -> list[t.TypeSpec]:
        merged = self.__scopes if scopes is None else (self.__scopes | scopes)
        return self.__parent.get_implicit_where_specs(merged)

    def get_discriminators(self) -> dict[str, int]:
        return self.__parent.get_discriminators()

    def get_optimization_level(self) -> int:
        return self.__parent.get_optimization_level()


class ResolverType(Resolver):
    __parent: Resolver
    __find: Callable[[set[str]], list[Resolved[s.TypeStatement]]]

    def __init__(self, parent: Resolver, find: Callable[[set[str]], list[Resolved[s.TypeStatement]]]):
        self.__parent = parent
        self.__find = find

    def find_type(self, names: set[str]) -> list[Resolved[s.TypeStatement]]:
        return self.__parent.find_type(names) + self.__find(names)

    def find_data(self, names: set[str]) -> list[Resolved[s.DataStatement]]:
        return self.__parent.find_data(names)

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
    __find: Callable[[set[str]], list[Resolved[s.DataStatement]]]

    def __init__(self, parent: Resolver, find: Callable[[set[str]], list[Resolved[s.DataStatement]]]):
        self.__parent = parent
        self.__find = find

    def find_type(self, names: set[str]) -> list[Resolved[s.TypeStatement]]:
        return self.__parent.find_type(names)

    def find_data(self, names: set[str]) -> list[Resolved[s.DataStatement]]:
        # Lexical shadowing: a name bound at this scope hides the same name
        # in any enclosing scope. Without this, a lambda parameter named `io`
        # inside a function with a parameter also named `io` triggers an
        # ambiguity error ("Resolved too many io") instead of shadowing.
        own = self.__find(names)
        if own:
            return own
        return self.__parent.find_data(names)

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

    def find_type(self, names: set[str]) -> list[Resolved[s.TypeStatement]]:
        return self.__parent.find_type(names)

    def find_data(self, names: set[str]) -> list[Resolved[s.DataStatement]]:
        return self.__parent.find_data(names)

    def get_traits(self) -> list[s.LetStatement]:
        return self.__parent.get_traits()

    def get_implicit_where_specs(self, scopes: set[str] | None = None) -> list[t.TypeSpec]:
        return self.__parent.get_implicit_where_specs(scopes)

    def get_discriminators(self) -> dict[str, int]:
        return self.__discriminators

    def get_optimization_level(self) -> int:
        return self.__optimization_level

