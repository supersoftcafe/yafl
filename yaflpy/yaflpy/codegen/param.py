from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Callable

from xdg.Mime import get_type

import langtools
from codegen.tools import mangle_name
import codegen.typedecl as t


@dataclass(frozen=True)
class RParam:
    def get_type(self) -> t.Type:
        raise ValueError()

    def rename_vars(self, renames: dict[str, str]) -> RParam:
        return self

    def replace_params(self, replacer: Callable[[RParam], RParam]) -> RParam:
        return replacer(self)

    def to_c(self, type_cache: dict[t.Type, tuple[str, str]]) -> str:
        return ""

    def get_live_vars(self) -> frozenset[StackVar]:
        return frozenset()


@dataclass(frozen=True)
class InitArray(RParam): # Only for static initialisation of array types
    member_type: t.Type
    values: tuple[RParam, ...]

    def rename_vars(self, renames: dict[str, str]) -> RParam:
        return dataclasses.replace(self, values = tuple(x.rename_vars(renames) for x in self.values))

    def replace_params(self, replacer: Callable[[RParam], RParam]) -> RParam:
        return replacer(dataclasses.replace(self, values=tuple(x.replace_params(replacer) for x in self.values)))

    def to_c(self, type_cache: dict[t.Type, tuple[str, str]]) -> str:
        return "{" + ", ".join(x.to_c(type_cache) for x in self.values) + "}"

    def get_live_vars(self) -> frozenset[StackVar]:
        return frozenset(y for x in self.values for y in x.get_live_vars())


@dataclass(frozen=True)
class NewStruct(RParam): # Create a new blank instance of the defined struct
    values: tuple[tuple[str, RParam], ...]

    def get_type(self) -> t.Struct:
        return t.Struct(tuple((name, rparam.get_type()) for name, rparam in self.values))

    def rename_vars(self, renames: dict[str, str]) -> NewStruct:
        return dataclasses.replace(self, values = tuple((name, rparam.rename_vars(renames)) for name, rparam in self.values))

    def replace_params(self, replacer: Callable[[RParam], RParam]) -> RParam:
        return replacer(dataclasses.replace(self, values=tuple((xn, xp.replace_params(replacer)) for xn, xp in self.values)))

    def to_c(self, type_cache: dict[t.Type, tuple[str, str]]) -> str:
        xtype = self.get_type()
        type_name = xtype.declare(type_cache)
        init_values = dict((name, expr.to_c(type_cache)) for name, expr in self.values)
        return f"({type_name}){xtype.initialise(type_cache, init_values)}"

    def get_live_vars(self) -> frozenset[StackVar]:
        return frozenset(y for xname, x in self.values for y in x.get_live_vars())

    def __add__(self, other: NewStruct) -> NewStruct:
        return NewStruct(self.values + other.values)


@dataclass(frozen=True)
class Invoke(RParam):
    function: str
    parameters: RParam
    type: t.Type

    def get_type(self) -> t.Type:
        return self.type

    def rename_vars(self, renames: dict[str, str]) -> Invoke:
        return dataclasses.replace(self, parameters = self.parameters.rename_vars(renames))

    def replace_params(self, replacer: Callable[[RParam], RParam]) -> RParam:
        return replacer(dataclasses.replace(self, parameters=self.parameters.replace_params(replacer)))

    def to_c(self, type_cache: dict[t.Type, tuple[str, str]]) -> str:
        p = self.parameters
        ptype = p.get_type()
        if not isinstance(ptype, t.Struct):
            raise ValueError("parameters must be a struct type")

        if isinstance(p, NewStruct):
            return f"{self.function}({", ".join(src.to_c(type_cache) for name, src in p.values)})"
        return f"{self.function}({", ".join(f"{p.to_c(type_cache)}.{name}" for name, ftype in ptype.fields)})"

    def get_live_vars(self) -> frozenset[StackVar]:
        return self.parameters.get_live_vars()


@dataclass(frozen=True)
class StructField(RParam):
    struct: RParam
    field: str

    def get_type(self) -> t.Type:
        xtype = self.struct.get_type()
        if not isinstance(xtype, t.Struct):
            raise ValueError("Incorrect type of 'struct'")
        xtype = next(type for name, type in xtype.fields if name == self.field)
        if not xtype:
            raise ValueError(f"Field '{self.field}' not found in 'struct'")
        return xtype

    def rename_vars(self, renames: dict[str, str]) -> StructField:
        return dataclasses.replace(self, struct = self.struct.rename_vars(renames))

    def replace_params(self, replacer: Callable[[RParam], RParam]) -> RParam:
        return replacer(dataclasses.replace(self, struct=self.struct.replace_params(replacer)))

    def to_c(self, type_cache: dict[t.Type, tuple[str, str]]) -> str:
        return f"({self.struct.to_c(type_cache)}.{mangle_name(self.field)})"

    def get_live_vars(self) -> frozenset[StackVar]:
        return self.struct.get_live_vars()


@dataclass(frozen=True)
class String(RParam):
    value: str

    def get_type(self) -> t.Str:
        return t.Str()

    def to_c(self, type_cache: dict[t.Type, tuple[str, str]]) -> str:
        return self.get_type().initialise(type_cache,self.value)


