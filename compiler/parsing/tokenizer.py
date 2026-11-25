from __future__ import annotations

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
    CHAR = 7
    REGEX = 8
    INTERP = 9

    def __repr__(self):
        return self.name


@dataclass(frozen=True, order=True)
class LineRef:
    """Where a token is written: file, line, the 1-based column it starts at,
    and its length in characters. Everything that makes one says what it
    marks, so `length` is at least 1. The one exception is a position the
    compiler invents, with no source behind it: `synthetic` and `invented`
    make those, with length 0, and nothing else does. `point` is the other
    way to name a place without a token: one character wide."""
    filename: str
    line: int
    offset: int
    length: int

    @staticmethod
    def synthetic(filename: str, line: int, offset: int) -> "LineRef":
        """A position that marks no source text (a made-up name, a generated
        unit). Length 0 is what says so."""
        return LineRef(filename, line, offset, 0)

    def invented(self) -> "LineRef":
        """The same place, for a node the compiler makes up there: it marks no
        source text of its own."""
        return LineRef(self.filename, self.line, self.offset, 0)

    def point(self) -> "LineRef":
        """The place this one starts at, one character wide: where a block
        ends is a place, not a token."""
        return LineRef(self.filename, self.line, self.offset, 1)

    def same_start(self, other: "LineRef") -> bool:
        """Whether both begin at the same place, whatever their lengths: the
        compiler's made-up names begin where the code they stand for does."""
        return (self.filename, self.line, self.offset) == (other.filename, other.line, other.offset)

    def __repr__(self):
        # The whole name, path included: a unit is identified by its path
        # relative to its root, and a diagnostic that says only `fs.yafl`
        # cannot tell two same-named units apart.
        return f"{self.filename}[{self.line}:{self.offset}]"

    def hash6(self) -> str:
        # Hash the place only (file, line, column): the length is not part of a name
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


__keywords = ["ret", "let", "fun", "typealias", "where", "class", "interface", "instance", "import", "namespace", "__builtin_type__", "__builtin_op__", "__builtin_pin_set__", "match", "enum", "if", "else", "with"]
__ws = re.compile(r"[\t\v ]+")
__kinds = [
    (__ws, None),  # White space
    (re.compile(r"#.*"), None),  # Line comment
    # String literal: opening quote, then a body of either escape sequence
    # (backslash + any single char, including a quote or another backslash)
    # OR any non-backslash non-quote char. Ordering matters — `\.` must
    # win over `[^\\\"]` so `"\""` tokenises as a single 4-char literal
    # rather than splitting on the escaped quote.
    # Regex literal: `re"..."` — RAW (escapes are NOT decoded; the regex
    # engine owns its backslashes), but backslash-pairs are still consumed so
    # an escaped quote stays inside the token. Must precede IDENTIFIER, which
    # would otherwise eat the `re` prefix.
    (re.compile(r"re\"(\\.|[^\\\"])*\"?"), TokenKind.REGEX),
    # Interpolated string: `$"text {expr} text {expr, spec}"`. Text is the
    # string body (an escape, or any char but backslash, quote and `{`); a
    # slot is `{`, then plain string / char literals or any char but quote,
    # apostrophe and braces, then `}`. A slot may hold string literals but no
    # braces outside them, so the nesting stays one level deep and the token
    # stays regular. The parser splits the token and reports what this
    # pattern stops short on (an unterminated slot, a nested `$"`).
    (re.compile(r"\$\"(?:\\.|\{(?:\"(?:\\.|[^\\\"])*\"|'(?:\\.|[^\\'])*'|[^\"'{}])*\}?|[^\\\"{])*\"?"),
     TokenKind.INTERP),
    (re.compile(r"\"(\\.|[^\\\"])*\"?"), TokenKind.STRING),
    # Char literal: single quotes, same escape body as a string. The parser
    # decodes it (reusing the string escapes) and requires exactly one
    # codepoint, yielding an Int32 of that codepoint's value.
    (re.compile(r"'(\\.|[^\\'])*'?"), TokenKind.CHAR),
    (re.compile(r"([^\d\W][\w_]*)|(`[^`]*`)"), TokenKind.IDENTIFIER),
    (re.compile(r"(&&)|(\|\|)|(==)|(\|>)|(\?\?)|(\?>)|(<<)|(>>)|(!=)|(<=)|(>=)|(=>)|(:=)|(::)|(\.\.)|[=%*+?\-/&|^!~()\[\]<>.;:,]"), TokenKind.SYMBOLS),
    # Numeric literal: hex/bin/oct prefix forms, OR decimal with optional
    # fraction, exponent (signed or unsigned), and type suffix (i8|i16|i32|i64|f32|f64).
    # The fraction's negative lookahead keeps `1..9` out of the float: `1.`
    # is only a float when the dot is NOT immediately followed by another
    # dot (which would be the `..` range symbol).
    (re.compile(
        r"0[xX][0-9a-fA-F_]+(?:[a-zA-Z]\w*)?"        # hex
        r"|0[bB][01_]+(?:[a-zA-Z]\w*)?"               # binary
        r"|0[oO][0-7_]+(?:[a-zA-Z]\w*)?"              # octal
        r"|\d[\d_]*(?:\.(?!\.)[\d_]*)?(?:[eE][+-]?\d[\d_]*)?(?:[a-zA-Z]\w*)?"  # decimal
    ), TokenKind.NUMBER),
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
                        tokens.append(Token(kind, match, indent, LineRef(filename, lineno, offset+1, len(match))))
                    offset += len(match)
                    break

    if tokens:
        tk = tokens[-1]
        # The end of the file: the place the next character would be, one wide.
        lr = LineRef(filename, tk.line_ref.line, tk.line_ref.offset + tk.line_ref.length, 1)
    else:
        lr = LineRef(filename, 1, 1, 1)
    tokens.append(Token(TokenKind.EOF, "", 0, lr))

    return tokens
