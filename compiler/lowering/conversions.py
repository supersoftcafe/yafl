"""Conversion-node insertion: make every implicit representation change explicit.

Generate never coerces — the converged AST is the absolute source of truth for
program correctness (docs/compiler-internals.md §2). This pass runs after
monomorphisation (every type is ground; a conversion inside a generic template
is undecidable before then) and walks the tree threading each sink's expected
type down to the value that flows into it, wrapping that value in a
`ConvertExpression` when a representation change is required. The DECISION is
`conversion.needs_conversion`, shared with `Expression.generate_to`'s
assertion — so anything this pass misses fails loudly at generate instead of
being silently converted.

Sinks threaded:
  - function/lambda bodies and `return` values → the return type
  - `let` / destructure RHS → the declared type / the targets' tuple type
  - call arguments → the callee's declared parameter types
  - match arms / ternary branches → the expected type (they share one slot)
  - enum construction args → the variant's field types
Recur back-edges need nothing extra: `[tail]` lowering runs after this pass, so
the recursive call's arguments are already boxed as ordinary call arguments.
"""
from __future__ import annotations

import dataclasses
import pyast.rewrite as rw

import pyast.statement as s
import pyast.expression as e
import pyast.match as m
import pyast.resolver as g
import pyast.typespec as t
from pyast.expression import conversion as cv


def insert_conversions(statements: list[s.Statement]) -> list[s.Statement]:
    resolver = g.ResolverRoot(statements)
    return [__convert_top_stmt(stmt, resolver) for stmt in statements]


def __convert_top_stmt(stmt: s.Statement, resolver: g.Resolver) -> s.Statement:
    if isinstance(stmt, s.FunctionStatement):
        if stmt.body is None:
            return stmt
        return rw.resolved(stmt.search_and_replace(resolver, __make_replace(stmt.return_type)), stmt)
    if isinstance(stmt, s.ClassStatement):
        # Each method needs a replace function that knows its own return type.
        new_stmts = [
            rw.resolved(inner.search_and_replace(resolver, __make_replace(inner.return_type)), inner)
            if isinstance(inner, s.FunctionStatement) else inner
            for inner in stmt.statements
        ]
        return dataclasses.replace(stmt, statements=new_stmts)
    if isinstance(stmt, s.LetStatement) and stmt.default_value is not None:
        return __convert_let(stmt, resolver)
    return stmt


def __make_replace(return_type: t.TypeSpec | None):
    """A search_and_replace visitor that boxes at every sink. `return_type` is
    the enclosing function's, used at ReturnStatement sites. search_and_replace
    is bottom-up, so children are already boxed when their parent is visited."""
    def replace(resolver: g.Resolver, thing):
        if isinstance(thing, s.FunctionStatement):
            # A nested function's body boxes against its OWN return type.
            if thing.body is not None and thing.return_type is not None:
                new_body = __convert_expr(thing.body, thing.return_type, resolver)
                if new_body is not thing.body:
                    return dataclasses.replace(thing, body=new_body)
            return rw.UNCHANGED
        if isinstance(thing, s.ReturnStatement):
            return __convert_return(thing, return_type, resolver)
        if isinstance(thing, s.DestructureStatement):
            return __convert_destructure(thing, resolver)
        if isinstance(thing, s.LetStatement):
            return __convert_let(thing, resolver)
        if isinstance(thing, e.CallExpression):
            return __convert_call_args(thing, resolver)
        if isinstance(thing, e.NewEnumExpression):
            return __convert_enum_args(thing, resolver)
        if isinstance(thing, e.LambdaExpression):
            return __convert_lambda(thing, resolver)
        if isinstance(thing, e.ConvertExpression):
            # ast_inline also inserts ConvertExpression (inlined returns). Recurse
            # into its inner so nested match arms / block values get boxed
            # against the target — no other entry point visits that position.
            return __recurse_conversion(thing, resolver)
        return rw.UNCHANGED
    return replace


def __recurse_conversion(expr: e.ConvertExpression, resolver: g.Resolver) -> e.Expression:
    inner_actual = expr.inner.get_type(resolver)
    if (inner_actual is not None
            and inner_actual.as_unique_id_str() is not None
            and inner_actual.as_unique_id_str() == expr.target.as_unique_id_str()):
        return expr
    new_inner = __convert_expr(expr.inner, expr.target, resolver)
    if new_inner is not expr.inner:
        return dataclasses.replace(expr, inner=new_inner)
    return expr


