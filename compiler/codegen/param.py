from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Callable

import langtools
from codegen.tools import mangle_name, to_pointer_mask
import codegen.typedecl as t


@dataclass(frozen=True)
class RParam:
    def flatten(self, is_reader:bool=True) -> list[RParam]:
        return [self]

    def test(self, predicate: Callable[[RParam], bool]) -> bool:
        return predicate(self)

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

    def flatten(self, is_reader:bool=True) -> list[RParam]:
        return [self] + [p for param in self.values for p in param.flatten()]

    def test(self, predicate: Callable[[RParam], bool]) -> bool:
        return predicate(self) or any(1 for v in self.values if v.test(predicate))

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

    def flatten(self, is_reader:bool=True) -> list[RParam]:
        return [self] + [p for name, param in self.values for p in param.flatten()]

    def test(self, predicate: Callable[[RParam], bool]) -> bool:
        return predicate(self) or any(1 for _, p in self.values if p.test(predicate))

    def get_type(self) -> t.Struct:
        return t.Struct(tuple((name, rparam.get_type()) for name, rparam in self.values))

    def rename_vars(self, renames: dict[str, str]) -> NewStruct:
        return dataclasses.replace(self, values = tuple((name, rparam.rename_vars(renames)) for name, rparam in self.values))

    def replace_params(self, replacer: Callable[[RParam], RParam]) -> RParam:
        return replacer(dataclasses.replace(self, values=tuple((xn, xp.replace_params(replacer)) for xn, xp in self.values)))

    def to_c(self, type_cache: dict[t.Type, tuple[str, str]]) -> str:
        xtype = self.get_type()
        type_name = xtype.declare(type_cache)
        if len(self.values) <= 2:
            fields = ", ".join(f".{t.mangle_name(name)} = {expr.to_c(type_cache)}" for name, expr in self.values)
            return f"({type_name}){{{fields}}}"
        fields = "".join(f"\n        .{t.mangle_name(name)} = {expr.to_c(type_cache)}," for name, expr in self.values)
        return f"({type_name}){{{fields}\n    }}"

    def get_live_vars(self) -> frozenset[StackVar]:
        return frozenset(y for xname, x in self.values for y in x.get_live_vars())

    def __add__(self, other: NewStruct) -> NewStruct:
        return NewStruct(self.values + other.values)


@dataclass(frozen=True)
class Invoke(RParam):
    function: str
    parameters: RParam
    type: t.Type

    def flatten(self, is_reader:bool=True) -> list[RParam]:
        return [self] + self.parameters.flatten()

    def test(self, predicate: Callable[[RParam], bool]) -> bool:
        return predicate(self) or self.parameters.test(predicate)

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

    def flatten(self, is_reader:bool=True) -> list[RParam]:
        return [self] + self.struct.flatten()

    def test(self, predicate: Callable[[RParam], bool]) -> bool:
        return predicate(self) or self.struct.test(predicate)

    def get_type(self) -> t.Type:
        xtype = self.struct.get_type()
        if isinstance(xtype, t.Struct):
            fields = xtype.fields
        elif isinstance(xtype, t.UnionContainer):
            fields = xtype.slots
        elif isinstance(xtype, t.TaskWrapper):
            fields = (("value", xtype.inner), ("task", t.DataPointer()))
        else:
            raise ValueError(f"StructField requires a Struct or UnionContainer, got {xtype}")
        result = next((ftype for name, ftype in fields if name == self.field), None)
        if result is None:
            raise ValueError(f"Field '{self.field}' not found")
        return result

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
class Float(RParam):
    value: float
    precision: int

    def get_type(self) -> t.Float:
        return t.Float(self.precision)

    def to_c(self, type_cache: dict[t.Type, tuple[str, str]]) -> str:
        return self.get_type().initialise(type_cache, self.value)


@dataclass(frozen=True)
class IntEqConst(RParam):
    """Emits `(value == const_val)` — used for $tag comparison in match arms."""
    value: RParam
    const_val: int

    def get_type(self) -> t.Int:
        return t.Int(32)

    def flatten(self, is_reader: bool = True) -> list[RParam]:
        return [self] + self.value.flatten()

    def test(self, predicate: Callable[[RParam], bool]) -> bool:
        return predicate(self) or self.value.test(predicate)

    def rename_vars(self, renames: dict[str, str]) -> RParam:
        return dataclasses.replace(self, value=self.value.rename_vars(renames))

    def replace_params(self, replacer: Callable[[RParam], RParam]) -> RParam:
        return replacer(dataclasses.replace(self, value=self.value.replace_params(replacer)))

    def get_live_vars(self) -> frozenset[StackVar]:
        return self.value.get_live_vars()

    def to_c(self, type_cache: dict[t.Type, tuple[str, str]]) -> str:
        return f"({self.value.to_c(type_cache)} == {self.const_val})"


