from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Optional, Callable, List, Dict, Any, Tuple, Union
from codegen.tools import mangle_name
import codegen.typedecl as t


@dataclass(frozen=True)
class RParam:
    def rename_vars(self, renames: dict[str, str]) -> RParam:
        return self

    def to_c(self, type_cache: Dict[t.Type, (str, str)]) -> str:
        return ""


@dataclass(frozen=True)
class NewObject(RParam): # Create a new blank instance of the named object
    name: str
    size: RParam|None = None

    def rename_vars(self, renames: dict[str, str]) -> NewObject:
        return dataclasses.replace(self, size = self.size and self.size.rename_vars(renames))

    def to_c(self, type_cache: Dict[t.Type, (str, str)]) -> str:
        if self.size is not None:
            return f"array_create((vtable_t*)&{self.name}, {self.size})"
        else:
            return f"object_create((vtable_t*)&{self.name})"


@dataclass(frozen=True)
class NewStruct(RParam): # Create a new blank instance of the defined struct
    type: t.Type
    values: tuple[tuple[str, RParam], ...]

    def rename_vars(self, renames: dict[str, str]) -> NewStruct:
        return dataclasses.replace(self, values = tuple((name, rparam.rename_vars(renames)) for name, rparam in self.values))

    def to_c(self, type_cache: Dict[t.Type, (str, str)]) -> str:
        type_name = self.type.declare(type_cache)
        init_values = dict((name, expr.to_c(type_cache)) for name, expr in self.values)
        return f"({type_name}){self.type.initialise(type_cache, init_values)}"


@dataclass(frozen=True)
class Invoke(RParam):
    function: str
    parameters: tuple[RParam, ...]

    def rename_vars(self, renames: dict[str, str]) -> Invoke:
        return dataclasses.replace(self, parameters = tuple(rparam.rename_vars(renames) for rparam in self.parameters))

    def to_c(self, type_cache: Dict[t.Type, (str, str)]) -> str:
        return f"{self.function}({", ".join(src.to_c(type_cache) for src in self.parameters)})"


@dataclass(frozen=True)
class StructField(RParam):
    struct: RParam
    field: str

    def rename_vars(self, renames: dict[str, str]) -> StructField:
        return dataclasses.replace(self, struct = self.struct.rename_vars(renames))

    def to_c(self, type_cache: Dict[t.Type, (str, str)]) -> str:
        return f"({self.struct.to_c(type_cache)}.{mangle_name(self.field)})"


@dataclass(frozen=True)
class Immediate(RParam):
    value: int|str

    def to_c(self, type_cache: Dict[t.Type, (str, str)]) -> str:
        return str(self.value)


@dataclass(frozen=True)
class GlobalFunction(RParam):
    name: str
    object: RParam|None = None

    def rename_vars(self, renames: dict[str, str]) -> GlobalFunction:
        return dataclasses.replace(self, object = self.object and self.object.rename_vars(renames))

    def to_c(self, type_cache: Dict[t.Type, (str, str)]) -> str:
        return f"((fun_t){{.f={mangle_name(self.name)},.o={self.object.to_c(type_cache) if self.object else 'NULL'}}})"


@dataclass(frozen=True)
class VirtualFunction(RParam):
    name: str
    object: RParam

    def rename_vars(self, renames: dict[str, str]) -> VirtualFunction:
        return dataclasses.replace(self, object = self.object.rename_vars(renames))

    def to_c(self, type_cache: Dict[t.Type, (str, str)]) -> str:
        return f"(vtable_lookup({self.object.to_c(type_cache)}, __FUNCTION_ID__{mangle_name(self.name)}))"


@dataclass(frozen=True)
class LParam(RParam):
    def rename_vars(self, renames: dict[str, str]) -> LParam:
        return self


@dataclass(frozen=True)
class StackVar(LParam):
    name: str

    def rename_vars(self, renames: dict[str, str]) -> StackVar:
        return dataclasses.replace(self, name = renames.get(self.name, self.name))

    def to_c(self, type_cache: Dict[t.Type, (str, str)]) -> str:
        return mangle_name(self.name)


@dataclass(frozen=True)
class GlobalVar(LParam):
    name: str   # Object globals resolve to a pointer

    def rename_vars(self, renames: dict[str, str]) -> GlobalVar:
        return self

    def to_c(self, type_cache: Dict[t.Type, (str, str)]) -> str:
        return mangle_name(self.name)


@dataclass(frozen=True)
class ObjectField(LParam):
    pointer: RParam
    object_name: str         # Which object type
    field: str               # Which named field
    index: RParam|None  # If 'field' is an array, this is required

    def rename_vars(self, renames: dict[str, str]) -> ObjectField:
        return dataclasses.replace(self, pointer = self.pointer.rename_vars(renames), index = self.index and self.index.rename_vars(renames))

    def to_c(self, type_cache: Dict[t.Type, (str, str)]) -> str:
        index = f"[{self.index.to_c(type_cache)}]" if self.index is not None else ""
        return f"(({mangle_name(self.object_name)}_t*){self.pointer})->{mangle_name(self.field)}{index}"
