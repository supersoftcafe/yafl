from __future__ import annotations

from collections.abc import Mapping
from abc import ABC, abstractmethod, abstractproperty
from dataclasses import dataclass, field
from typing import Optional, Callable, List, Dict, OrderedDict, Any, Tuple, Union
from codegen.tools import mangle_name

word_size = 8


@dataclass(frozen=True)
class Type(ABC):
    @property
    @abstractmethod
    def size(self) -> int:
        pass

    @property
    def alignment(self) -> int:
        return self.size

    def offsetof(self, *args) -> int:
        if args:
            raise ValueError()
        return 0

    def _initialise(self, type_cache: Dict[Type, (str, str)], data: Any, field_indent: str) -> str:
        return f"{data}"

    def _declare_struct(self, type_cache: Dict[Type, (str, str)], field_indent: str) -> str:
        raise NotImplementedError()

    def _declare(self, type_cache: Dict[Type, (str, str)], field_indent: str) -> str:
        if self not in type_cache:
            type_str = f"typedef {self._declare_struct(type_cache, "    ")}"
            name = f"struct_anon_{len(type_cache)}_t"
            type_cache[self] = name, f"{type_str} {name};"
        else:
            value = type_cache[self]
            name, _ = value
        return name

    def initialise(self, type_cache: Dict[Type, (str, str)], data: Any) -> str:
        return self._initialise(type_cache, data, "    ")

    def declare(self, type_cache: Dict[Type, (str, str)]) -> str:
        return self._declare(type_cache, "    ")

    def get_pointer_paths(self, path: str) -> List[str]:
        return []


@dataclass(frozen=True)
class Int(Type):
    precision: int = 0 # Bit precision

    @property
    def size(self) -> int:
        return self.precision // 8 if self.precision != 0 else word_size

    def _initialise(self, type_cache: Dict[Type, (str, str)], data: Any, field_indent: str) -> str:
        return f"{data}"

    def _declare(self, type_cache: Dict[Type, (str, str)], field_indent: str) -> str:
        return f"int{self.precision}_t" if self.precision != 0 else "void*"


@dataclass(frozen=True)
class IntPtr(Type):
    @property
    def size(self) -> int:
        return word_size

    def _initialise(self, type_cache: Dict[Type, (str, str)], data: Any, field_indent: str) -> str:
        return f"{data}"

    def _declare(self, type_cache: Dict[Type, (str, str)], field_indent: str) -> str:
        return "intptr_t"


@dataclass(frozen=True)
class DataPointer(Type):
    @property
    def size(self) -> int:
        return word_size

    def _declare(self, type_cache: Dict[Type, (str, str)], field_indent: str) -> str:
        return "void*"

    def get_pointer_paths(self, path: str) -> List[str]:
        return [path]


@dataclass(frozen=True)
class FuncPointer(Type):
    @property
    def size(self) -> int:
        return word_size * 2

    @property
    def alignment(self) -> int:
        return word_size

    def offsetof(self, *args):
        match args:
            case [0] | []:
                return 0
            case [1]:
                return word_size
            case _:
                raise ValueError()

    def _initialise(self, type_cache: Dict[Type, (str, str)], data: Any, field_indent: str) -> str:
        fun, obj = (data['f'], data['o'] or "NULL") if isinstance(data, Mapping) else (str(data), "NULL")
        return f"(fun_t){{ .f = {fun}, .o = {obj} }}"

    def _declare(self, type_cache: Dict[Type, (str, str)], field_indent: str) -> str:
        return "fun_t"

    def get_pointer_paths(self, path: str) -> List[str]:
        return [f"{path}.o"]


@dataclass(frozen=True)
class Struct(Type):
    fields: Tuple[Tuple[str, Type], ...]

    @property
    def size(self) -> int:
        sz, al = 0, 0
        for name, field_type in self.fields:
            a = field_type.alignment
            sz = (sz + a - 1) // a * a + field_type.size # Bring up to alignment requirement and then add size
            al = max(al, a)
        return (sz + al - 1) // al * al if al else 0 # Round up to alignment size

    @property
    def alignment(self) -> int:
        return max(field_type.alignment for name, field_type in self.fields)

    def offsetof(self, *args):
        match args:
            case [index, *rest]:
                if isinstance(index, str):
                    index = next((i for i, x in enumerate(self.fields) if x[0] == str), -1)
                last = self.fields[index][1]
                return Struct(self.fields[:index+1]).size - last.size + last.offsetof(*rest)
            case _:
                raise ValueError()

    def _initialise(self, type_cache: Dict[Type, (str, str)], data: Any, field_indent: str) -> str:
        all_names = [name for name, type in self.fields]
        missing_names = [name for name, value in data.items() if name not in all_names]
        if any(missing_names):
            raise ValueError(f"Fields {missing_names} are not present in the struct for initialisation")
        new_indent = field_indent + "    "
        strings = ",".join(f"\n{new_indent}.{mangle_name(name)} = {field_type._initialise(type_cache, data[name], new_indent)}" for name, field_type in self.fields if name in data)
        return f"{{ {strings} \n{field_indent}}}"

    def _declare_struct(self, type_cache: Dict[Type, (str, str)], field_indent: str) -> str:
        new_indent = field_indent + "    "
        return f"struct {{ {"".join(f"\n{field_indent}{field_type._declare(type_cache, new_indent)} {mangle_name(name)};" for name, field_type in self.fields)}\n{field_indent[:-4]}}}"

    def __add__(self, other: Struct) -> Struct:
        return Struct(self.fields + other.fields)

    def get_pointer_paths(self, path: str) -> List[str]:
        return [pointer_path for name, field_type in self.fields for pointer_path in
                field_type.get_pointer_paths(f"{path}.{mangle_name(name)}")]


@dataclass(frozen=True)
class Array(Type):
    type: Type
    length: int

    @property
    def size(self) -> int:
        return self.type.size * self.length

    @property
    def alignment(self) -> int:
        return self.type.alignment

    def offsetof(self, *args):
        match args:
            case [index, *rest]:
                return self.type.size * index + self.type.offsetof(*rest)
            case _:
                raise ValueError()

    def _initialise(self, type_cache: Dict[Type, (str, str)], data: Any, field_indent: str) -> str:
        new_indent = field_indent + "    "
        strings = ",".join(f"\n{field_indent}.a[{index}] = {self.type._initialise(type_cache, item, new_indent)}" for index, item in enumerate(data))
        return f"{{ {strings} \n{field_indent[:-4]}}}"

    def _declare(self, type_cache: Dict[Type, (str, str)], field_indent: str) -> str:
        new_indent = field_indent + "    "
        return f"struct {{\n{field_indent}{self.type._declare(type_cache, new_indent)} a[{self.length}];\n{field_indent[:-4]}}}"

    def get_pointer_paths(self, path: str) -> List[str]:
        return [pointer_path for index in range(self.length) for pointer_path in
                self.type.get_pointer_paths(f"{path}.a[{index}]")]