def __convert_return(stmt: s.ReturnStatement, return_type: t.TypeSpec | None,
                 resolver: g.Resolver) -> s.ReturnStatement:
    if return_type is None or stmt.value is None:
        return stmt
    new_value = __convert_expr(stmt.value, return_type, resolver)
    return dataclasses.replace(stmt, value=new_value) if new_value is not stmt.value else stmt


def __convert_let(stmt: s.LetStatement, resolver: g.Resolver) -> s.LetStatement:
    if stmt.default_value is None or stmt.declared_type is None:
        return stmt
    new_dv = __convert_expr(stmt.default_value, stmt.declared_type, resolver)
    return dataclasses.replace(stmt, default_value=new_dv) if new_dv is not stmt.default_value else stmt


def __convert_destructure(stmt: s.DestructureStatement, resolver: g.Resolver) -> s.DestructureStatement:
    # The RHS flows into the TARGETS' tuple type, which may be wider than the
    # value (`(s: String|None, n) = (None, 7)`, the shape a |>-lambda binds).
    if stmt.default_value is None:
        return stmt
    slot = stmt.get_type()
    if any(entry.type is None for entry in slot.entries):
        return __convert_let(stmt, resolver)
    new_dv = __convert_expr(stmt.default_value, slot, resolver)
    return dataclasses.replace(stmt, default_value=new_dv) if new_dv is not stmt.default_value else stmt


def __convert_call_args(expr: e.CallExpression, resolver: g.Resolver) -> e.CallExpression:
    func_type = expr.function.get_type(resolver)
    if not isinstance(func_type, t.CallableSpec) or not isinstance(expr.parameter, e.TupleExpression):
        return expr
    entries = func_type.parameters.entries
    if len(entries) != len(expr.parameter.expressions):
        return expr
    new_exprs = [
        dataclasses.replace(te, value=__convert_expr(te.value, entry.type, resolver))
        for te, entry in zip(expr.parameter.expressions, entries)
    ]
    if not any(ne.value is not oe.value for ne, oe in zip(new_exprs, expr.parameter.expressions)):
        return expr
    return dataclasses.replace(expr, parameter=dataclasses.replace(expr.parameter, expressions=new_exprs))


def __convert_enum_args(expr: e.NewEnumExpression, resolver: g.Resolver) -> e.NewEnumExpression:
    """Box each construction argument toward its variant field's declared type
    (mirrors the field lookup construct_enum_value performs when emitting)."""
    types = resolver.find_type(expr.root_spec_name)
    if len(types) != 1 or not isinstance(types[0].statement, s.EnumStatement):
        return expr
    root_stmt = types[0].statement
    root_spec = root_stmt._enum_spec
    if root_spec is None or expr.leaf_name not in root_spec.all_leaf_names:
        return expr
    leaf_idx = root_spec.all_leaf_names.index(expr.leaf_name)
    leaf_fields = t._collect_leaf_field_sets(root_stmt, [])[leaf_idx]
    by_name = {let.name: let.declared_type for let in leaf_fields}
    new_args = {fname: __convert_expr(fexpr, by_name.get(fname), resolver)
                for fname, fexpr in expr.field_args.items()}
    if all(new_args[k] is expr.field_args[k] for k in new_args):
        return expr
    return dataclasses.replace(expr, field_args=new_args)


def __convert_lambda(expr: e.LambdaExpression, resolver: g.Resolver) -> e.LambdaExpression:
    if expr.return_type is None:
        return expr
    nested = g.ResolverData(resolver, expr._find_locals)
    new_body = __convert_expr(expr.expression, expr.return_type.result, nested)
    return dataclasses.replace(expr, expression=new_body) if new_body is not expr.expression else expr


# ── scope helpers (get_type needs the bindings a position can see) ─────────

def __arm_scope(arm, subject_type, resolver: g.Resolver) -> g.Resolver:
    if not arm.name or arm.name == "_":
        return resolver
    # For a complex-enum subject the arm binds at the SUBJECT's (monomorphised)
    # type; arm.type_spec may still carry pre-generics placeholders. Mirrors
    # codegen's match binding.
    bound_type = subject_type if isinstance(subject_type, t.EnumSpec) \
                              else (arm.type_spec or subject_type)
    if bound_type is None:
        return resolver
    name, line_ref = arm.name, arm.line_ref

    def find(query: str, n=name, lr=line_ref, bt=bound_type):
        if g.name_matches(n, query):
            let = s.LetStatement(lr, n, None, {}, (), None, bt)
            return [g.Resolved(n, let, g.ResolvedScope.LOCAL)]
        return []
    return g.ResolverData(resolver, find)


