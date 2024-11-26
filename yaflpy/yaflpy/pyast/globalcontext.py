from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import codegen.typedecl as cg_t
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
    stack_vars: tuple[tuple[str, cg_t.Type], ...] = ()
    operations: tuple[cg_o.Op, ...] = ()

    def __get_new_labels(self, base_index: int) -> dict[str, str]:
        return dict((name, f"ulabel_{index}") for index, name in enumerate((l.name for l in other.operations if isinstance(l, cg_o.Label)), base_index))

    def __get_new_vars(self, base_index: int) -> dict[str, str]:
        return dict( (name, f"uvar_{index}") for index, (name, _) in enumerate(self.stack_vars, base_index) )

    def __rename_labels_and_vars(self, renames: dict[str, str]) -> OperationBundle:
        stack_vars = tuple((renames[name], xtype) for name, xtype in self.stack_vars)
        operations = tuple(op.rename_vars(renames) for op in self.operations)
        return OperationBundle(stack_vars, operations)

    def append(self, other: OperationBundle) -> OperationBundle:
        # If a var is referenced, or a jump target is used, that does not exist in the local stack
        # or as a local label, it must reference something external, and so remains untouched. We
        # only rename the things that are internal to this bundle.
        vars1 = self.__get_new_vars(0)
        labels1 = self.__get_new_labels(0)
        bundle1 = self.__rename_labels_and_vars(labels1 | vars1)
        vars2 = other.__get_new_vars(len(vars1))
        labels2 = other.__get_new_labels(len(labels1))
        bundle2 = other.__rename_labels_and_vars(labels2 | vars2)
        return OperationBundle(bundle1.stack_vars + bundle2.stack_vars, bundle1.operations + bundle2.operations)


class Global:
    def find_global_type(self, names: set[str]) -> list[t.TypeSpec]:
        return []

    def find_global_func(self, names: set[str]) -> list[s.FunctionStatement]:
        return []

    def find_global_data(self, names: set[str]) -> list[s.LetStatement]:
        return []

    def find_local_data(self, names: set[str]) -> list[s.LetStatement]:
        return []


def _match_names(name: str, matches: set[str]) -> bool:
    for m in matches:
        if '@' in m and name == m:
            return True
        if '@' not in m and name.startswith(m + '@'):
            return True
    return False

class GlobalRoot(Global):
    __statements: list[s.Statement]

    def __init__(self, statements: list[s.Statement]):
        self.__statements = statements

    def find_global_type(self, names: set[str]) -> list[t.TypeSpec]:
        return [x.type for x in self.__statements if isinstance(x, s.TypeAliasStatement) and _match_names(x.name, names)]

    def find_global_data(self, names: set[str]) -> list[s.LetStatement]:
        return [x for x in self.__statements if isinstance(x, s.LetStatement) and _match_names(x.name, names)]

    def find_global_func(self, names: set[str]) -> list[s.FunctionStatement]:
        return [x for x in self.__statements if isinstance(x, s.FunctionStatement) and _match_names(x.name, names)]

class AddScopeResolution(Global):
    __parent: Global
    __scopes: set[str]

    def __init__(self, parent: Global, scopes: set[str]|s.ImportGroup|None):
        self.__parent = parent
        if scopes is None:
            self.__scopes = set()
        elif isinstance(scopes, s.ImportGroup):
            self.__scopes = set(x.path for x in scopes.imports)
        else:
            self.__scopes = scopes

    def __expand_names(self, names: set[str]) -> set[str]:
        return set((name if "::" in name or "@" in name else f"{scope}::{name}") for scope in self.__scopes for name in names)

    def find_global_type(self, names: set[str]) -> list[t.TypeSpec]:
        return self.__parent.find_global_type(self.__expand_names(names))

    def find_global_func(self, names: set[str]) -> list[s.FunctionStatement]:
        return self.__parent.find_global_func(self.__expand_names(names))

    def find_global_data(self, names: set[str]) -> list[s.LetStatement]:
        return self.__parent.find_global_data(self.__expand_names(names))

    def find_local_data(self, names: set[str]) -> list[s.LetStatement]:
        return self.__parent.find_local_data(names)


class GlobalType(Global):
    __parent: Global
    __find: Callable[[set[str]], list[t.TypeSpec]]

    def __init__(self, parent: Global, find: Callable[[set[str]], list[t.TypeSpec]]):
        self.__parent = parent
        self.__find = find

    def find_global_type(self, names: set[str]) -> list[t.TypeSpec]:
        return self.__parent.find_global_type(names) + self.__find(names)

    def find_global_func(self, names: set[str]) -> list[s.FunctionStatement]:
        return self.__parent.find_global_func(names)

    def find_global_data(self, names: set[str]) -> list[s.LetStatement]:
        return self.__parent.find_global_data(names)

    def find_local_data(self, names: set[str]) -> list[s.LetStatement]:
        return self.__parent.find_local_data(names)


class GlobalFunc(Global):
    __parent: Global
    __find: Callable[[set[str]], list[s.LetStatement]]

    def __init__(self, parent: Global, find: Callable[[set[str]], list[s.LetStatement]]):
        self.__parent = parent
        self.__find = find

    def find_global_type(self, names: set[str]) -> list[t.TypeSpec]:
        return self.__parent.find_global_type(names)

    def find_global_func(self, names: set[str]) -> list[s.LetStatement]:
        return self.__parent.find_global_func(names) + self.__find(names)

    def find_global_data(self, names: set[str]) -> list[s.LetStatement]:
        return self.__parent.find_global_data(names)

    def find_local_data(self, names: set[str]) -> list[s.LetStatement]:
        return self.__parent.find_local_data(names)


class GlobalData(Global):
    __parent: Global
    __find: Callable[[set[str]], list[s.LetStatement]]

    def __init__(self, parent: Global, find: Callable[[set[str]], list[s.LetStatement]]):
        self.__parent = parent
        self.__find = find

    def find_global_type(self, names: set[str]) -> list[t.TypeSpec]:
        return self.__parent.find_global_type(names)

    def find_global_func(self, names: set[str]) -> list[s.FunctionStatement]:
        return self.__parent.find_global_func(names)

    def find_global_data(self, names: set[str]) -> list[s.LetStatement]:
        return self.__parent.find_global_data(names) + self.__find(names)

    def find_local_data(self, names: set[str]) -> list[s.LetStatement]:
        return self.__parent.find_local_data(names)


class LocalData(Global):
    __parent: Global
    __find: Callable[[set[str]], list[s.LetStatement]]

    def __init__(self, parent: Global, find: Callable[[set[str]], list[s.LetStatement]]):
        self.__parent = parent
        self.__find = find

    def find_global_type(self, names: set[str]) -> list[t.TypeSpec]:
        return self.__parent.find_global_type(names)

    def find_global_func(self, names: set[str]) -> list[s.FunctionStatement]:
        return self.__parent.find_global_func(names)

    def find_global_data(self, names: set[str]) -> list[s.LetStatement]:
        return self.__parent.find_global_data(names)

    def find_local_data(self, names: set[str]) -> list[s.LetStatement]:
        return self.__parent.find_local_data(names) + self.__find(names)
