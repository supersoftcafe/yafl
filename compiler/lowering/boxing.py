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
import pyast.match as m
import pyast.resolver as g
import pyast.typespec as t


def insert_boxing(statements: list[s.Statement]) -> list[s.Statement]:
    resolver = g.ResolverRoot(statements)
    return [__box_top_stmt(stmt, resolver) for stmt in statements]


def __box_top_stmt(stmt: s.Statement, resolver: g.Resolver) -> s.Statement:
    if isinstance(stmt, s.FunctionStatement):
        if stmt.body is None:
            return stmt
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
        if isinstance(thing, s.FunctionStatement):
            # Box the body's final value against this function's own return type.
            # search_and_replace calls replace(nested_resolver, fn) after recursing into
            # the body, so resolver already includes the function's parameters.
            if thing.body is not None and thing.return_type is not None:
                new_body = __box_expr(thing.body, thing.return_type, resolver)
                if new_body is not thing.body:
                    return dataclasses.replace(thing, body=new_body)
            return thing
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


def __box_match_arms(expr: "m.MatchExpression", expected_type: t.TypeSpec,
                     resolver: g.Resolver) -> "m.MatchExpression":
    """Box each arm body against the expression's expected type so every arm
    produces a value of the same C representation at codegen time.

    An arm whose pattern binds a name to a typed variant needs that name in
    the resolver so the arm body's types resolve correctly during boxing —
    mirrors MatchArm.__find_bound.
    """
    subject_type = expr.subject.get_type(resolver)
    new_arms = []
    any_changed = False
    for arm in expr.arms:
        arm_resolver = __arm_scope(arm, subject_type, resolver)
        boxed_body = __box_expr(arm.body, expected_type, arm_resolver)
        if boxed_body is not arm.body:
            new_arms.append(dataclasses.replace(arm, body=boxed_body))
            any_changed = True
        else:
            new_arms.append(arm)
    return dataclasses.replace(expr, arms=new_arms) if any_changed else expr


def __arm_scope(arm, subject_type, resolver: g.Resolver) -> g.Resolver:
    """Return a resolver that knows about the arm's bound variable (if any)."""
    if not arm.name or arm.name == "_":
        return resolver
    bound_type = arm.type_spec if arm.type_spec is not None else subject_type
    if bound_type is None:
        return resolver
    name = arm.name
    line_ref = arm.line_ref

    def find(names: set[str], n=name, lr=line_ref, bt=bound_type):
        if g.match_names(n, names):
            let = s.LetStatement(lr, n, None, {}, (), None, bt)
            return [g.Resolved(n, let, g.ResolvedScope.LOCAL)]
        return []
    return g.ResolverData(resolver, find)


def __box_tuple_field_widen(
        expr: e.TupleExpression, actual_type: t.TupleSpec,
        expected_type: t.TupleSpec, resolver: g.Resolver) -> e.Expression:
    """Recursively box each field of a tuple literal so fields whose actual type
    is narrower than the expected tuple field type get widened.

    Unlike __box_tuple_into_union (tuple → union-containing-tuple), this
    handles tuple → wider tuple where one or more fields need widening.
    """
    if len(expected_type.entries) != len(expr.expressions):
        return expr
    new_exprs = []
    any_changed = False
    for te, expected_entry in zip(expr.expressions, expected_type.entries):
        if expected_entry.type is None:
            new_exprs.append(te)
            continue
        new_value = __box_expr(te.value, expected_entry.type, resolver)
        if new_value is not te.value:
            any_changed = True
            new_exprs.append(dataclasses.replace(te, value=new_value))
        else:
            new_exprs.append(te)
    return dataclasses.replace(expr, expressions=new_exprs) if any_changed else expr


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


def __block_scope(expr: e.BlockExpression, resolver: g.Resolver) -> g.Resolver:
    lets = [(let.name, let.line_ref, let.declared_type)
            for x in expr.statements
            if isinstance(x, s.LetStatement)
            for let in x.flatten()]

    def find(names: set[str], bindings=lets):
        return [g.Resolved(n, s.LetStatement(lr, n, None, {}, (), None, dt), g.ResolvedScope.LOCAL)
                for n, lr, dt in bindings
                if g.match_names(n, names)]
    return g.ResolverData(resolver, find)


def __box_expr(expr: e.Expression, expected_type: t.TypeSpec | None, resolver: g.Resolver) -> e.Expression:
    """Wrap expr in BoxExpression or WideExpression if its type needs widening
    to match the expected type.

    When `expr` is a MatchExpression or TernaryExpression, the expected type is
    propagated into each branch so branches with narrower types get boxed
    individually; this matters at codegen time because all branches share one
    result slot whose C type must be uniform.
    """
    if expected_type is None:
        return expr
    actual_type = expr.get_type(resolver)
    if actual_type is None:
        return expr

    # BlockExpression: box the final value against the expected type; statements box themselves.
    if isinstance(expr, e.BlockExpression):
        nested = __block_scope(expr, resolver)
        new_value = __box_expr(expr.value, expected_type, nested)
        if new_value is not expr.value:
            return dataclasses.replace(expr, value=new_value)
        return expr

    # Match expressions: box each arm body against the expected type.
    if isinstance(expr, m.MatchExpression):
        expr = __box_match_arms(expr, expected_type, resolver)
        actual_type = expr.get_type(resolver)
        if actual_type is None:
            return expr

    # Ternary: box both branches against the expected type.
    if isinstance(expr, e.TernaryExpression):
        new_true  = __box_expr(expr.trueResult,  expected_type, resolver)
        new_false = __box_expr(expr.falseResult, expected_type, resolver)
        if new_true is not expr.trueResult or new_false is not expr.falseResult:
            expr = dataclasses.replace(expr, trueResult=new_true, falseResult=new_false)
        actual_type = expr.get_type(resolver)
        if actual_type is None:
            return expr

    # Lambda: when passed to a call site whose declared callable has a
    # wider return type than the lambda's body produces, box the body
    # against that wider return type. Without this, `(x) => (io, s)` in
    # an arg slot declared `(:IO, :T): (io: IO, v: T|IOError)` loses the
    # widening to `String|IOError` and the call check rejects it.
    if isinstance(expr, e.LambdaExpression) and isinstance(expected_type, t.CallableSpec):
        nested_resolver = g.ResolverData(resolver, expr._find_locals)
        new_body = __box_expr(expr.expression, expected_type.result, nested_resolver)
        if new_body is not expr.expression:
            # Keep the lambda's return_type but widen via the new body; if
            # no return_type was declared, carry the expected_type forward.
            new_return_type = expr.return_type if expr.return_type is not None else expected_type
            return dataclasses.replace(expr, expression=new_body, return_type=new_return_type)
        return expr

    if isinstance(expected_type, t.TupleSpec):
        if isinstance(expr, e.TupleExpression) and isinstance(actual_type, t.TupleSpec):
            return __box_tuple_field_widen(expr, actual_type, expected_type, resolver)
        return expr

    if not isinstance(expected_type, t.CombinationSpec):
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
