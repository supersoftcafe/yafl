from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Callable, List, Dict, Any, Tuple, Union
from pathlib import Path
from codegen.tools import mangle_name

from codegen.perfecthash import create_perfect_lookups
from codegen.things import *
from codegen.typedecl import *


def _real_vtable(vtable_size: int, implements_size: int) -> Struct:
    return  Struct((
        ("object_size", Int(16)),
        ("array_el_size", Int(16)),
        ("object_pointer_locations", Int(32)),
        ("array_el_pointer_locations", Int(32)),
        ("functions_mask", Int(32)),
        ("array_len_offset", Int(16)),
        ("implements_count", Int(16)),
        ("implements_offset", Int(32)),
        ("entries", Array(Struct((
            ("i", IntPtr()),
            ("f", DataPointer())
        )), vtable_size)),
        ("implements", Array(DataPointer(),implements_size))
    ))


# Aggregates all application data for code generation
class Application:
    functions: Dict[str, Function] = { }
    objects: Dict[str, Object] = { }
    globals: Dict[str, Global] = { }

    __type_cache: dict[Type, (str, str)] = { }
    __typedefs : list[str] = []
    __forwards : list[str] = []
    __variables: list[str] = []
    __functions: list[str] = []



    def __gen_function(self, name: str, f: Function):
        self.__forwards.append(f.to_c_prototype(self.__type_cache))
        self.__functions.append(f.to_c_implement(self.__type_cache))

    def __gen_object(self, name: str, o: Object, global_ids: dict[str, int], vtable_sizes: dict[str, int]):
        type_cache = self.__type_cache

        # Build up the hashed vtable
        default_entry = {"i": "-1", "f": "&abort"}
        vtable_size = vtable_sizes[name]
        vtable_array = [default_entry] * vtable_size
        for signature, target in o.functions:
            id = global_ids[signature]
            index = id & (vtable_size-1)
            while vtable_array[index]["i"] == -1:
                index += 1
                if index >= len(vtable_array):
                    vtable_array.append(default_entry)
            vtable_array[index] = {"i": f"__FUNCTION_ID__{mangle_name(signature)}", "f": f"&{mangle_name(target)}"}

        # Ensure last entry is empty as a final catch-all
        if vtable_array[-1]["i"] != -1:
            vtable_array.append(default_entry)

        # Write out the vtable
        implements = [f"&{mangle_name(e)}" for e in o.extends]
        vtable_type = _real_vtable(len(vtable_array), len(implements))
        vtable_data = {
            "object_size": o.get_object_size(type_cache),
            "array_el_size": o.get_array_el_size(type_cache),
            "object_pointer_locations": o.get_pointer_mask(type_cache),
            "array_el_pointer_locations": o.get_array_pointer_mask(type_cache),
            "functions_mask": f"rotate_function_id({vtable_size-1})",
            "array_len_offset": o.get_array_length_offset(type_cache),
            "implements_count": len(implements),
            "implements_offset": vtable_type.offsetof("implements", 0),
            "entries": vtable_array,
            "implements": implements
        }

        self.__typedefs.append(f"typedef {o.fields.declare(type_cache)} {mangle_name(name)}_t;")
        self.__variables.append(f"static {vtable_type.declare(self.__type_cache)} {mangle_name(name)} = {vtable_type.initialise(self.__type_cache, vtable_data)};")

    def __gen_global(self, name: str, g: Global) -> str:
        f"static {g.type.declare(self.__type_cache)} {mangle_name(g.name)};"

    def __gen_function_ids(self, global_ids: dict[str, int]) -> str:
        if not global_ids:
            return "";
        return f"enum {{{','.join(f'\n    __FUNCTION_ID__{mangle_name(name)} = rotate_function_id({id})' for name, id in global_ids.items())}\n}};\n"

    def __read_common_code(self, name, just_testing = False):
        if just_testing:
            return ""
        path = Path(__file__).parent / f"common_{name}.h"
        with path.open() as f:
            return f.read()

    def gen(self, just_testing = False) -> str:
        entry_point_name = "__entrypoint__"
        if entry_point_name not in self.functions:
            raise ValueError(f"A function called '{entry_point_name}' is required")
        ep = self.functions[entry_point_name]
        if ep.params != Struct( fields = ( ("this", DataPointer()), ) ):
            raise ValueError(f"Function '{entry_point_name}' is required to take a single 'this' parameter only")
        if ep.result != Int(32):
            raise ValueError(f"Function '{entry_point_name}' is required to return int32")

        vtables = {name: [signature for signature, _ in o.functions] for name, o in self.objects.items()}
        global_ids, vtable_sizes = create_perfect_lookups(vtables)

        for name, f in self.functions.items():
            self.__gen_function(name, f)
        for name, o in self.objects.items():
            self.__gen_object(name, o, global_ids, vtable_sizes)
        for name, g in self.globals.items():
            self.__gen_global(name, g)

        return "\n".join([
            self.__read_common_code("prefix", just_testing=just_testing),
            self.__gen_function_ids(global_ids),
            "\n".join(declaration for name, declaration in self.__type_cache.values()),
            "\n".join(self.__typedefs),
            "\n".join(self.__forwards),
            "\n".join(self.__variables),
            "\n".join(self.__functions),
            self.__read_common_code("suffix", just_testing=just_testing)
        ])
