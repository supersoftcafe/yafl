from __future__ import annotations

import dataclasses
from typing import Optional, Callable, List, Dict, Any, Tuple, Union
from dataclasses import dataclass, field
from codegen.tools import mangle_name

from codegen.ops import Op, Jump, JumpIf, Return, Label

import codegen.typedecl as t
import codegen.param as p


@dataclass(frozen=True)
class Function:
    name: str
    params: t.Struct            # First parameter must be DataPointer and must be named 'this'
    result: t.Type
    stack_vars: t.Struct
    ops: tuple[Op, ...]
    comment: str = ""

    def __post_init__(self):
        if len(self.params.fields) == 0:
            raise ValueError("Functions require a first parameter")
        name, field_type = self.params.fields[0]
        if not isinstance(field_type, t.DataPointer):
            raise ValueError("First parameter to a function must be a DataPointer")

    def __declare_vars(self, type_cache: dict[t.Type, tuple[str, str]], sep: str, p: t.Struct, end: str) -> str:
        return sep.join(f'{ptype.declare(type_cache)} {mangle_name(pname)}{end}' for pname, ptype in p.fields)

    def __prototype(self, type_cache: dict[t.Type, tuple[str, str]]) -> str:
        return (f"static NOINLINE\n"
                f"{self.result.declare(type_cache)} {mangle_name(self.name)}("
                f"{self.__declare_vars(type_cache, ', ', self.params, '')}"
                f")")

    @property
    def comment_line(self):
        return f"// {self.comment}\n" if self.comment else ""

    def to_c_prototype(self, type_cache: dict[t.Type, tuple[str, str]]) -> str:
        return f"{self.comment_line}{self.__prototype(type_cache)};\n"

    def to_c_implement(self, type_cache: dict[t.Type, tuple[str, str]]) -> str:
        return (f"{self.comment_line}{self.__prototype(type_cache)}\n"
                f"{{\n"
                f"    /* Begin local variables */\n"
                f"    {self.__declare_vars(type_cache, '    ', self.stack_vars, ';\n')}\n"
                f"    /* Begin operations */\n"
                f"{''.join(op.to_c(type_cache) for op in self.ops)}"
                f"}}\n")

    def replace_params(self, replacer: Callable[[p.RParam], p.RParam]) -> Function:
        return dataclasses.replace(self, ops=tuple(op.replace_params(replacer) for op in self.ops))

    def strip_unused_operations(self) -> Function:
        labels: dict[str, int] = {op.name: index for index, op in enumerate(self.ops) if isinstance(op, Label)}
        seen_indexes: set[int] = set()
        to_see_indexes: set[int] = {0}
        while to_see_indexes:
            seen_indexes.update(to_see_indexes)
            to_see = to_see_indexes
            to_see_indexes = set()
            for index in to_see:
                op = self.ops[index]
                if isinstance(op, Jump):
                    to_see_indexes.add(labels[op.name])
                elif isinstance(op, JumpIf):
                    to_see_indexes.add(labels[op.label])
                    if index+1 < len(self.ops):
                        to_see_indexes.add(index+1)
                elif isinstance(op, Return):
                    pass
                else:
                    if index+1 < len(self.ops):
                        to_see_indexes.add(index+1)
        ops = tuple(op for index, op in enumerate(self.ops) if index in seen_indexes)
        return dataclasses.replace(self, ops=ops)


