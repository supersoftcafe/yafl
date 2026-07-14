from __future__ import annotations

from typing import Callable, Any, ClassVar
import dataclasses
import pyast.rewrite as rw
from dataclasses import dataclass, field
from functools import reduce

from langtools import checked_cast
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


@dataclass
class StringExpression(Expression):
    value: str

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        return t.BuiltinSpec(self.line_ref, "str")

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement]]:
        # A literal owns its conversion to the receiver — its only case is
        # boxing into a union slot (`"x"` into `String|None`).
        from pyast.expression.conversion import converted
        return converted(self, expected_type, resolver), []

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
        # RULED (2026-07-04): a literal's type comes from its SPELLING alone —
        # 37 is Int, 37i32 is Int32, 12.5 is Float64, 12.5f32 is Float32, and
        # a char literal is an Int32 literal. No context narrowing, no
        # conversion: type what you mean. (Superseded machinery: contextual
        # width adoption, f238a66; literal second phase, same-day.)
        # The one conversion a literal owns is boxing into a union slot
        # (`7` into `Int|None`) — a representation change, not a re-typing.
        from pyast.expression.conversion import converted
        return converted(self, expected_type, resolver), []

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
        # Boxing into a union slot is the one conversion a literal owns.
        from pyast.expression.conversion import converted
        return converted(self, expected_type, resolver), []

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        return []

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        # `bool` lowers to Int(8); a literal is just 1 or 0.
        xexpr = cg_p.Integer(1 if self.value else 0, 8)
        return g.OperationBundle( (), (), xexpr )



@dataclass
class RegexExpression(Expression):
    """A `re"..."` literal, RAW pattern text. Exists only between parse and
    the interning pass (lowering/regexes.py), which validates the pattern at
    compile time and rewrites every use into a reference to a shared
    per-pattern `$regexes::` global — one Regex per distinct pattern, built
    once. Reaching compile/check means the pass did not run."""
    pattern: str

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        return None

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement]]:
        return self, []

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        return [Error(self.line_ref, "internal: regex literal was not lowered (lowering/regexes.py)")]


@dataclass
class NothingExpression(Expression):
    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,Any],Any]) -> Expression:
        return replace(resolver, self)

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        return None

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement]]:
        return self, []

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        return []

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        return g.OperationBundle()





def is_literal_value(expr) -> bool:
    """A value with no captures, no effects and no evaluation order.

    THE shared definition: both `[const]` (lets.py) and the field/parameter
    default rule (typespec/specs.py) mean exactly this by "literal", and a
    default is cloned into every site that omits the field, so the two must
    not drift apart.

    A TUPLE of literals is itself one — nothing is captured, nothing is
    evaluated. Its base case is `()`, the unit value, which is what `None` is:
    that makes `parent: Node|None = None` (the most natural default there is)
    expressible, via the `[const] None` the stdlib declares."""
    from pyast.expression.tuple_expr import TupleExpression
    expr = strip_conversions(expr)
    if isinstance(expr, TupleExpression):
        return all(not en.spread and is_literal_value(en.value)
                   for en in expr.expressions)
    return isinstance(expr, (IntegerExpression, FloatExpression,
                             StringExpression, BoolExpression,
                             NothingExpression))


def strip_conversions(expr):
    """See through inserted conversions to the value underneath.

    By check time a default has been through the compile fixpoint, which boxes
    it toward its declared slot (`None` into `Node|None` becomes a
    ConvertExpression). A conversion of a constant is still a constant — same
    value, different representation — so the literal rules look through it."""
    from pyast.expression.conversion import ConvertExpression
    while isinstance(expr, ConvertExpression):
        expr = expr.inner
    return expr
