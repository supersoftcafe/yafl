from __future__ import annotations

from typing import Callable, Any
import dataclasses
import random
from dataclasses import dataclass, field
from functools import reduce

from langtools import cast
from parsing.tokenizer import LineRef
from parsing.parselib import Error

import codegen.ops as cg_o
import codegen.param as cg_p
import codegen.typedecl as cg_t

import pyast.resolver as g
import pyast.statement as s
import pyast.typespec as t
import pyast.utils as u
from pyast.expression.base import Expression


_INT_PRECISION = {"int8": 8, "int16": 16, "int32": 32, "int64": 64}


def _resolve_int_precision(expected: t.TypeSpec | None, resolver: g.Resolver) -> int:
    """Bit-width of `expected` if it is (or aliases) a fixed-width integer
    builtin, else 0. Peels a single typealias layer (`System::Int32` ->
    `int32`) by name lookup — deliberately *not* via `.compile`, so it never
    spawns globals or recurses into generic instantiation."""
    if isinstance(expected, t.NamedSpec):
        found = resolver.find_type(expected.name)
        if len(found) == 1 and isinstance(found[0].statement, s.TypeAliasStatement):
            expected = found[0].statement.type
    if isinstance(expected, t.BuiltinSpec):
        return _INT_PRECISION.get(expected.type_name, 0)
    return 0


@dataclass
class StringExpression(Expression):
    value: str

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        return t.BuiltinSpec(self.line_ref, "str")

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement]]:
        return self, []

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        return []

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        xexpr = cg_p.String(self.value)
        return g.OperationBundle( (), (), xexpr )



@dataclass
class IntegerExpression(Expression):
    value: int
    precision: int = 0

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        return t.BuiltinSpec(self.line_ref, f"int{self.precision}" if self.precision else "bigint")

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement]]:
        # Context-type an unsuffixed literal: a bare `0` flowing into an
        # `Int32` slot becomes `0i32`, so the user need not write the width.
        # An explicit `i32`/`i64` suffix (precision != 0) is authoritative and
        # never overridden. Only a concrete fixed-width integer builtin is
        # adopted — `bigint` (precision 0) leaves the literal unchanged, and
        # non-integer expected types are ignored (a genuine mismatch is caught
        # by the assignability check). The resolution is pure: it peels a
        # typealias (`System::Int32`) to its builtin without spawning work.
        if self.precision == 0:
            prec = _resolve_int_precision(expected_type, resolver)
            if prec:
                return dataclasses.replace(self, precision=prec), []
        return self, []

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        return []

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        xexpr = cg_p.Integer(self.value, self.precision)
        return g.OperationBundle( (), (), xexpr )



@dataclass
class FloatExpression(Expression):
    value: float
    precision: int = 64

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        return t.BuiltinSpec(self.line_ref, f"float{self.precision}")

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement]]:
        return self, []

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        return []

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        xexpr = cg_p.Float(self.value, self.precision)
        return g.OperationBundle( (), (), xexpr )



@dataclass
class BoolExpression(Expression):
    value: bool

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        return t.BuiltinSpec(self.line_ref, "bool")

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement]]:
        return self, []

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        return []

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        # `bool` lowers to Int(8); a literal is just 1 or 0.
        xexpr = cg_p.Integer(1 if self.value else 0, 8)
        return g.OperationBundle( (), (), xexpr )



@dataclass
class NothingExpression(Expression):
    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,Any],Any]) -> Expression:
        return cast(Expression, replace(resolver, self))

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        return None

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement]]:
        return self, []

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        return []

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        return g.OperationBundle()