def __block_scope(expr: e.BlockExpression, resolver: g.Resolver) -> g.Resolver:
    return g.ResolverData(resolver, expr._find_locals())


# ── the expected-type threading ─────────────────────────────────────────────

def __convert_expr(expr: e.Expression, expected_type: t.TypeSpec | None,
               resolver: g.Resolver) -> e.Expression:
    """Thread `expected_type` down to the value position(s) of `expr` and wrap
    where a representation change is needed (e.converted decides). Branch/merge
    nodes (block, match, ternary) push the type into each branch — all branches
    share one result slot at codegen, so each must produce the slot's type."""
    if expected_type is None:
        return expr
    if expr.get_type(resolver) is None:
        return expr

    if isinstance(expr, e.ConvertExpression):
        return __recurse_conversion(expr, resolver)

    if isinstance(expr, e.BlockExpression):
        nested = __block_scope(expr, resolver)
        new_value = __convert_expr(expr.value, expected_type, nested)
        if new_value is not expr.value:
            return dataclasses.replace(expr, value=new_value)
        return expr

    if isinstance(expr, m.MatchExpression):
        subject_type = expr.subject.get_type(resolver)
        new_arms = []
        for arm in expr.arms:
            arm_scope = __arm_scope(arm, subject_type, resolver)
            body = __convert_expr(arm.body, expected_type, arm_scope)
            new_arms.append(dataclasses.replace(arm, body=body) if body is not arm.body else arm)
        if any(na is not oa for na, oa in zip(new_arms, expr.arms)):
            return dataclasses.replace(expr, arms=new_arms)
        return expr

    if isinstance(expr, e.TernaryExpression):
        new_true = __convert_expr(expr.trueResult, expected_type, resolver)
        new_false = __convert_expr(expr.falseResult, expected_type, resolver)
        if new_true is not expr.trueResult or new_false is not expr.falseResult:
            return dataclasses.replace(expr, trueResult=new_true, falseResult=new_false)
        return expr

    if isinstance(expr, e.LambdaExpression) and isinstance(expected_type, t.CallableSpec):
        # A lambda in an argument slot whose declared callable returns wider
        # than the body produces: box the body toward the declared result.
        nested = g.ResolverData(resolver, expr._find_locals)
        new_body = __convert_expr(expr.expression, expected_type.result, nested)
        if new_body is not expr.expression:
            new_return_type = expr.return_type if expr.return_type is not None else expected_type
            return dataclasses.replace(expr, expression=new_body, return_type=new_return_type)
        return expr

    if (isinstance(expected_type, t.TupleSpec) and isinstance(expr, e.TupleExpression)
            and len(expected_type.entries) == len(expr.expressions)):
        # A tuple literal widens FIELD-WISE (nicer nodes than rebuilding the
        # whole tuple); a non-literal tuple value falls through to `converted`,
        # whose ConvertExpression rebuilds it at generate.
        new_exprs = [
            dataclasses.replace(te, value=__convert_expr(te.value, entry.type, resolver))
            if entry.type is not None else te
            for te, entry in zip(expr.expressions, expected_type.entries)
        ]
        if any(ne.value is not oe.value for ne, oe in zip(new_exprs, expr.expressions)):
            return dataclasses.replace(expr, expressions=new_exprs)
        return expr

    if (isinstance(expected_type, t.CombinationSpec) and isinstance(expr, e.TupleExpression)):
        # Tuple literal into a union holding a matching tuple variant
        # (cv.matching_tuple_variant — the shared match): widen the fields
        # toward the variant first, then box the whole into the union.
        actual = expr.get_type(resolver)
        if isinstance(actual, t.TupleSpec):
            variant = cv.matching_tuple_variant(actual, expected_type, resolver)
            if variant is not None:
                widened = __convert_expr(expr, variant, resolver)
                return e.ConvertExpression(expr.line_ref, widened, expected_type)
        return expr

    return e.converted(expr, expected_type, resolver)
