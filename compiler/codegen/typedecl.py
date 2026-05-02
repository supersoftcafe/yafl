from __future__ import annotations

from itertools import groupby
from itertools import chain
from collections.abc import Mapping
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Any
from codegen.tools import mangle_name

# word_size = 8
max_int = (1 << 31) - 1
min_int = 0 - max_int - 1
mask_int = (1 << 32) - 1


@dataclass(frozen=True)
class Type(ABC):
    # @property
    # @abstractmethod
    # def size(self) -> int:
    #     pass

    @property
    def has_pointers(self) -> bool:
        return False

    @property
    def _dont_cache(self) -> bool:
        return False

    # @property
    # def alignment(self) -> int:
    #     return self.size

    # def offsetof(self, *args) -> int:
    #     if args:
    #         raise ValueError()
    #     return 0

    def _initialise(self, type_cache: dict[Type, tuple[str, str]], data: Any, field_indent: str) -> str:
        return f"{data}"

    def _declare_struct(self, type_cache: dict[Type, tuple[str, str]], field_indent: str) -> str:
        raise NotImplementedError()

    def _declare(self, type_cache: dict[Type, tuple[str, str]], field_indent: str) -> str:
        if self._dont_cache:
            declaration = self._declare_struct(type_cache, "    ")
        elif self not in type_cache:
            type_str = f"typedef {self._declare_struct(type_cache, "    ")}"
            declaration = f"struct_anon_{len(type_cache)}_t"
            type_cache[self] = declaration, f"{type_str} {declaration};\n"
        else:
            value = type_cache[self]
            declaration, _ = value
        return declaration

    def initialise(self, type_cache: dict[Type, tuple[str, str]], data: Any) -> str:
        return self._initialise(type_cache, data, "    ")

    def declare(self, type_cache: dict[Type, tuple[str, str]]) -> str:
        return self._declare(type_cache, "    ")

    def get_pointer_paths(self, path: str) -> list[str]:
        return []

# Escape table for emitting YAFL string literals into C source. Control
# bytes and high-bit bytes go to \xHH hex escapes; backslash and double-
# quote must be backslash-escaped or the surrounding C "..." breaks.
_str_escape_table = str.maketrans({
    **{f'{chr(c)}': f'\\x{c:02x}' for c in chain(range(0, 32), range(128, 256))},
    '\\': '\\\\',
    '"':  '\\"',
})

@dataclass(frozen=True)
class Str(Type):
    # @property
    # def size(self) -> int:
    #     return word_size

    def _initialise(self, type_cache: dict[Type, tuple[str, str]], data: Any, field_indent: str) -> str:
        if not isinstance(data, str):
            raise ValueError("data must be of type str")
        return f"STR(\"{data.translate(_str_escape_table)}\")"

    def _declare(self, type_cache: dict[Type, tuple[str, str]], field_indent: str) -> str:
        return "object_t*"

    def get_pointer_paths(self, path: str) -> list[str]:
        return [path]

