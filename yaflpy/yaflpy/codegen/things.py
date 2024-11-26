from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property
from random import random
from typing import Optional, Callable, List, Dict, OrderedDict, Any, Tuple, Union
from collections import defaultdict
from codegen.tools import mangle_name

from codegen.typedecl import Type, Struct, DataPointer, Array, Int
from codegen.ops import Op


@dataclass(frozen=True)
class Function:
    name: str
    params: Struct            # First parameter must be DataPointer and must be named 'this'
    result: Type
    stack_vars: Struct
    ops: Tuple[Op, ...]
    use_continuation_passing_style: bool = False

    def __post_init__(self):
        if len(self.params.fields) == 0:
            raise ValueError("Functions require a first parameter")
        name, field_type = self.params.fields[0]
        if not isinstance(field_type, DataPointer):
            raise ValueError("First parameter to a function must be a DataPointer")

    def declare_vars(self, type_cache: Dict[Type, (str, str)], sep: str, p: Struct, end: str) -> str:
        return sep.join(f'{ptype.declare(type_cache)} {mangle_name(pname)}{end}' for pname, ptype in p.fields)

    def prototype(self, type_cache: Dict[Type, (str, str)]) -> str:
        return (f"static __attribute__((noinline))\n"
                f"{self.result.declare(type_cache)} {mangle_name(self.name)}("
                f"{self.declare_vars(type_cache, ', ', self.params, '')}"
                f")")

    def to_c_prototype(self, type_cache: Dict[Type, (str, str)]) -> str:
        return f"{self.prototype(type_cache)};\n"

    def to_c_implement(self, type_cache: Dict[Type, (str, str)]) -> str:
        return (f"{self.prototype(type_cache)}\n"
                f"{{\n"
                f"    /* Begin local variables */\n"
                f"    {self.declare_vars(type_cache, '    ', self.stack_vars, ';\n')}\n"
                f"    /* Begin operations */\n"
                f"{''.join(op.to_c(type_cache) for op in self.ops)}"
                f"}}\n")


@dataclass(frozen=True)
class Object:
    name: str
    extends: Tuple[str, ...]                # Full list of everything from which this inherits, all the way up to root
    functions: Tuple[Tuple[str, str], ...]  # Virtual name to global name lookup including inherited members
    fields: Struct                          # All fields of this and parent objects in the correct order
    length_field: Optional[str] = None      # Name of field that is the Int(32) length

    def __post_init__(self):
        if len(self.fields.fields) == 0:
            raise ValueError("Object cannot have empty fields array")
        else:
            name, field_type = self.fields.fields[0]
            if name != "type":
                raise ValueError("The first field of an object must be named 'type'")
            if not isinstance(field_type, DataPointer):
                raise ValueError("The first field of an object must be DataPointer")
            if any(1 for name, field_type in self.fields.fields[:-1] if isinstance(field_type, Array)):
                raise ValueError("An object may only have one array field and it must come last")
            name, field_type = self.fields.fields[-1]
            if isinstance(field_type, Array):
                if field_type.length > 0:
                    raise ValueError("The final array field must have length 0")
                if name != "array":
                    raise ValueError("The final array field must be named 'array'")
        if self.length_field is not None:
            if self.array_type is None:
                raise ValueError("Length field requires that there is an array field")
            if not any(1 for name, field_type in self.fields.fields if name == self.length_field):
                raise ValueError("Length field does not exist")
        if self.array_type is not None:
            if self.length_field is None:
                raise ValueError("Array field requires that there is a length field")

    @property
    def array_type(self) -> Optional[Type]:
        f = self.fields.fields
        if len(f) > 0:
            f = f[-1][1]
            if isinstance(f, Array):
                return f.type
        return None

    def __to_pointer_mask(self, field_type: Type, type_str: str) -> str:
        mask = "".join(f"|maskof({type_str}, {path})" for path in field_type.get_pointer_paths(""))
        return f"(0{mask})"

    def get_pointer_mask(self, type_cache: Dict[Type, (str, str)]) -> str:
        f = self.fields.fields
        f = f[1:-1] if self.length_field else f[1:]
        return self.__to_pointer_mask(Struct(f), self.fields.declare(type_cache))

    def get_array_pointer_mask(self, type_cache: Dict[Type, (str, str)]) -> str:
        array_type = self.array_type
        if not array_type: return "0"
        return self.__to_pointer_mask(array_type, array_type.declare(type_cache))

    def get_object_size(self, type_cache: Dict[Type, (str, str)]) -> str:
        f = self.fields
        type_str = f.declare(type_cache)
        return f"offsetof({type_str}, {f.fields[-1][0]})" if self.length_field else f"sizeof({type_str})"

    def get_array_el_size(self, type_cache: Dict[Type, (str, str)]) -> str:
        a = self.array_type
        return f"sizeof({a.declare(type_cache)})" if a else "0"

    def get_array_length_offset(self, type_cache: Dict[Type, (str, str)]) -> str:
        l = self.length_field
        if l is not None:
            return f"offsetof({self.fields.declare(type_cache)}, {l})"
        return "0"


@dataclass(frozen=True)
class Global:
    name: str
    type: Type