@dataclass(frozen=True)
class Object:
    name: str
    extends: tuple[str, ...]                # Full list of everything from which this inherits, all the way up to root
    functions: tuple[tuple[str, str], ...]  # Virtual name to global name lookup including inherited members
    fields: t.ImmediateStruct               # All fields of this and parent objects in the correct order
    length_field: str|None = None           # Name of field that is the Int(32) length
    comment: str = ""

    def __post_init__(self):
        if not isinstance(self.fields, t.ImmediateStruct):
            raise ValueError("Fields parameter must be ImmediateStruct")
        if len(self.fields.fields) == 0:
            raise ValueError("Object cannot have empty fields array")
        else:
            name, field_type = self.fields.fields[0]
            if name != "type":
                raise ValueError("The first field of an object must be named 'type'")
            if not isinstance(field_type, t.DataPointer):
                raise ValueError("The first field of an object must be DataPointer")
            if any(1 for name, field_type in self.fields.fields[:-1] if isinstance(field_type, t.Array)):
                raise ValueError("An object may only have one array field and it must come last")
            name, field_type = self.fields.fields[-1]
            if isinstance(field_type, t.Array):
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
    def array_type(self) -> t.Type|None:
        f = self.fields.fields
        if len(f) > 0:
            f = f[-1][1]
            if isinstance(f, t.Array):
                return f.type
        return None

    def __to_pointer_mask(self, field_type: t.Type, type_str: str) -> str:
        mask = "".join(f"|maskof({type_str}, {path})" for path in field_type.get_pointer_paths(""))
        return f"(0{mask})"

    @property
    def comment_line(self):
        return f"// {self.comment}\n" if self.comment else ""

    def get_pointer_mask(self, type_cache: dict[t.Type, tuple[str, str]]) -> str:
        # Trim vtable reference and array field if it exists
        f = self.fields.fields[1:-1] if self.array_type else self.fields.fields[1:]
        return self.__to_pointer_mask(t.Struct(f), f"{mangle_name(self.name)}_t")

    def get_array_pointer_mask(self, type_cache: dict[t.Type, tuple[str, str]]) -> str:
        array_type = self.array_type
        if not array_type: return "0"
        return self.__to_pointer_mask(array_type, array_type.declare(type_cache))

    def get_object_size(self, type_cache: dict[t.Type, tuple[str, str]]) -> str:
        type_str = f"{mangle_name(self.name)}_t"
        return f"offsetof({type_str}, {self.fields.fields[-1][0]})" if self.array_type else f"sizeof({type_str})"

    def get_array_el_size(self, type_cache: dict[t.Type, tuple[str, str]]) -> str:
        a = self.array_type
        return f"sizeof({a.declare(type_cache)})" if a else "0"

    def get_array_length_offset(self, type_cache: dict[t.Type, tuple[str, str]]) -> str:
        l = self.length_field
        if l is not None:
            return f"offsetof({mangle_name(self.name)}_t, {l})"
        return "0"


@dataclass(frozen=True)
class Global:
    name: str
    type: t.Type
    init: p.RParam|None = None    # How to initialise it. If DataPointer, this is NewStruct
    object_name: str|None = None  # Which object type
    lazy_init_function: str|None = None # If initialisation is more complex, the function that will do it
    lazy_init_flag: str|None = None

    def to_c_name(self) -> str:
        return mangle_name(self.name)

    def __prototype(self, type_cache: dict[t.Type, tuple[str, str]]) -> str:
        if self.object_name and self.init:
            if not isinstance(self.init, p.NewStruct):
                raise ValueError("init must be NewStruct")
            last_element = self.init.values[-1]
            if isinstance(last_element, p.InitArray):
                return (f"static struct {{\n"
                        + "".join(f"    {value.get_type().declare(type_cache)} {name};\n" for name, value in self.init.values) +
                        f"}}[1] {self.to_c_name()}")
            return f"static {mangle_name(self.object_name)}_t[1] {self.to_c_name()}"
        return f"static {self.type.declare(type_cache)} {self.to_c_name()}"

    def to_c_prototype(self, type_cache: dict[t.Type, tuple[str, str]]) -> str:
        return f"{self.__prototype(type_cache)};\n"

    def to_c_implement(self, type_cache: dict[t.Type, tuple[str, str]]) -> str:
        if not self.init:
            return ""
        if self.object_name:
            if not isinstance(self.init, p.NewStruct):
                raise ValueError("init must be NewStruct")
            return (f"{self.__prototype(type_cache)} = {{\n"
             f"    (const vtable_t const *)&obj_{self.to_c_name()}\n"
             + "".join(f"  , {value.to_c(type_cache)}\n" for name, value in self.init.values) +
             f"}};\n")
        else:
            return f"{self.__prototype(type_cache)} = {self.init.to_c(type_cache)};"

