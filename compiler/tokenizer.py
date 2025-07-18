from __future__ import annotations

from pathlib import Path
from functools import cached_property
from dataclasses import dataclass, field
from typing import Optional, Callable, List, Any, Tuple, Union, Generator
from enum import Enum
import re

import hashlib
import string
import base64


class TokenKind(Enum):
    STRING = 1
    IDENTIFIER = 2
    SYMBOLS = 3
    NUMBER = 4
    CRAP = 5
    EOF = 6

    def __repr__(self):
        return self.name


@dataclass(frozen=True, order=True)
class LineRef:
    filename: str
    line: int
    offset: int

    def __repr__(self):
        return f"{Path(self.filename).name}[{self.line}:{self.offset}]"

    def hash6(self) -> str:
        # Create string to hash from all fields
        source = f"{self.filename}:{self.line}:{self.offset}"

        # Generate bytes hash
        hash_bytes = hashlib.md5(source.encode()).digest()

        # Convert to base64 to get alphanumeric chars
        b64 = base64.b64encode(hash_bytes).decode()

        # Filter to only alphanumeric and take first 6
        valid_chars = string.ascii_letters + string.digits
        hash_str = ''.join(c for c in b64 if c in valid_chars)
        return hash_str[:6]


@dataclass(frozen=True)
class Token:
    kind: TokenKind
    value: str
    indent: int
    line_ref: LineRef


__keywords = ["ret", "let", "fun", "typealias", "interface", "class", "import", "namespace", "__builtin_type__", "__builtin_op__"]
__ws = re.compile(r"[\t\v ]+")
__kinds = [
    (__ws, None),  # White space
    (re.compile(r"#.*"), None),  # Line comment
    (re.compile(r"\"([^\"]|(\\\\)|(\\\"))*\"?"), TokenKind.STRING),
    (re.compile(r"([^\d\W][\w_]*)|(`[^`]*`)"), TokenKind.IDENTIFIER),
    (re.compile(r"(<<)|(>>)|(!=)|(<=)|(>=)|(=>)|(::)|[=%*+?\-/&|^!()\[\]<>.;:,]"), TokenKind.SYMBOLS),
    (re.compile(r"\d[\w_]*((\.[a-df-zA-DF-Z\d_]*)?([eE][+-][\w_]*)|(\.[\w_]*))?"), TokenKind.NUMBER),
    (re.compile(r"."), TokenKind.CRAP)
]


def tokenize(content: str, filename: str) -> List[Token]:
    tokens = []
    for lineno, line in enumerate(content.splitlines(), 1):
        indent = len(match[0]) if (match := __ws.match(line)) else 0
        offset = indent
        while offset < len(line):
            for expr, kind in __kinds:
                if match := expr.match(line, offset):
                    match = match[0]
                    if kind:
                        if kind == TokenKind.IDENTIFIER and match in __keywords:
                            kind = TokenKind.SYMBOLS
                        tokens.append(Token(kind, match, indent, LineRef(filename, lineno, offset+1)))
                    offset += len(match)
                    break

    if tokens:
        tk = tokens[-1]
        lr = LineRef(filename, tk.line_ref.line, tk.line_ref.offset + len(tk.value))
    else:
        lr = LineRef(filename, 1, 1)
    tokens.append(Token(TokenKind.EOF, "", 0, lr))

    return tokens
