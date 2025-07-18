from __future__ import annotations

from typing import Generic, TypeVar
from dataclasses import dataclass, field
from tokenizer import *


T = TypeVar('T')
Y = TypeVar('Y')


@dataclass(frozen=True,order=True)
class Error:
    line_ref: LineRef
    message: str

    def __str__(self):
        return f"{self.line_ref} - {self.message}"


@dataclass(frozen=True)
class Result(Generic[T]):
    value: Optional[T]
    tokens: List[Token]
    line_ref: LineRef
    errors: List[Error]

    def __bool__(self) -> bool:
        return self.value is not None

    @staticmethod
    def ok(value: T, tokens: list[Token], line_ref: LineRef) -> Result[T]:
        return Result(value, tokens, line_ref, [])

    @staticmethod
    def none(tokens: List[Token], line_ref: LineRef) -> Result[T]:
        return Result(None, tokens, line_ref, [])

    @staticmethod
    def error(message: str, tokens: list[Token], line_ref: LineRef) -> Result[T]:
        return Result(None, tokens, line_ref, [Error(tokens[-1].line_ref, message)])


@dataclass(frozen=True)
class Parser(Generic[T]):
    wrapped_parser: Callable[[List[Token]], Result[T]]

    def __call__(self, *args, **kwargs):
        return self.wrapped_parser(*args, **kwargs)

    def __or__(self, other):
        def p(tokens: List[Token]) -> Result[T]:
            left = self(tokens)
            if left:
                return left
            return other(tokens)
        return Parser(p)

    def __and__(self, other):
        def p(tokens: List[Token]) -> Result[T]:
            def as_tuple(a):
                if not isinstance(a, tuple):
                    a = (a,)
                return a
            left = self(tokens)
            if not left:
                return left
            right = other(left.tokens)
            errors = left.errors + right.errors
            if not right:
                return Result(None, right.tokens, left.line_ref, errors)
            value = as_tuple(left.value) + as_tuple(right.value)
            if isinstance(value, Tuple) and len(value) == 1:
                value = value[0]
            return Result(value, right.tokens, left.line_ref, errors)
        return Parser(p)

    def __rshift__(self, other: Callable[[Result[T], List[Token]], Result[Y]]) -> Parser[Y]:
        def p(tokens: List[Token]) -> Result[Y]:
            left = self(tokens)
            if not left:
                return left
            return other(left, tokens)
        return Parser(p)

    def __getitem__(self, index) -> Parser[list[T]]:
        #   [:] == any amount
        #   [1:] == 1 or more
        #   [:10] == up to 10
        #   [5] == precisely 5
        if isinstance(index, slice):
            min_count = index.start if index.start is not None else 0
            max_count = index.stop if index.stop is not None else 1000000000
        elif isinstance(index, int):
            min_count = index
            max_count = index
        else:
            raise TypeError("Invalid argument type.")
        def p(tokens: List[Token]) -> Result[list[T]]:
            result_list: list[T] = []
            errors_list: list[Error] = []
            cursor = tokens
            while len(result_list) < max_count and not is_eof(cursor):
                result = self(cursor)
                cursor = result.tokens
                if not result:
                    break
                result_list.append(result.value)
                errors_list.extend(result.errors)
            if len(result_list) < min_count:
                return Result.error("too few occurrences", cursor, tokens[0].line_ref)
            return Result(result_list, cursor, tokens[0].line_ref, [])
        return Parser(p)


def first_or_none(iterable):
    return next(iter(iterable), None)


def is_eof(tokens: List[Token]) -> bool:
    return tokens[0].kind == TokenKind.EOF


def to_nothing(result: Result, tokens: List[Token]) -> Result[Tuple]:
    return Result((), result.tokens, result.line_ref, result.errors)


def __str_of_kind(kind: TokenKind, w: Optional[str | List[str]]) -> Parser[str]:
    def p(tokens: List[Token]) -> Result[str]:
        match tokens:
            case [head, *tail] if head.kind == kind and (
                    w is None or head.value == w or (isinstance(w, list) and head.value in w)):
                return Result.ok(head.value, tail, head.line_ref)
        return Result.none(tokens, tokens[0].line_ref)
    return Parser(p)


def ident(w: Optional[str | List[str]] = None) -> Parser[str]:
    return __str_of_kind(TokenKind.IDENTIFIER, w)


def sym(w: Optional[str | List[str]] = None) -> Parser[str]:
    return __str_of_kind(TokenKind.SYMBOLS, w)


def imm(w: Optional[str] = None) -> Parser[str]:
    return Parser(lambda tokens: Result(w, tokens, tokens[0].line_ref, []))


def discard_ident(w: Optional[str | List[str]]) -> Parser[Tuple]:
    return ident(w) >> to_nothing


def discard_sym(w: Optional[str | List[str]]) -> Parser[Tuple]:
    return sym(w) >> to_nothing


def many(parser: Parser[T], skip: Optional[Callable[[List[Token]],Result]] = None) -> Parser[list[T]]:
    def p(tokens: List[Token]) -> Result[list[T]]:
        items = []
        errors = []
        line_ref = None
        while not is_eof(tokens):
            item = parser(tokens)
            errors += item.errors
            if line_ref is None:
                line_ref = item.line_ref
            if not item:
                if not skip:
                    break
                tokens_after = skip(tokens).tokens
                errors.append(Error(line_ref, "Skipped tokens"))
                tokens = tokens_after
            else:
                items.append(item.value)
                tokens = item.tokens
        return Result(items, tokens, tokens[0].line_ref if line_ref is None else line_ref, errors)
    return Parser(p)


def maybe(parser: Parser[T]) -> Parser[list[T]]:
    def p(tokens: List[Token]) -> Result[list[T]]:
        item = parser(tokens)
        if not item:
            return Result([], tokens, item.line_ref, item.errors)
        return Result([item.value], item.tokens, item.line_ref, item.errors)
    return Parser(p)


def block(parser: Parser[T]) -> Parser[T]:
    def p(tokens: List[Token]) -> Result[T]:
        index = 0
        indent = tokens[0].indent
        line = tokens[0].line_ref.line

        while index < len(tokens) and not tokens[index].kind == TokenKind.EOF:
            tk = tokens[index]
            if not tk or (tk.line_ref.line > line and tk.indent <= indent):
                break
            index += 1

        result = parser(tokens[:index] + [Token(TokenKind.EOF, "", 0, tokens[index].line_ref)])

        errors = []
        if not is_eof(result.tokens):
            errors = [Error(result.tokens[0].line_ref, "extra unexpected characters")]

        return Result(result.value, tokens[index:], result.line_ref, result.errors + errors)

    return Parser(p)


def delimited_list(parser: Parser[T], seperator: str|List[str]) -> Parser[list[T]]:
    def xlate(result: Result[Tuple[list[T], list[T]]], tokens: List[Token]) -> Result[list[T]]:
        items = result.value[0] + result.value[1]
        return Result(items, result.tokens, result.line_ref, result.errors)
    return (many(parser & discard_sym(seperator)) & maybe(parser)) >> xlate


def requires(left: Parser[T], right: Parser[Y], message: str) -> Parser[Y]:
    def p(tokens: List[Token]) -> Result[Y]:
        l = left(tokens)
        if not l:
            return Result(None, tokens, tokens[0].line_ref, [])
        r = right(l.tokens)
        errors = l.errors + r.errors
        if not r:
            if not errors:
                errors = [Error(l.tokens[0].line_ref, message)]
            return Result(None, r.tokens, r.line_ref, errors)
        return Result(r.value, r.tokens, r.line_ref, errors)
    return Parser(p)
