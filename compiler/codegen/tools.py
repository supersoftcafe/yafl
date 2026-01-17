from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import codegen.typedecl

__valid_chars = "abcdefghijklmnoprstuvwxyzABCDEFGHIJKLMNOPRSTUVWXYZ0123456789_"
def mangle_name(symbol: str) -> str:
    return ''.join(c if c in __valid_chars else f"Q{ord(c)}q" for c in symbol).replace('Q58qQ58q', 'Q__q')

def to_pointer_mask(field_type: codegen.typedecl.Type, type_str: str) -> str:
    mask = "".join(f"|maskof({type_str}, {path})" for path in field_type.get_pointer_paths(""))
    return f"(0{mask})"