@dataclass(frozen=True)
class NullPointer(RParam):
    """A null data pointer — used when boxing unit/None into a DataPointer union."""
    def get_type(self) -> t.DataPointer:
        return t.DataPointer()

    def to_c(self, type_cache: dict[t.Type, tuple[str, str]]) -> str:
        return "((object_t*)0)"


@dataclass(frozen=True)
class ObjVtableEq(RParam):
    """Emits `object_is_instance(p, target)` — libyafl's tag-aware "is-a"
    test that handles NULL, tagged integer/string pointers, exact vtable
    identity, and transitive matches against the vtable's implements_array.

    Exactly one of `class_name` or `extern_symbol` must be set:
      * `class_name` — the yafl class name (e.g. "System::IO::_IO@hash");
        the target is `obj_` + mangle_name(class_name), and the trim pass
        treats the class as live.
      * `extern_symbol` — a library-provided C symbol (e.g.
        "STRING_VTABLE", "INTEGER_VTABLE"); address-of is applied since
        these are declared as structs in libyafl."""
    value: RParam
    class_name: str | None = None
    extern_symbol: str | None = None

    def __post_init__(self):
        if (self.class_name is None) == (self.extern_symbol is None):
            raise ValueError("ObjVtableEq: exactly one of class_name / extern_symbol must be set")

    def get_type(self) -> t.Int:
        return t.Int(8)

    def flatten(self, is_reader: bool = True) -> list[RParam]:
        return [self] + self.value.flatten()

    def test(self, predicate: Callable[[RParam], bool]) -> bool:
        return predicate(self) or self.value.test(predicate)

    def rename_vars(self, renames: dict[str, str]) -> RParam:
        return dataclasses.replace(self, value=self.value.rename_vars(renames))

    def replace_params(self, replacer: Callable[[RParam], RParam]) -> RParam:
        return replacer(dataclasses.replace(self, value=self.value.replace_params(replacer)))

    def get_live_vars(self) -> frozenset[StackVar]:
        return self.value.get_live_vars()

    def to_c(self, type_cache: dict[t.Type, tuple[str, str]]) -> str:
        if self.class_name is not None:
            target = f"obj_{mangle_name(self.class_name)}"
        else:
            target = f"(vtable_t*)&{self.extern_symbol}"
        return f"object_is_instance({self.value.to_c(type_cache)}, {target})"


@dataclass(frozen=True)
class SyncWrap(RParam):
    """Wrap a synchronous return value in a TaskWrapper with task=NULL.

    Used on the sync return path of a hot-path function whose return type has
    been promoted to TaskWrapper(inner).  The caller checks .task != NULL to
    detect async; NULL means the result is in .value.
    """
    value: RParam
    wrapper_type: t.TaskWrapper

    def get_type(self) -> t.TaskWrapper:
        return self.wrapper_type

    def flatten(self, is_reader: bool = True) -> list[RParam]:
        return [self] + self.value.flatten(is_reader)

    def test(self, predicate) -> bool:
        return predicate(self) or self.value.test(predicate)

    def rename_vars(self, renames: dict[str, str]) -> SyncWrap:
        return dataclasses.replace(self, value=self.value.rename_vars(renames))

    def replace_params(self, replacer) -> RParam:
        return replacer(dataclasses.replace(self, value=self.value.replace_params(replacer)))

    def get_live_vars(self) -> frozenset[StackVar]:
        return self.value.get_live_vars()

    def to_c(self, type_cache: dict[t.Type, tuple[str, str]]) -> str:
        value_c = self.value.to_c(type_cache)
        type_name = self.wrapper_type.declare(type_cache)
        return f"(({type_name}){{.value={value_c},.task=((object_t*)0)}})"


@dataclass(frozen=True)
class ZeroOf(RParam):
    """Zero value of a specific type. Emits (TypeName){0} for struct/compound types.

    Use this instead of NewStruct when zero-initialising a field whose type must
    be preserved exactly — e.g. a Struct field in a state object where the field's
    C typedef must match the assignment target.
    """
    value_type: t.Type

    def get_type(self) -> t.Type:
        return self.value_type

    def to_c(self, type_cache: dict[t.Type, tuple[str, str]]) -> str:
        vt = self.value_type
        if isinstance(vt, (t.DataPointer, t.Str)) or (isinstance(vt, t.Int) and vt.precision == 0):
            return "((object_t*)0)"
        if isinstance(vt, t.Int):
            return "0"
        if isinstance(vt, t.FuncPointer):
            return "((fun_t){0})"
        type_name = vt.declare(type_cache)
        # Empty struct: {0} is technically "excess initializers"; use {} instead.
        init = "{}" if isinstance(vt, t.Struct) and not vt.fields else "{0}"
        return f"(({type_name}){init})"