@dataclass(frozen=True)
class Int(Type):
    precision: int = 0 # Bit precision

    # @property
    # def size(self) -> int:
    #     return self.precision // 8 if self.precision != 0 else word_size

    def _initialise(self, type_cache: dict[Type, tuple[str, str]], data: Any, field_indent: str) -> str:
        if not isinstance(data, int):
            raise ValueError()
        if self.precision != 0:
            return f"((int{self.precision}_t){data})"

        sign = 0
        if data < 0:
            sign = -1
            data = -data

        array: list[int] = []
        while data != 0:
            array.append(data & mask_int)
            data = data >> 32

        if not array:
            return f"INTEGER_LITERAL_1(0, 0)"
        elif len(array) == 1:
            return f"INTEGER_LITERAL_1({sign}, {array[0]})"
        elif len(array) == 2:
            return f"INTEGER_LITERAL_2({sign}, {array[0]}, {array[1]})"
        else:
            groups = [[x for _, x in group] for _, group in groupby(enumerate(array), key=lambda x: x[0] // 2)]
            values = [(f"INTEGER_LITERAL_N_1({x[0]})" if len(x) == 1 else f"INTEGER_LITERAL_N_2({x[0]}, {x[1]})") for x in groups]
            return f"INTEGER_LITERAL_N({sign}, {len(array)}, {' INTEGER_LITERAL_SEP '.join(values)})"

    def _declare(self, type_cache: dict[Type, tuple[str, str]], field_indent: str) -> str:
        return f"int{self.precision}_t" if self.precision != 0 else "object_t*"

    def get_pointer_paths(self, path: str) -> list[str]:
        return [path] if self.precision == 0 else []


@dataclass(frozen=True)
class Float(Type):
    precision: int  # 32 or 64

    def _initialise(self, type_cache: dict[Type, tuple[str, str]], data: Any, field_indent: str) -> str:
        if not isinstance(data, (int, float)):
            raise ValueError("Float literal must be int or float")
        if self.precision == 32:
            return f"((float){float(data)!r}f)"
        return f"((double){float(data)!r})"

    def _declare(self, type_cache: dict[Type, tuple[str, str]], field_indent: str) -> str:
        if self.precision == 32:
            return "float"
        if self.precision == 64:
            return "double"
        raise ValueError(f"Float precision must be 32 or 64, got {self.precision}")

    def get_pointer_paths(self, path: str) -> list[str]:
        return []


@dataclass(frozen=True)
class IntPtr(Type):
    # @property
    # def size(self) -> int:
    #     return word_size

    def _initialise(self, type_cache: dict[Type, tuple[str, str]], data: Any, field_indent: str) -> str:
        return f"{data}"

    def _declare(self, type_cache: dict[Type, tuple[str, str]], field_indent: str) -> str:
        return "intptr_t"


@dataclass(frozen=True)
class DataPointer(Type):
    # @property
    # def size(self) -> int:
    #     return word_size

    @property
    def has_pointers(self) -> bool:
        return True

    def _declare(self, type_cache: dict[Type, tuple[str, str]], field_indent: str) -> str:
        return "object_t*"

    def get_pointer_paths(self, path: str) -> list[str]:
        return [path]


@dataclass(frozen=True)
class FuncPointer(Type):
    # @property
    # def size(self) -> int:
    #     return word_size * 2

    @property
    def has_pointers(self) -> bool:
        return True

    # @property
    # def alignment(self) -> int:
    #     return word_size

    # def offsetof(self, *args):
    #     match args:
    #         case [0] | []:
    #             return 0
    #         case [1]:
    #             return word_size
    #         case _:
    #             raise ValueError()

    def _initialise(self, type_cache: dict[Type, tuple[str, str]], data: Any, field_indent: str) -> str:
        fun, obj = (data['f'], data['o'] or "NULL") if isinstance(data, Mapping) else (str(data), "NULL")
        return f"(fun_t){{ .f = {fun}, .o = {obj} }}"

    def _declare(self, type_cache: dict[Type, tuple[str, str]], field_indent: str) -> str:
        return "fun_t"

    def get_pointer_paths(self, path: str) -> list[str]:
        return [f"{path}.o"]


@dataclass(frozen=True)
class Struct(Type):
    fields: Tuple[Tuple[str, Type], ...]

    @property
    def _dont_cache(self) -> bool:
        return False

    # @property
    # def size(self) -> int:
    #     sz, al = 0, 0
    #     for name, field_type in self.fields:
    #         a = field_type.alignment
    #         sz = (sz + a - 1) // a * a + field_type.size # Bring up to alignment requirement and then add size
    #         al = max(al, a)
    #     return (sz + al - 1) // al * al if al else 0 # Round up to alignment size

    @property
    def has_pointers(self) -> bool:
        return any(1 for x, y in self.fields if y.has_pointers)

    # @property
    # def alignment(self) -> int:
    #     return max(field_type.alignment for name, field_type in self.fields)

    # def offsetof(self, *args):
    #     match args:
    #         case [index, *rest]:
    #             if isinstance(index, str):
    #                 index = next((i for i, x in enumerate(self.fields) if x[0] == str), -1)
    #             last = self.fields[index][1]
    #             return Struct(self.fields[:index+1]).size - last.size + last.offsetof(*rest)
    #         case _:
    #             raise ValueError()

    def _initialise(self, type_cache: dict[Type, tuple[str, str]], data: Any, field_indent: str) -> str:
        all_names = [name for name, type in self.fields]
        missing_names = [name for name, value in data.items() if name not in all_names]
        if any(missing_names):
            raise ValueError(f"Fields {missing_names} are not present in the struct for initialisation")
        new_indent = field_indent + "    "
        strings = ",".join(f"\n{new_indent}.{mangle_name(name)} = {field_type._initialise(type_cache, data[name], new_indent)}" for name, field_type in self.fields if name in data)
        return f"{{ {strings} \n{field_indent}}}"

    def _declare_struct(self, type_cache: dict[Type, tuple[str, str]], field_indent: str) -> str:
        new_indent = field_indent + "    "
        return f"struct {{ {"".join(f"\n{field_indent}{field_type._declare(type_cache, new_indent)} {mangle_name(name)};" for name, field_type in self.fields)}\n{field_indent[:-4]}}}"

    def __add__(self, other: Struct) -> Struct:
        return Struct(self.fields + other.fields)

    def get_pointer_paths(self, path: str) -> List[str]:
        return [pointer_path for name, field_type in self.fields for pointer_path in
                field_type.get_pointer_paths(f"{path}.{mangle_name(name)}")]




@dataclass(frozen=True)
class Void(Type):
    # @property
    # def size(self) -> int:
    #     return 0

    @property
    def has_pointers(self) -> bool:
        return False

    def _declare(self, type_cache: dict[Type, tuple[str, str]], field_indent: str) -> str:
        return "void"

    def get_pointer_paths(self, path: str) -> list[str]:
        return []


@dataclass(frozen=True)
class ImmediateStruct(Struct):
    @property
    def _dont_cache(self) -> bool:
        return True


@dataclass(frozen=True)
class Array(Type):
    type: Type
    length: int

    # @property
    # def size(self) -> int:
    #     return self.type.size * self.length

    @property
    def has_pointers(self) -> bool:
        return self.type.has_pointers

    # @property
    # def alignment(self) -> int:
    #     return self.type.alignment

    # def offsetof(self, *args):
    #     match args:
    #         case [index, *rest]:
    #             return self.type.size * index + self.type.offsetof(*rest)
    #         case _:
    #             raise ValueError()

    def _initialise(self, type_cache: dict[Type, tuple[str, str]], data: Any, field_indent: str) -> str:
        new_indent = field_indent + "    "
        strings = ",".join(f"\n{field_indent}.a[{index}] = {self.type._initialise(type_cache, item, new_indent)}" for index, item in enumerate(data))
        return f"{{ {strings} \n{field_indent[:-4]}}}"

    def _declare(self, type_cache: dict[Type, tuple[str, str]], field_indent: str) -> str:
        new_indent = field_indent + "    "
        return f"struct {{\n{field_indent}{self.type._declare(type_cache, new_indent)} a[{self.length}];\n{field_indent[:-4]}}}"

    def get_pointer_paths(self, path: str) -> List[str]:
        return [pointer_path for index in range(self.length) for pointer_path in
                self.type.get_pointer_paths(f"{path}.a[{index}]")]


@dataclass(frozen=True)
class TaskWrapper(Type):
    """Wraps a non-pointer primitive return type in a struct so it can carry a task signal.

    Emits: struct { <inner> value; object_t* task; }
    task == NULL means a real value; task != NULL means the result is a pending task.
    """
    inner: Type

    @property
    def has_pointers(self) -> bool:
        return True  # the task field is a GC pointer

    def _declare_struct(self, type_cache: dict[Type, tuple[str, str]], field_indent: str) -> str:
        inner_decl = self.inner._declare(type_cache, field_indent)
        return f"struct {{\n{field_indent}{inner_decl} value;\n{field_indent}object_t* task;\n{field_indent[:-4]}}}"

    def get_pointer_paths(self, path: str) -> list[str]:
        return [f"{path}.task"]


def first_pointer_field(t: Type) -> str | None:
    """Return the name of the first pointer-typed field in a Struct type, or None.

    Pointer-typed means: DataPointer, Str, or Int(precision=0) (bigint = object_t*).
    """
    if not isinstance(t, Struct):
        return None
    for name, ft in t.fields:
        if isinstance(ft, (DataPointer, Str)) or (isinstance(ft, Int) and ft.precision == 0):
            return name
    return None


def is_task_check(expr: str, t: Type) -> str:
    """Return a C expression (truthy when result is a task) for the given return type."""
    if isinstance(t, (DataPointer, Str)):
        return f"PTR_IS_TASK({expr})"
    if isinstance(t, FuncPointer):
        return f"PTR_IS_TASK(({expr}).o)"
    if isinstance(t, TaskWrapper):
        return f"({expr}).task"
    if isinstance(t, Struct):
        fname = first_pointer_field(t)
        if fname is not None:
            return f"PTR_IS_TASK(({expr}).{mangle_name(fname)})"
    raise ValueError(f"Cannot generate is_task_check for type {t}")


def _flatten_primitives(t: Type) -> list[Type]:
    """Recursively decompose a type into its primitive slot types."""
    if isinstance(t, Struct):
        return [p for _, ft in t.fields for p in _flatten_primitives(ft)]  # unit → []
    if isinstance(t, FuncPointer):
        return [IntPtr(), DataPointer()]  # f=code pointer (non-GC), o=data pointer (GC)
    if isinstance(t, UnionContainer):
        return [slot_t for _, slot_t in t.slots]
    return [t]  # Int, Str, DataPointer, IntPtr — already primitive


def _primitive_rank(t: Type) -> int:
    """Lower rank = stored first in the slot struct."""
    if isinstance(t, Int) and t.precision == 64: return 0   # Int64 (8 bytes)
    if isinstance(t, Float) and t.precision == 64: return 0 # Float64 (8 bytes)
    if isinstance(t, (DataPointer, Str)): return 1           # GC pointer
    if isinstance(t, Int) and t.precision == 0: return 1    # bigint = GC pointer
    if isinstance(t, IntPtr): return 2                       # non-GC pointer-sized
    if isinstance(t, Int) and t.precision == 32: return 3   # Int32
    if isinstance(t, Float) and t.precision == 32: return 3 # Float32
    if isinstance(t, Int) and t.precision == 16: return 4   # Int16
    if isinstance(t, Int) and t.precision == 8: return 5    # Int8/Bool
    return 6


def _can_merge_into(small: Type, large: Type) -> bool:
    """True if a fixed-width small integer can be stored in a fixed-width larger integer slot."""
    return (isinstance(small, Int) and isinstance(large, Int)
            and 0 < small.precision < large.precision)


@dataclass(frozen=True)
class UnionContainer(Type):
    """Flat struct payload for a tagged union.

    Variant types are deconstructed into typed primitive slots.  Same-type slots are
    shared across mutually-exclusive variants.  Smaller integer slots are merged into
    larger ones when no variant uses both.  Slots are sorted by rank so pointer slots
    come before scalar slots, giving the GC precise (never maybe-pointer) information.
    """
    slots: tuple[tuple[str, Type], ...]  # (slot_name, slot_type)

    def _declare_struct(self, type_cache: dict[Type, tuple[str, str]], field_indent: str) -> str:
        new_indent = field_indent + "    "
        members = "".join(
            f"\n{field_indent}{slot_t._declare(type_cache, new_indent)} {mangle_name(name)};"
            for name, slot_t in self.slots)
        return f"struct {{{members}\n{field_indent[:-4]}}}"

    def get_pointer_paths(self, path: str) -> list[str]:
        return [f"{path}.{mangle_name(name)}"
                for name, slot_t in self.slots
                if slot_t.get_pointer_paths("x") == ["x"]]

    @staticmethod
    def compute(variant_types: list[Type]) -> tuple[UnionContainer, tuple[tuple[tuple[int, Type], ...], ...]]:
        """Compute the slot layout for a union with the given variant types.

        Returns (UnionContainer, variant_map) where variant_map[i] is a tuple of
        (slot_index, original_type) for each primitive of variant i.  When original_type
        differs from the slot type, a smaller int was merged into a larger slot (truncate
        on read, zero-extend on write).
        """
        flat: list[list[Type]] = [_flatten_primitives(vt) for vt in variant_types]

        # slots_list: list of [slot_type, set_of_variant_indices]
        slots_list: list[list] = []
        vmap: list[list[tuple[int, Type]]] = [[] for _ in flat]

        for vi, prims in enumerate(flat):
            for prim in prims:
                found = next(
                    (si for si, (st, su) in enumerate(slots_list) if st == prim and vi not in su),
                    -1)
                if found >= 0:
                    slots_list[found][1].add(vi)
                    vmap[vi].append((found, prim))
                else:
                    slots_list.append([prim, {vi}])
                    vmap[vi].append((len(slots_list) - 1, prim))

        # Merge smaller int slots into larger ones when no variant uses both
        changed = True
        while changed:
            changed = False
            for si in range(len(slots_list)):
                if slots_list[si] is None: continue
                st, su = slots_list[si]
                for li in range(len(slots_list)):
                    if li == si or slots_list[li] is None: continue
                    lt, lu = slots_list[li]
                    if _can_merge_into(st, lt) and su.isdisjoint(lu):
                        lu.update(su)
                        for vi in su:
                            vmap[vi] = [(li if s == si else s, orig) for s, orig in vmap[vi]]
                        slots_list[si] = None
                        changed = True
                        break
                if changed: break

        # Collect active slots and sort by rank
        active = [(si, s) for si, s in enumerate(slots_list) if s is not None]
        active.sort(key=lambda x: _primitive_rank(x[1][0]))
        renumber = {old_si: new_si for new_si, (old_si, _) in enumerate(active)}

        slot_fields = tuple((f"$s{new_si}", s[0]) for new_si, (_, s) in enumerate(active)) + (("$tag", Int(32)),)
        variant_map = tuple(
            tuple((renumber[si], orig) for si, orig in vm)
            for vm in vmap
        )
        return UnionContainer(slots=slot_fields), variant_map
