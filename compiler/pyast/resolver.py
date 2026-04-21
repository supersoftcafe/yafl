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

    def __get_new_labels(self, prefix: str, base_index: int) -> dict[str, str]:
        return dict((name, f"ulabel_{prefix}{index}") for index, name in enumerate((l.name for l in self.operations if isinstance(l, cg_o.Label)), base_index))

    def __get_new_vars(self, prefix: str, base_index: int) -> dict[str, str]:
        return dict( (sv.name, f"uvar_{prefix}{index}") for index, sv in enumerate(self.stack_vars, base_index) if '@' not in sv.name and sv.name != "this" )

    def __rename_labels_and_vars(self, renames: dict[str, str]) -> OperationBundle:
        stack_vars = tuple(sv.rename_vars(renames) for sv in self.stack_vars)
        operations = tuple(op.rename_vars(renames) for op in self.operations)
        return OperationBundle(stack_vars, operations)

    # def append(self, other: OperationBundle) -> OperationBundle:
    #     # If a var is referenced, or a jump target is used, that does not exist in the local stack
    #     # or as a local label, it must reference something external, and so remains untouched. We
    #     # only rename the things that are internal to this bundle.
    #
    #     vars1 = self.__get_new_vars(0)
    #     labels1 = self.__get_new_labels(0)
    #     bundle1 = self.__rename_labels_and_vars(labels1 | vars1)
    #
    #     vars2 = other.__get_new_vars(len(vars1))
    #     labels2 = other.__get_new_labels(len(labels1))
    #     bundle2 = other.__rename_labels_and_vars(labels2 | vars2)
    #
    #     return OperationBundle(
    #         bundle1.stack_vars + bundle2.stack_vars,
    #         bundle1.operations + bundle2.operations,
    #         other.result_var and other.result_var.rename_vars(vars1 | vars2))

    def rename_vars(self, prefix: str|int) -> OperationBundle:
        if isinstance(prefix, int):
            prefix = f"{prefix}_"
        renames = self.__get_new_vars(prefix, 0) | self.__get_new_labels(prefix, 0)
        new_stack_vars = tuple(sv.rename_vars(renames) for sv in self.stack_vars)
        new_result_var = self.result_var and self.result_var.rename_vars(renames)
        new_operations = tuple(op.rename_vars(renames) for op in self.operations)
        return OperationBundle(new_stack_vars, new_operations, new_result_var)

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


def simple_name(name: str) -> str:
    return name.rpartition('@')[0] or name

def match_name(left: str, right: str) -> bool:
    return simple_name(left) == simple_name(right)

def match_names(name: str, matches: set[str]) -> bool:
    return any(m for m in matches if m == name or name.startswith(m + '@'))


def _find_in_enum_variants(variants: list[s.EnumStatement], names: set[str]) -> list[Resolved[s.TypeStatement]]:
    results: list[Resolved[s.TypeStatement]] = []
    for v in variants:
        if match_names(v.name, names):
            results.append(Resolved(v.name, v, ResolvedScope.GLOBAL))
        results += _find_in_enum_variants(v.variants, names)
    return results


class ResolverRoot(Resolver):
    __statements: list[s.Statement]
    __traits: list[s.LetStatement]

    def __init__(self, statements: list[s.Statement]):
        self.__statements = statements
        self.__traits = [st for st in self.__statements if isinstance(st, s.LetStatement) and 'trait' in st.attributes]

    def find_type(self, names: set[str]) -> list[Resolved[s.TypeStatement]]:
        results = [Resolved(x.name, x, ResolvedScope.GLOBAL)
                   for x in self.__statements
                   if isinstance(x, s.TypeStatement) and match_names(x.name, names)]
        for x in self.__statements:
            if isinstance(x, s.EnumStatement):
                results += _find_in_enum_variants(x.variants, names)
        return results

    def find_data(self, names: set[str]) -> list[Resolved[s.DataStatement]]:
        return [Resolved(x.name, x, ResolvedScope.GLOBAL)
                for x in self.__statements
                if isinstance(x, s.DataStatement) and match_names(x.name, names)]

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


class ResolverDiscriminators(Resolver):
    __parent: Resolver
    __discriminators: dict[str, int]

    def __init__(self, parent: Resolver, discriminators: dict[str, int]):
        self.__parent = parent
        self.__discriminators = discriminators

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