@dataclass(frozen=True)
class NewStructTyped(RParam):
    """Compound literal with an explicit type — required when the inferred type of the values
    would differ from the intended container type (e.g. a DataPointer value stored in a Str slot).

    Always constructed via union_struct(), which zero-fills every unspecified slot so all
    pointer slots are null-initialised for GC safety.
    """
    struct_type: t.UnionContainer
    values: tuple[tuple[str, RParam], ...]

    def __post_init__(self):
        expected = {name for name, _ in self.struct_type.slots}
        provided = {name for name, _ in self.values}
        assert expected == provided, \
            f"NewStructTyped: missing slots {expected - provided}, unexpected {provided - expected}"

    def get_type(self) -> t.Type:
        return self.struct_type

    def flatten(self, is_reader: bool = True) -> list[RParam]:
        return [self] + [p for _, v in self.values for p in v.flatten()]

    def test(self, predicate: Callable[[RParam], bool]) -> bool:
        return predicate(self) or any(v.test(predicate) for _, v in self.values)

    def rename_vars(self, renames: dict[str, str]) -> RParam:
        return dataclasses.replace(self, values=tuple((n, v.rename_vars(renames)) for n, v in self.values))

    def replace_params(self, replacer: Callable[[RParam], RParam]) -> RParam:
        return replacer(dataclasses.replace(self, values=tuple((n, v.replace_params(replacer)) for n, v in self.values)))

    def get_live_vars(self) -> frozenset[StackVar]:
        return frozenset(lv for _, v in self.values for lv in v.get_live_vars())

    def to_c(self, type_cache: dict[t.Type, tuple[str, str]]) -> str:
        type_name = self.struct_type.declare(type_cache)
        if len(self.values) <= 2:
            fields = ", ".join(f".{t.mangle_name(name)} = {v.to_c(type_cache)}" for name, v in self.values)
            return f"({type_name}){{{fields}}}"
        fields = "".join(f"\n        .{t.mangle_name(name)} = {v.to_c(type_cache)}," for name, v in self.values)
        return f"({type_name}){{{fields}\n    }}"


def _zero_for(field_type: t.Type) -> RParam:
    """Return a zero-valued RParam for the given primitive slot type."""
    if isinstance(field_type, (t.DataPointer, t.Str)) or (isinstance(field_type, t.Int) and field_type.precision == 0):
        return NullPointer()
    if isinstance(field_type, t.Int):
        return Integer(0, field_type.precision)
    if isinstance(field_type, t.IntPtr):
        return Integer(0, 64)
    if isinstance(field_type, t.Float):
        return Float(0.0, field_type.precision)
    raise ValueError(f"No zero value defined for slot type {field_type}")


def union_struct(container: t.UnionContainer, named_values: dict[str, RParam]) -> NewStructTyped:
    """Build an exhaustive NewStructTyped for a UnionContainer, zero-filling any unspecified slots."""
    return NewStructTyped(container, tuple(
        (name, named_values.get(name, _zero_for(slot_type)))
        for name, slot_type in container.slots
    ))


@dataclass(frozen=True)
class TagTask(RParam):
    """Returns the correct 'this is actually a task' value for a given return type.

    For pointer types:    (RetType)((uintptr_t)task | PTR_TAG_TASK)
    For TaskWrapper:      (WrapperType){ .value = <zero>, .task = task }
    For struct-with-ptr:  (StructType){ .first_ptr = tagged_task, other=0... }
    """
    task: RParam
    target_type: t.Type

    def get_type(self) -> t.Type:
        return self.target_type

    def flatten(self, is_reader: bool = True) -> list[RParam]:
        return [self] + self.task.flatten()

    def test(self, predicate: Callable[[RParam], bool]) -> bool:
        return predicate(self) or self.task.test(predicate)

    def rename_vars(self, renames: dict[str, str]) -> TagTask:
        return dataclasses.replace(self, task=self.task.rename_vars(renames))

    def replace_params(self, replacer: Callable[[RParam], RParam]) -> RParam:
        return replacer(dataclasses.replace(self, task=self.task.replace_params(replacer)))

    def get_live_vars(self) -> frozenset[StackVar]:
        return self.task.get_live_vars()

    def to_c(self, type_cache: dict[t.Type, tuple[str, str]]) -> str:
        task_c = self.task.to_c(type_cache)
        typ = self.target_type
        if isinstance(typ, (t.DataPointer, t.Str)) or (isinstance(typ, t.Int) and typ.precision == 0):
            return f"((object_t*)((uintptr_t){task_c} | PTR_TAG_TASK))"
        if isinstance(typ, t.FuncPointer):
            return f"((fun_t){{.f=NULL,.o=(void*)((uintptr_t){task_c} | PTR_TAG_TASK)}})"
        if isinstance(typ, t.TaskWrapper):
            inner_zero = ZeroOf(typ.inner).to_c(type_cache)
            type_name = typ.declare(type_cache)
            return f"(({type_name}){{.value={inner_zero},.task={task_c}}})"
        if isinstance(typ, t.Struct):
            fname = t.first_pointer_field(typ)
            if fname is None:
                raise ValueError(f"TagTask: struct {typ} has no pointer field")
            type_name = typ.declare(type_cache)
            fields = ", ".join(
                f".{mangle_name(n)} = (object_t*)((uintptr_t){task_c} | PTR_TAG_TASK)" if n == fname
                else f".{mangle_name(n)} = 0"
                for n, _ in typ.fields
            )
            return f"(({type_name}){{{fields}}})"
        raise ValueError(f"TagTask: unsupported target type {typ}")


