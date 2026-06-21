from __future__ import annotations

from typing import Callable, Any, ClassVar
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


_INT_WIDTHS = {"int8": 8, "int16": 16, "int32": 32, "int64": 64}
_FLOAT_WIDTHS = {"float32": 32, "float64": 64}


def _resolve_numeric_precision(expected: t.TypeSpec | None, resolver: g.Resolver,
                               widths: dict[str, int]) -> int:
    """Bit-width of `expected` if it is (or aliases) one of `widths`' builtins,
    else 0. Peels a single typealias layer (`System::Int32` -> `int32`) by name
    lookup — deliberately *not* via `.compile`, so it never spawns globals or
    recurses into generic instantiation."""
    if isinstance(expected, t.NamedSpec):
        found = resolver.find_type(expected.name)
        if len(found) == 1 and isinstance(found[0].statement, s.TypeAliasStatement):
            expected = found[0].statement.type
    if isinstance(expected, t.BuiltinSpec):
        return widths.get(expected.type_name, 0)
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
class _NumericLiteral(Expression):
    """A numeric literal. `precision == 0` means *unspecified*: the literal
    defaults to the wide builtin (`bigint` / `float64`) but is narrowed to its
    context by `compile`. An explicit suffix (`i32`, `f32`, ...) gives a
    non-zero precision and is authoritative — never re-narrowed."""
    value: int | float
    precision: int = 0

    # Subclass contract.
    _KIND: ClassVar[str]               # builtin family: "int" / "float"
    _WIDE: ClassVar[str]               # builtin used when precision == 0
    _WIDTHS: ClassVar[dict[str, int]]  # narrowable builtin name -> bit width

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        name = self._WIDE if self.precision == 0 else f"{self._KIND}{self.precision}"
        return t.BuiltinSpec(self.line_ref, name)

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement]]:
        # Context-type an unsuffixed literal: a bare `0` / `1.5` flowing into an
        # `Int32` / `Float32` slot adopts that width, so the user need not spell
        # it. Explicit suffixes (precision != 0) are never overridden, and a
        # context of the wrong family (or none) is ignored — a genuine mismatch
        # is caught by the assignability check.
        if self.precision == 0:
            prec = _resolve_numeric_precision(expected_type, resolver, self._WIDTHS)
            if prec:
                return dataclasses.replace(self, precision=prec), []
        return self, []

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        return []

    def _emit(self) -> cg_p.RParam:
        raise NotImplementedError()

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        return g.OperationBundle((), (), self._emit())


@dataclass
class IntegerExpression(_NumericLiteral):
    _KIND = "int"
    _WIDE = "bigint"
    _WIDTHS = _INT_WIDTHS

    def _emit(self) -> cg_p.RParam:
        # precision 0 -> bigint in codegen (lowered to a heap value by integers.py).
        return cg_p.Integer(self.value, self.precision)


@dataclass
class FloatExpression(_NumericLiteral):
    _KIND = "float"
    _WIDE = "float64"
    _WIDTHS = _FLOAT_WIDTHS

    def _emit(self) -> cg_p.RParam:
        # precision 0 -> float64, the natural machine default (no lowering needed).
        return cg_p.Float(self.value, self.precision or 64)



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



