from __future__ import annotations

from itertools import groupby
from collections.abc import Mapping
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from typing import Callable, Any
from codegen.tools import mangle_name

# word_size = 8
max_int = (1 << 31) - 1
min_int = 0 - max_int - 1
mask_int = (1 << 32) - 1


@dataclass(frozen=True)
class Type(ABC):
    def words_upper_bound(self) -> int:
        """Conservative bound on this type's size in pointer-words, for sizing
        the vtable's pointer-mask window array. Every member rounds UP to
        whole words, so the bound never undershoots the real C layout (member
        alignment never exceeds a word) — an overshoot merely emits an all-zero
        trailing mask window, which the GC walkers skip for free."""
        return 1

    @property
    def nominal_size(self) -> int:
        """Rank for laying out tagged-union slots, largest first. An IR fact,
        not a byte count: a pointer's 6 places pointers between the 8-byte
        and 4-byte scalars whatever the target's word size. Only primitive
        slot types have one — a new primitive must choose, never default."""
        raise NotImplementedError(f"{type(self).__name__} has no nominal size")
    # @property
    # @abstractmethod
    # def size(self) -> int:
    #     pass

    @property
    def has_pointers(self) -> bool:
        return False

    @property
    def never_null(self) -> bool:
        """Is this a word no value of the type leaves zero? Only a
        primitive slot type can say yes (DataPointer, Str, IntPtr): a flat
        enum tells its variants apart by such words (compute_enum_slots)."""
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
            type_str = "typedef " + self._declare_struct(type_cache, "    ")
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

def str_literal(value: str) -> str:
    # Emit the literal's UTF-8 bytes into a C string. Each byte outside the
    # printable-ASCII range becomes a three-digit octal escape (\ooo): octal
    # consumes at most three digits, so — unlike \xHH, which greedily eats
    # every following hex digit — a subsequent digit can never be swallowed
    # into the escape. This keeps multi-byte sequences intact (é → \303\251,
    # 🎉 → \360\237\216\211), where escaping per Python codepoint instead
    # corrupted U+0080..U+00FF into a single Latin-1 byte and let codepoints
    # ≥ U+0100 through only by accident of the source encoding.
    out: list[str] = []
    for byte in value.encode("utf-8"):
        if byte == 0x5C:                  # backslash
            out.append("\\\\")
        elif byte == 0x22:                # double quote
            out.append("\\\"")
        elif 0x20 <= byte < 0x7F:         # printable ASCII
            out.append(chr(byte))
        else:
            out.append(f"\\{byte:03o}")
    # The runtime's literal forms (yafl.h): inline up to 15 UTF-8 bytes, a
    # static read-only head beyond — the canonical-by-length rule.
    form = "STR16_SHORT" if len(value.encode("utf-8")) <= 15 else "STR16_LONG"
    return f"{form}(\"{''.join(out)}\")"