@dataclass(frozen=True)
class GlobalFunction(RParam):
    name: str
    object: RParam|None = None
    external: bool = False
    c_symbol: str | None = None
    impure: bool = False
    sync: bool = False

    def __post_init__(self):
        if not isinstance(self.name, str):
            raise ValueError()

    def flatten(self, is_reader:bool=True) -> list[RParam]:
        return [self] + (self.object.flatten() if self.object else [])

    def test(self, predicate: Callable[[RParam], bool]) -> bool:
        return predicate(self) or (self.object and self.object.test(predicate))

    def get_type(self) -> t.FuncPointer:
        return t.FuncPointer()

    def rename_vars(self, renames: dict[str, str]) -> GlobalFunction:
        return dataclasses.replace(self, object = self.object and self.object.rename_vars(renames))

    def replace_params(self, replacer: Callable[[RParam], RParam]) -> RParam:
        return replacer(dataclasses.replace(self, object=self.object and self.object.replace_params(replacer)))

    def to_c(self, type_cache: dict[t.Type, tuple[str, str]]) -> str:
        f_ref = self.c_symbol if self.c_symbol else mangle_name(self.name)
        return f"((fun_t){{.f={f_ref},.o={self.object.to_c(type_cache) if self.object else 'NULL'}}})"

    def get_live_vars(self) -> frozenset[StackVar]:
        return self.object.get_live_vars() if self.object else set()


@dataclass(frozen=True)
class VirtualFunction(RParam):
    name: str
    object: RParam
    fast_lookup: bool = False

    def flatten(self, is_reader:bool=True) -> list[RParam]:
        return [self] + self.object.flatten()

    def test(self, predicate: Callable[[RParam], bool]) -> bool:
        return predicate(self) or self.object.test(predicate)

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
class PointerTo(RParam):
    value: LParam

    def flatten(self, is_reader:bool=True) -> list[RParam]:
        return [self] + self.value.flatten()

    def test(self, predicate: Callable[[RParam], bool]) -> bool:
        return predicate(self) or self.value.test(predicate)

    def get_type(self) -> t.DataPointer:
        return t.DataPointer()

    def rename_vars(self, renames: dict[str, str]) -> PointerTo:
        return dataclasses.replace(self, value = self.value.rename_vars(renames))

    def replace_params(self, replacer: Callable[[RParam], RParam]) -> RParam:
        return replacer(dataclasses.replace(self, value=self.value.replace_params(replacer)))

    def to_c(self, type_cache: dict[t.Type, tuple[str, str]]) -> str:
        return f"(object_t*)&{self.value.to_c(type_cache)}"

    def get_live_vars(self) -> frozenset[StackVar]:
        return self.value.get_live_vars()


@dataclass(frozen=True)
class LParam(RParam):
    type: t.Type

    def flatten(self, is_reader:bool=True) -> list[RParam]:
        return [self] if is_reader else []

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

    def flatten(self, is_reader:bool=True) -> list[RParam]:
        return ([self] if is_reader else []) + self.pointer.flatten() + (self.index.flatten() if self.index else [])

    def test(self, predicate: Callable[[RParam], bool]) -> bool:
        return predicate(self) or self.pointer.test(predicate) or (self.index and self.index.test(predicate))

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
        pointer = self.pointer.to_c(type_cache)
        field_ref = f"(({mangle_name(self.object_name)}_t*){pointer})->{mangle_name(self.field)}{index}"
        if self.type.has_pointers:
            mask = to_pointer_mask(self.type, self.type.declare(type_cache))
            return f"    GC_WRITE_BARRIER({field_ref}, {mask});\n    {field_ref} = {value};\n"
        else:
            return f"    {field_ref} = {value};\n"



    def get_live_vars(self) -> frozenset[StackVar]:
        return self.pointer.get_live_vars() | (self.index.get_live_vars() if self.index else frozenset())
