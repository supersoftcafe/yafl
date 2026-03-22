"""Lower implicit union boxing/widening into explicit BoxExpression/WideExpression nodes.

Runs after type stabilisation and generics/strings/integers lowering, before lambda lifting.
By this point every type is fully resolved; we can compare actual vs expected types and insert
the conversion nodes that codegen will later emit as tag-packing or null-check sequences.

Sites handled:
  - ReturnStatement values (against the enclosing function's return type)
  - LetStatement default values (against the declared type)
  - CallExpression arguments (against the callee's parameter types)
  - LambdaExpression bodies (against the lambda's own return type)
"""
from __future__ import annotations

import dataclasses

import pyast.statement as s
import pyast.expression as e
import pyast.resolver as g
import pyast.typespec as t


def insert_boxing(statements: list[s.Statement]) -> list[s.Statement]:
    resolver = g.ResolverRoot(statements)
    return [__box_top_stmt(stmt, resolver) for stmt in statements]


def __box_top_stmt(stmt: s.Statement, resolver: g.Resolver) -> s.Statement:
    if isinstance(stmt, s.FunctionStatement):
        return stmt.search_and_replace(resolver, __make_replace(stmt.return_type))
    if isinstance(stmt, s.ClassStatement):
        # Each method needs a replace function that knows its own return type.
        new_stmts = [
            inner.search_and_replace(resolver, __make_replace(inner.return_type))
            if isinstance(inner, s.FunctionStatement) else inner
            for inner in stmt.statements
        ]
        return dataclasses.replace(stmt, statements=new_stmts)
    if isinstance(stmt, s.LetStatement) and stmt.default_value is not None and stmt.declared_type is not None:
        new_dv = __box_expr(stmt.default_value, stmt.declared_type, resolver)
        return dataclasses.replace(stmt, default_value=new_dv) if new_dv is not stmt.default_value else stmt
    return stmt


def __make_replace(return_type: t.TypeSpec | None):
    """Return a search_and_replace replace-function that boxes at all relevant sites.

    return_type is the enclosing function's declared return type, used when the replace
    function encounters a ReturnStatement.
    """
    def replace(resolver: g.Resolver, thing):
        if isinstance(thing, s.ReturnStatement):
            return __box_return(thing, return_type, resolver)
        if isinstance(thing, s.LetStatement):
            return __box_let(thing, resolver)
        if isinstance(thing, e.CallExpression):
            return __box_call_args(thing, resolver)
        if isinstance(thing, e.LambdaExpression):
            return __box_lambda(thing, resolver)
        return thing
    return replace


def __box_return(stmt: s.ReturnStatement, return_type: t.TypeSpec | None, resolver: g.Resolver) -> s.ReturnStatement:
    if return_type is None:
        return stmt
    new_value = __box_expr(stmt.value, return_type, resolver)
    return dataclasses.replace(stmt, value=new_value) if new_value is not stmt.value else stmt


def __box_let(stmt: s.LetStatement, resolver: g.Resolver) -> s.LetStatement:
    if stmt.default_value is None or stmt.declared_type is None:
        return stmt
    new_dv = __box_expr(stmt.default_value, stmt.declared_type, resolver)
    return dataclasses.replace(stmt, default_value=new_dv) if new_dv is not stmt.default_value else stmt


def __box_call_args(expr: e.CallExpression, resolver: g.Resolver) -> e.CallExpression:
    func_type = expr.function.get_type(resolver)
    if not isinstance(func_type, t.CallableSpec) or not isinstance(expr.parameter, e.TupleExpression):
        return expr
    entries = func_type.parameters.entries
    new_exprs = [
        dataclasses.replace(te, value=__box_expr(te.value, entry.type, resolver))
        for te, entry in zip(expr.parameter.expressions, entries)
    ]
    if not any(ne.value is not oe.value for ne, oe in zip(new_exprs, expr.parameter.expressions)):
        return expr
    return dataclasses.replace(expr, parameter=dataclasses.replace(expr.parameter, expressions=new_exprs))


def __box_lambda(expr: e.LambdaExpression, resolver: g.Resolver) -> e.LambdaExpression:
    if expr.return_type is None:
        return expr
    new_body = __box_expr(expr.expression, expr.return_type.result, resolver)
    return dataclasses.replace(expr, expression=new_body) if new_body is not expr.expression else expr


def __box_expr(expr: e.Expression, expected_type: t.TypeSpec | None, resolver: g.Resolver) -> e.Expression:
    """Wrap expr in BoxExpression or WideExpression if its type needs widening to a union type."""
    if not isinstance(expected_type, t.CombinationSpec):
        return expr
    actual_type = expr.get_type(resolver)
    if actual_type is None:
        return expr
    if isinstance(expr, e.TupleExpression) and isinstance(actual_type, t.TupleSpec):
        return __box_tuple_into_union(expr, actual_type, expected_type, resolver)
    if isinstance(actual_type, t.CombinationSpec):
        return __widen_union(expr, actual_type, expected_type, resolver)
    return __box_singleton_variant(expr, actual_type, expected_type)


def __box_tuple_into_union(
        expr: e.TupleExpression, actual_type: t.TupleSpec,
        expected_type: t.CombinationSpec, resolver: g.Resolver) -> e.Expression:
    """Box a tuple literal into a union that contains a matching tuple variant."""
    matching = [v for v in expected_type.types
                if isinstance(v, t.TupleSpec)
                and v.trivially_assignable_from(resolver, actual_type) is True]
    if len(matching) != 1:
        return expr
    variant = matching[0]
    new_exprs = [
        dataclasses.replace(te, value=__box_expr(te.value, entry.type, resolver))
        for te, entry in zip(expr.expressions, variant.entries)
    ]
    return e.BoxExpression(expr.line_ref, dataclasses.replace(expr, expressions=new_exprs), expected_type)


def __widen_union(
        expr: e.Expression, actual_type: t.CombinationSpec,
        expected_type: t.CombinationSpec, resolver: g.Resolver) -> e.Expression:
    """Widen a union value to a wider union type."""
    if (actual_type.as_unique_id_str() != expected_type.as_unique_id_str()
            and expected_type.trivially_assignable_from(resolver, actual_type) is True):
        return e.WideExpression(expr.line_ref, expr, actual_type, expected_type)
    return expr


def __box_singleton_variant(
        expr: e.Expression, actual_type: t.TypeSpec,
        expected_type: t.CombinationSpec) -> e.Expression:
    """Box a non-union value into a union that contains it as a direct variant."""
    uid = actual_type.as_unique_id_str()
    if uid is not None and any(v.as_unique_id_str() == uid for v in expected_type.types):
        return e.BoxExpression(expr.line_ref, expr, expected_type)
    return expr
