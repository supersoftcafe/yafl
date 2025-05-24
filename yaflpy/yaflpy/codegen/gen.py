from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Callable, List, Dict, Any, Tuple, Union
from pathlib import Path

from codegen.tools import mangle_name

from codegen.perfecthash import create_perfect_lookups
from codegen.things import *
from codegen.typedecl import *


_common_code_path = Path(__file__).parent.parent / "lowlevel"

def _read_source(path: Path) -> str:
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    for i, line in enumerate(lines):
        if line.startswith("#line "):
            return ''.join(lines[i:])
    return ''

def _read_common_code(just_testing: bool = False) -> str:
    if just_testing: return ""
    h = ''.join(_read_source(x) for x in _common_code_path.glob(f"*.h"))
    c = ''.join(_read_source(x) for x in _common_code_path.glob(f"*.c"))
    return h + c

def _gen_function_ids(global_ids: dict[str, int]) -> str:
    if not global_ids: return ""
    return f"enum {{{','.join(f'\n    __FUNCTION_ID__{mangle_name(name)} = rotate_function_id({id})' for name, id in global_ids.items())}\n}};\n"


# Aggregates all application data for code generation
class Application:
    functions: Dict[str, Function] = { }
    objects: Dict[str, Object] = { }
    globals: Dict[str, Global] = { }

    __type_cache: dict[Type, tuple[str, str]] = { }
    __typedefs : list[str] = []
    __forwards : list[str] = []
    __vtables  : list[str] = []
    __variables: list[str] = []
    __functions: list[str] = []


    def __gen_function(self, name: str, f: Function):
        self.__forwards.append(f.to_c_prototype(self.__type_cache))
        self.__functions.append(f.to_c_implement(self.__type_cache))

    def __gen_object(
            self, name: str, o: Object,
            global_ids: dict[str, int],
            vtable_sizes: dict[str, int]):
        type_cache = self.__type_cache

        # Build up the hashed vtable
        default_entry = {"i": -1, "f": "(void*)&__abort_on_vtable_lookup"}
        vtable_size = vtable_sizes[name]
        vtable_array = [default_entry] * vtable_size
        for slot_id, target in o.functions:
            id = global_ids[slot_id]
            index = id & (vtable_size-1)
            while vtable_array[index]["i"] != -1:
                index += 1
                if index >= len(vtable_array):
                    vtable_array.append(default_entry)
            vtable_array[index] = {"i": f"__FUNCTION_ID__{mangle_name(slot_id)}", "f": f"(void*)&{mangle_name(target)}"}

        # Ensure last entry is empty as a final catch-all
        if vtable_array[-1]["i"] != -1:
            vtable_array.append(default_entry)

        mangled_name = mangle_name(name)
        implements_array = [f"obj_{mangle_name(e)}" for e in o.extends]
        implements_str = ", ".join(implements_array)
        vtable_str = ",".join(f"\n        {{ .i = {entry['i']}, .f = {entry['f']} }}" for entry in vtable_array)

        self.__typedefs.append(f"{o.comment_line}typedef {o.fields.declare(type_cache)} ALIGNED {mangled_name}_t;\n")
        self.__forwards.append(f"{o.comment_line}static vtable_t* const obj_{mangled_name};\n")
        self.__variables.append(
            f"{o.comment_line}static vtable_t* const obj_{mangle_name(name)} = VTABLE_DECLARE({len(vtable_array)}){{\n" +
            f"    .object_size = {o.get_object_size(type_cache)},\n"
            f"    .array_el_size = {o.get_array_el_size(type_cache)},\n"
            f"    .object_pointer_locations = {o.get_pointer_mask(type_cache)},\n"
            f"    .array_el_pointer_locations = {o.get_array_pointer_mask(type_cache)},\n"
            f"    .functions_mask = rotate_function_id({vtable_size-1}),\n"
            f"    .array_len_offset = {o.get_array_length_offset(type_cache)},\n"
            f"    .implements_array = VTABLE_IMPLEMENTS({len(implements_array)}, {implements_str}),\n"
            f"    .lookup = {{ {vtable_str} }},\n"
            f"}};\n")

    def __gen_global(self, name: str, g: Global):
        self.__forwards.append(g.to_c_prototype(self.__type_cache))
        self.__variables.append(g.to_c_implement(self.__type_cache))

    def __declare_roots(self) -> str:
        return ("EXPORT decl_func\n"
                "void declare_roots_yafl(void(*declare)(object_t**)) {\n"
                "}\n")

    def gen(self, just_testing = False) -> str:
        entry_point_name = "__entrypoint__"
        if entry_point_name not in self.functions:
            raise ValueError(f"A function called '{entry_point_name}' is required")
        ep = self.functions[entry_point_name]
        if ep.params != Struct( fields = ( ("this", DataPointer()), ("$continuation", FuncPointer())) ):
            raise ValueError(f"Function '{entry_point_name}' is required to take a single 'this' parameter only")
        if ep.result != Void():
            raise ValueError(f"Function '{entry_point_name}' is required to return Void")

        vtables = {name: [signature for signature, _ in o.functions] for name, o in self.objects.items()}
        global_ids, vtable_sizes = create_perfect_lookups(vtables)

        for name, f in self.functions.items():
            self.__gen_function(name, f)
        for name, o in self.objects.items():
            self.__gen_object(name, o, global_ids, vtable_sizes)
        for name, g in self.globals.items():
            self.__gen_global(name, g)

        common_code = _read_common_code(just_testing=just_testing)

        return "\n".join([
            common_code,
            f"\n#line {len(common_code.splitlines())} \"yafl.c\"",
            _gen_function_ids(global_ids),
            "\n".join(declaration for name, declaration in self.__type_cache.values()),
            "\n".join(self.__typedefs),
            "\n".join(self.__forwards),
            "\n".join(self.__vtables),
            "\n".join(self.__variables),
            "\n".join(self.__functions),
            "\n" + self.__declare_roots(),
        ])