@dataclass(frozen=True)
class Integer(RParam):
    value: int
    precision: int

    def get_type(self) -> t.Int:
        return t.Int(self.precision)

    def to_c(self, type_cache: dict[t.Type, tuple[str, str]]) -> str:
        return self.get_type().initialise(type_cache,self.value)


@dataclass(frozen=True)
class GlobalFunction(RParam):
    name: str
    object: RParam|None = None

    def get_type(self) -> t.FuncPointer:
        return t.FuncPointer()

    def rename_vars(self, renames: dict[str, str]) -> GlobalFunction:
        return dataclasses.replace(self, object = self.object and self.object.rename_vars(renames))

    def replace_params(self, replacer: Callable[[RParam], RParam]) -> RParam:
        return replacer(dataclasses.replace(self, object=self.object and self.object.replace_params(replacer)))

    def to_c(self, type_cache: dict[t.Type, tuple[str, str]]) -> str:
        return f"((fun_t){{.f={mangle_name(self.name)},.o={self.object.to_c(type_cache) if self.object else 'NULL'}}})"

    def get_live_vars(self) -> frozenset[StackVar]:
        return self.object.get_live_vars() if self.object else set()


@dataclass(frozen=True)
class VirtualFunction(RParam):
    name: str
    object: RParam
    fast_lookup: bool = False

    def get_type(self) -> t.FuncPointer:
        return t.FuncPointer()

    def rename_vars(self, renames: dict[str, str]) -> VirtualFunction:
        return dataclasses.replace(self, object = self.object.rename_vars(renames))

    def replace_params(self, replacer: Callable[[RParam], RParam]) -> RParam:
        return replacer(dataclasses.replace(self, object=self.object.replace_params(replacer)))

    def to_c(self, type_cache: dict[t.Type, tuple[str, str]]) -> str:
        # TODO: If this specific use of the slot, on all classes that might apply here:
        #  1. Is always at the first try position:-
        #       We can use a faster lookup that doesn't loop.
        #  2. Is always provided by the same backing function:-
        #       We can avoid a lookup at all.
        # For this to work we must pre-calculate all vtables, and have all of them available here to examine.
        return f"(vtable_lookup({self.object.to_c(type_cache)}, __FUNCTION_ID__{mangle_name(self.name)}))"

    def get_live_vars(self) -> frozenset[StackVar]:
        return self.object.get_live_vars()


@dataclass(frozen=True)
class LParam(RParam):
    type: t.Type

    def get_type(self) -> t.Type:
        return self.type

    def rename_vars(self, renames: dict[str, str]) -> LParam:
        return self

    def replace_params(self, replacer: Callable[[RParam], RParam]) -> LParam:
        return langtools.cast(LParam, replacer(self))

    def to_c_store(self, type_cache: dict[t.Type, tuple[str, str]], value: str) ->str:
        return f"    {self.to_c(type_cache)} = {value};\n"


@dataclass(frozen=True)
class StackVar(LParam):
    name: str

    def rename_vars(self, renames: dict[str, str]) -> StackVar:
        return dataclasses.replace(self, name = renames.get(self.name, self.name))

    def to_c(self, type_cache: dict[t.Type, tuple[str, str]]) -> str:
        return mangle_name(self.name)

    def get_live_vars(self) -> frozenset[StackVar]:
        return frozenset({self})


@dataclass(frozen=True)
class GlobalVar(LParam):
    name: str   # Object globals resolve to a pointer

    def rename_vars(self, renames: dict[str, str]) -> GlobalVar:
        return self

    def to_c(self, type_cache: dict[t.Type, tuple[str, str]]) -> str:
        return mangle_name(self.name)


@dataclass(frozen=True)
class ObjectField(LParam):
    pointer: RParam
    object_name: str         # Which object type
    field: str               # Which named field
    index: RParam|None       # If 'field' is an array, this is required

    def rename_vars(self, renames: dict[str, str]) -> ObjectField:
        return dataclasses.replace(self, pointer = self.pointer.rename_vars(renames), index = self.index and self.index.rename_vars(renames))

    def to_c(self, type_cache: dict[t.Type, tuple[str, str]]) -> str:
        index = f"[{self.index.to_c(type_cache)}]" if self.index is not None else ""
        pointer = self.pointer.to_c(type_cache)
        return f"(({mangle_name(self.object_name)}_t*){pointer})->{mangle_name(self.field)}{index}"

    def replace_params(self, replacer: Callable[[RParam], RParam]) -> LParam:
        return langtools.cast(LParam, replacer(dataclasses.replace(self, pointer=self.pointer.replace_params(replacer), index=self.index and self.index.replace_params(replacer))))

    def to_c_store(self, type_cache: dict[t.Type, tuple[str, str]], value: str) ->str:
        index = f"[{self.index.to_c(type_cache)}]" if self.index is not None else ""
        tmp_ptr = self.pointer.to_c(type_cache)
        pointer = f"object_mutation({tmp_ptr})" if self.type.has_pointers else tmp_ptr
        return f"    (({mangle_name(self.object_name)}_t*){pointer})->{mangle_name(self.field)}{index} = {value};\n"

    def get_live_vars(self) -> frozenset[StackVar]:
        return self.pointer.get_live_vars() | (self.index.get_live_vars() if self.index else frozenset())
