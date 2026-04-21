from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import codegen.typedecl

_VALID_CHARS = frozenset('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_')

_OPERATOR_CHARS: dict[str, str] = {
    '+': 'plus',
    '-': 'minus',
    '*': 'star',
    '/': 'slash',
    '=': 'eq',
    '>': 'gt',
    '<': 'lt',
    '?': 'bind',
    '|': 'or',
    '&': 'and',
    '!': 'bang',
    '%': 'mod',
    '^': 'xor',
    '~': 'tilde',
}

def mangle_name(symbol: str) -> str:
    # :: (namespace separator) becomes __ before individual char processing
    symbol = symbol.replace('::', '__')
    result = []
    for c in symbol:
        if c in _VALID_CHARS:
            result.append(c)
        elif c in ('@', '$'):
            result.append('_')
        elif c == '`':
            pass  # backtick delimiters around operator names — strip them
        elif c in _OPERATOR_CHARS:
            result.append(_OPERATOR_CHARS[c])
        else:
            result.append(f'X{ord(c):02x}')
    return ''.join(result)

def to_pointer_mask(field_type: codegen.typedecl.Type, type_str: str) -> str:
    mask = "".join(f"|maskof({type_str}, {path})" for path in field_type.get_pointer_paths(""))
    return f"(0{mask})"