def bigint_literal(value: int) -> str:
    # integer_t.sign is 0 (positive) or 1 (negative): the heap form stores it
    # as is, and the tagged form only tests it for truth.
    sign = 0
    if value < 0:
        sign = 1
        value = -value
    array: list[int] = []
    while value != 0:
        array.append(value & mask_int)
        value >>= 32
    if not array:
        return "INTEGER_LITERAL_1(0, 0)"
    elif len(array) == 1:
        return f"INTEGER_LITERAL_1({sign}, {array[0]})"
    elif len(array) == 2:
        return f"INTEGER_LITERAL_2({sign}, {array[0]}, {array[1]})"
    else:
        groups = [[x for _, x in group] for _, group in groupby(enumerate(array), key=lambda x: x[0] // 2)]
        values = [(f"INTEGER_LITERAL_N_1({x[0]})" if len(x) == 1 else f"INTEGER_LITERAL_N_2({x[0]}, {x[1]})") for x in groups]
        return f"INTEGER_LITERAL_N({sign}, {len(array)}, {' INTEGER_LITERAL_SEP '.join(values)})"


@dataclass(frozen=True)
class Int(Type):
    precision: int  # Bit precision: 8, 16, 32, or 64 only — use DataPointer() for bigint

    @property
    def nominal_size(self) -> int:
        return self.precision // 8

    # @property
    # def size(self) -> int:
    #     return self.precision // 8

    def _initialise(self, type_cache: dict[Type, tuple[str, str]], data: Any, field_indent: str) -> str:
        if not isinstance(data, int):
            raise ValueError()
        p = self.precision
        # 64-bit literals need an LL suffix so an in-range value near the top of
        # the signed range isn't taken as `int`/unsigned. The minimum can't be
        # written as `-N` (the operand N = 2^(p-1) overflows the signed type), so
        # emit it as `-(MAX) - 1`. Both keep clang's -Wimplicitly-unsigned-literal
        # quiet while staying standard C.
        suffix = "LL" if p == 64 else ""
        if data == -(1 << (p - 1)):
            return f"((int{p}_t)(-{(1 << (p - 1)) - 1}{suffix} - 1))"
        return f"((int{p}_t){data}{suffix})"

    def _declare(self, type_cache: dict[Type, tuple[str, str]], field_indent: str) -> str:
        return f"int{self.precision}_t"

    def get_pointer_paths(self, path: str) -> list[str]:
        return []


@dataclass(frozen=True)
class Float(Type):
    precision: int  # 32 or 64

    @property
    def nominal_size(self) -> int:
        return self.precision // 8

    def _initialise(self, type_cache: dict[Type, tuple[str, str]], data: Any, field_indent: str) -> str:
        if not isinstance(data, (int, float)):
            raise ValueError("Float literal must be int or float")
        # %.17g, not repr: repr's SHORTEST-round-trip search is not portably
        # re-implementable in the bootstrap, while 17 significant digits
        # round-trip any double exactly and match the bootstrap's printer
        # byte for byte. Integral values keep a trailing ".0" (C reads both,
        # but the two compilers must agree on the bytes).
        s = f"{float(data):.17g}"
        if not any(c in s for c in ".en"):
            s += ".0"
        if self.precision == 32:
            return f"((float){s}f)"
        return f"((double){s})"

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
    # The word is never zero: a function's code pointer, flattened out of a
    # never-NULL FuncPointer. A refinement, as DataPointer.nonnull is.
    nonnull: bool = field(default=False, compare=False)

    @property
    def never_null(self) -> bool:
        return self.nonnull

    @property
    def nominal_size(self) -> int:
        return 5   # pointer-sized, after the GC pointers

    # @property
    # def size(self) -> int:
    #     return word_size

    def _initialise(self, type_cache: dict[Type, tuple[str, str]], data: Any, field_indent: str) -> str:
        return f"{data}"

    def _declare(self, type_cache: dict[Type, tuple[str, str]], field_indent: str) -> str:
        return "intptr_t"


@dataclass(frozen=True)
class DataPointer(Type):
    # Every value of this type is a real word, never NULL: a heap object, a
    # tagged immediate (an Int), a complex enum, a union with no unit member.
    # Set where a type spec lowers; a flat enum tells its variants apart by
    # which slots are NULL when the slots allow it (compute_enum_slots). A
    # REFINEMENT of the same type, not a different representation — never-NULL
    # ≤ maybe-NULL, merged by AND at Phi — so it takes no part in equality,
    # and every type comparison is unchanged by it.
    nonnull: bool = field(default=False, compare=False)

    @property
    def never_null(self) -> bool:
        return self.nonnull

    @property
    def nominal_size(self) -> int:
        return 6   # between the 8-byte and 4-byte scalars

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
class Str(Type):
    """A String value: yafllib's 16-byte `str_t`. OPAQUE to the compiler
    except word 0, `head` — the only GC-visible word, and the dispatch word
    when a union containing String shares this representation (yafl.h,
    "String values"). The rest of the layout is the runtime's business and
    differs by word size, so the compiler never names it."""
    # `head` is never NULL: a String's is a tagged word ("" included) or its
    # buffer. A union that shares this representation puts NULL there for
    # None, so only a String — or a union with no unit member — says so. A
    # refinement, as DataPointer.nonnull is.
    nonnull: bool = field(default=False, compare=False)

    @property
    def never_null(self) -> bool:
        return self.nonnull

    def words_upper_bound(self) -> int:
        return 2   # 16 bytes

    @property
    def nominal_size(self) -> int:
        return 16

    @property
    def has_pointers(self) -> bool:
        return True

    def _declare(self, type_cache: dict[Type, tuple[str, str]], field_indent: str) -> str:
        return "str_t"

    def get_pointer_paths(self, path: str) -> list[str]:
        return [f"{path}.head"]


@dataclass(frozen=True)
class FuncPointer(Type):
    # Every function this value can hold is provably unable to suspend, so a
    # call through it is a plain call (lowering/sync_inference.py sets it,
    # async_lower reads it). A REFINEMENT of the same type, not a different
    # representation: sync ≤ may-suspend, merged by AND at Phi — so it takes
    # no part in equality, and every type comparison is unchanged by it.
    sync: bool = field(default=False, compare=False)
    # The code pointer `f` is never NULL: the value is a function (only a
    # task in flight, never matched on, leaves it NULL). The environment may
    # be NULL. A refinement, as DataPointer.nonnull is.
    nonnull: bool = field(default=False, compare=False)

    def words_upper_bound(self) -> int:
        return 2  # fun_t = { void* f; void* o; }
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

    def words_upper_bound(self) -> int:
        return sum(t.words_upper_bound() for _, t in self.fields)

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
        body = "".join(f"\n{field_indent}{field_type._declare(type_cache, new_indent)} {mangle_name(name)};"
                       for name, field_type in self.fields)
        return "struct { " + body + "\n" + field_indent[:-4] + "}"

    def __add__(self, other: Struct) -> Struct:
        return Struct(self.fields + other.fields)

    def get_pointer_paths(self, path: str) -> List[str]:
        return [pointer_path for name, field_type in self.fields for pointer_path in
                field_type.get_pointer_paths(f"{path}.{mangle_name(name)}")]




@dataclass(frozen=True)
class Void(Type):
    def words_upper_bound(self) -> int:
        return 0
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

    def words_upper_bound(self) -> int:
        return self.type.words_upper_bound() * self.length

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
    """Wraps a return type with no top-level pointer in a struct so it can carry a task signal.

    Emits: struct { <inner> value; object_t* task; }
    task == NULL means a real value; task != NULL means the result is a pending task
    (and `value` is zeroed).
    """
    inner: Type

    def words_upper_bound(self) -> int:
        return self.inner.words_upper_bound() + 1

    @property
    def has_pointers(self) -> bool:
        return True  # the task field is a GC pointer

    def _declare_struct(self, type_cache: dict[Type, tuple[str, str]], field_indent: str) -> str:
        inner_decl = self.inner._declare(type_cache, field_indent)
        return f"struct {{\n{field_indent}{inner_decl} value;\n{field_indent}object_t* task;\n{field_indent[:-4]}}}"

    def get_pointer_paths(self, path: str) -> list[str]:
        # The value's own pointers, then the task: a result that completed
        # synchronously is live in `value`, and is traced from there.
        return self.inner.get_pointer_paths(f"{path}.value") + [f"{path}.task"]


def first_pointer_field(t: Type) -> str | None:
    """Return the name of the first DataPointer-typed field in a Struct type, or None."""
    if not isinstance(t, Struct):
        return None
    for name, ft in t.fields:
        if isinstance(ft, DataPointer):
            return name
    return None


def is_task_check(expr: str, t: Type) -> str:
    """Return a C expression (truthy when result is a task) for the given return type."""
    if isinstance(t, DataPointer):
        return f"PTR_IS_TASK({expr})"
    if isinstance(t, FuncPointer):
        return f"PTR_IS_TASK(({expr}).o)"
    if isinstance(t, Str):
        return f"PTR_IS_TASK(({expr}).head)"
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
        # f=code pointer (non-GC), o=data pointer (GC)
        return [IntPtr(nonnull=t.nonnull), DataPointer()]
    return [t]  # Int, Float, DataPointer, IntPtr — already primitive


def _can_merge_into(small: Type, large: Type) -> bool:
    """True if a fixed-width small integer can be stored in a fixed-width larger integer slot."""
    return (isinstance(small, Int) and isinstance(large, Int)
            and 0 < small.precision < large.precision)


def _slot_key(t: Type) -> Type:
    """Canonical slot type for union slot sharing: never-NULL and nullable
    words of one kind share a slot. Whether the slot itself is never NULL is
    settled once packing knows every variant's use of it (_pack_slots)."""
    return type(t)() if t.never_null else t


def _tag_type(n_variants: int) -> Int:
    if n_variants <= 127:
        return Int(8)
    if n_variants <= 32767:
        return Int(16)
    return Int(32)


def compute_union_slots(variant_types: list[Type], max_tag: int | None = None) -> tuple[Struct, tuple[tuple[tuple[int, Type], ...], ...]]:
    """Compute the shared-slot layout for a tagged union with the given per-variant types.

    Returns (Struct, variant_map) where variant_map[i] is a tuple of
    (slot_index, original_type) for each primitive of variant i.  When original_type
    differs from the slot type, a smaller int was merged into a larger slot (truncate
    on read, zero-extend on write).  The last field of the returned Struct is always
    the $tag discriminant.
    """
    slot_types, variant_map = _pack_slots(variant_types)
    return _tagged_struct(slot_types, len(variant_types), max_tag), variant_map


def compute_enum_slots(variant_types: list[Type], max_tag: int | None = None) -> tuple[Struct, tuple[tuple[tuple[int, Type], ...], ...], tuple[tuple[tuple[int, bool], ...], ...] | None]:
    """The shared-slot layout of a flat enum: compute_union_slots' slots, and
    no $tag when the slots alone tell every variant apart (#75).

    A variant leaves every slot it does not use NULL, and a never-NULL word
    (Type.never_null) in a slot it does use is never NULL. So where, for
    every pair of variants, some slot is never-NULL in one and unused by the
    other, the pattern of NULL slots names the variant. Returns (Struct,
    variant_map, null_tests): null_tests[i] is the conjunction of
    (slot_index, is_null) tests that holds for variant i and for no other —
    or None, and the Struct ends in $tag as compute_union_slots' does.

    Only the size-optimal slots are considered: a slot added to spare the tag
    would cost the word the tag costs."""
    slot_types, variant_map = _pack_slots(variant_types)
    null_tests = _null_pattern_tests(variant_map, len(slot_types))
    if null_tests is None:
        return _tagged_struct(slot_types, len(variant_types), max_tag), variant_map, None
    return Struct(fields=_slot_fields(slot_types)), variant_map, null_tests


def _null_pattern_tests(variant_map, n_slots: int) -> tuple[tuple[tuple[int, bool], ...], ...] | None:
    """Per variant, the fewest (slot_index, is_null) tests that rule out every
    other variant — chosen greedily, each test the one ruling out most of the
    variants still left (ties to a non-NULL test, then to the lowest slot)
    — or None when some pair of variants cannot be told apart. A
    single variant has nothing to tell apart from: it keeps its tag."""
    if len(variant_map) < 2:
        return None
    used = [frozenset(si for si, _ in vm) for vm in variant_map]
    never_null = [frozenset(si for si, orig in vm if orig.never_null) for vm in variant_map]

    def ruled_out(test: tuple[int, bool], wi: int) -> bool:
        si, is_null = test
        return si in never_null[wi] if is_null else si not in used[wi]

    result = []
    for vi in range(len(variant_map)):
        candidates = ([(si, False) for si in sorted(never_null[vi])]
                      + [(si, True) for si in range(n_slots) if si not in used[vi]])
        left = {wi for wi in range(len(variant_map)) if wi != vi}
        chosen: list[tuple[int, bool]] = []
        while left:
            best = max(candidates, key=lambda c: sum(ruled_out(c, wi) for wi in left), default=None)
            hits = {wi for wi in left if best is not None and ruled_out(best, wi)}
            if not hits:
                return None
            chosen.append(best)
            left -= hits
        result.append(tuple(sorted(chosen)))
    return tuple(result)


def _slot_fields(slot_types: list[Type]) -> tuple[tuple[str, Type], ...]:
    return tuple((f"$s{si}", st) for si, st in enumerate(slot_types))


def _tagged_struct(slot_types: list[Type], n_variants: int, max_tag: int | None) -> Struct:
    # The tag must hold the largest value actually STORED: a flat enum stores
    # positional indices (< len), but a tagged combination stores GLOBAL
    # discriminators — the caller passes their maximum via max_tag, and a
    # 2-member union whose member is discriminator 135 needs more than int8.
    tag_bound = max(n_variants, (max_tag or 0) + 1)
    return Struct(fields=_slot_fields(slot_types) + (("$tag", _tag_type(tag_bound)),))


def _pack_slots(variant_types: list[Type]) -> tuple[list[Type], tuple[tuple[tuple[int, Type], ...], ...]]:
    """The union's shared slots, largest first, and each variant's primitive
    -> slot assignment."""
    flat: list[list[Type]] = [_flatten_primitives(vt) for vt in variant_types]

    # slots_list: list of [slot_type, set_of_variant_indices]
    slots_list: list[list] = []
    vmap: list[list[tuple[int, Type]]] = [[] for _ in flat]

    for vi, prims in enumerate(flat):
        for prim in prims:
            prim_key = _slot_key(prim)
            found = next(
                (si for si, (st, su) in enumerate(slots_list) if st == prim_key and vi not in su),
                -1)
            if found >= 0:
                slots_list[found][1].add(vi)
                vmap[vi].append((found, prim))
            else:
                slots_list.append([prim_key, {vi}])
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

    # Collect active slots, largest nominal size first (a stable sort: equal
    # sizes keep first-use order)
    active = [(si, s) for si, s in enumerate(slots_list) if s is not None]
    active.sort(key=lambda x: -x[1][0].nominal_size)
    renumber = {old_si: new_si for new_si, (old_si, _) in enumerate(active)}
    variant_map = tuple(
        tuple((renumber[si], orig) for si, orig in vm)
        for vm in vmap
    )

    # A slot every variant fills with a never-NULL word is never NULL; one a
    # variant leaves unused is NULL in that variant's values. Carried on the
    # slot type, so a union enclosing this one can name its own variants by it.
    def slot_type(old_si: int, st: Type) -> Type:
        filled = all(any(si == old_si and orig.never_null for si, orig in vm) for vm in vmap)
        return replace(st, nonnull=True) if filled else st
    return [slot_type(si, s[0]) for si, s in active], variant_map
