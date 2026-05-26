"""`[lazy]` let lowering.

For each `let [lazy] x: T = expr` (local + global), this pass:

  1. Wraps the RHS in a `() => expr` LambdaExpression so the subsequent
     lambdas pass converts it to a closure class + NewExpression.  The
     resulting default_value is a fun_t-valued expression.

  2. Rewrites every NamedExpression that resolves to the let into a
     LazyExpression at the same source location.  References then go
     through `lazy_fetch$<irmangle>` instead of reading the let's slot
     directly.

  3. LetStatement.generate (for `[lazy]` lets) allocates a Lazy$<irmangle>
     stub at the let's name, fills `flag = NULL` and `closure = <fun_t>`.

The pass runs after compile() has uniquified local names, so a single
string-equality match on `name` is enough to identify references — no
need to thread scope information.

Block-local stub allocation hoisting in `BlockExpression.generate` lets
two `[lazy]` lets in the same block forward-reference each other.
Forward references from a `[lazy]` body to a *non-lazy* let declared
later in the same block remain broken — `check_lazy_forward_refs`
turns that into a compile error rather than a runtime crash.
"""
from __future__ import annotations

import dataclasses
from typing import Any, Callable

import pyast.expression as e
import pyast.statement as s
import pyast.resolver as g
import pyast.typespec as t
from parsing.parselib import Error


def _make_empty_lambda_params(line_ref) -> s.DestructureStatement:
    return s.DestructureStatement(
        line_ref     = line_ref,
        name         = "_",
        imports      = s.ImportGroup(tuple()),
        attributes   = {},
        type_params  = (),
        default_value= None,
        declared_type= t.TupleSpec(line_ref, []),
        targets      = [],
    )


def check_lazy_forward_refs(statements: list[s.Statement]) -> list[Error]:
    """Detect `[lazy]` bodies that forward-reference a non-lazy let in
    the same block.  Such cases can't be made to work via stub-allocation
    hoisting (only `[lazy]` lets are hoisted; a non-lazy let's slot is
    written by its RHS evaluation in textual order), so the closure
    constructed at the lazy let's textual position captures an
    uninitialised value and the program crashes at force.  Turn it into
    a compile error with an actionable message instead.

    Cross-block forward refs are *not* errors — an inner block's
    `[lazy]` body referencing an outer non-lazy let works as expected
    (the outer let was already initialised before the inner block
    entered)."""
    errors: list[Error] = []

    def _check_block(stmts: list[s.Statement]) -> None:
        decl_at: dict[str, tuple[int, bool]] = {}
        for i, stmt in enumerate(stmts):
            if isinstance(stmt, s.LetStatement):
                for sub in stmt.flatten():
                    decl_at[sub.name] = (i, sub.is_deferred_init())

        for i, stmt in enumerate(stmts):
            if (isinstance(stmt, s.LetStatement)
                    and stmt.is_deferred_init()
                    and stmt.default_value is not None):
                seen: set[str] = set()
                def _check_ref(_resolver: g.Resolver, thing: Any) -> Any:
                    if isinstance(thing, e.NamedExpression):
                        info = decl_at.get(thing.name)
                        if info is not None and thing.name not in seen:
                            decl_idx, decl_is_lazy = info
                            if decl_idx > i and not decl_is_lazy:
                                seen.add(thing.name)
                                errors.append(Error(
                                    stmt.line_ref,
                                    f"[lazy] let '{stmt.name}' forward-references "
                                    f"non-lazy let '{thing.name}'. "
                                    f"Mark '{thing.name}' as [lazy], or move its "
                                    f"declaration before '{stmt.name}'."))
                    return thing
                stmt.default_value.search_and_replace(g.ResolverRoot([]), _check_ref)

    def _walk(_resolver: g.Resolver, node: Any) -> Any:
        if isinstance(node, e.BlockExpression):
            _check_block(node.statements)
        return node

    for stmt in statements:
        stmt.search_and_replace(g.ResolverRoot(statements), _walk)
    return errors


def _is_trivial_expr(expr: e.Expression | None, resolver: g.Resolver) -> bool:
    """AST-level "trivial init" predicate — an expression that
    `LetStatement.global_codegen` can emit as a direct C static
    without going through the lazy-thunk framework.

    Covers:
      * Numeric / string literals — emit as the literal's RParam.
      * `CallExpression(NamedExpression(ClassName), TupleExpression(literals…))`
        — class instantiation with literal args, emitted as a static
        struct of those field values.
      * `TupleExpression` of trivials — emitted as a tuple struct.

    Anything else (variable references, function calls returning
    non-class values, nested constructors) auto-promotes to `[lazy]`
    and runs through the lazy-thunk framework at first force."""
    if expr is None:
        return False
    if isinstance(expr, (e.IntegerExpression, e.FloatExpression, e.StringExpression)):
        return True
    if isinstance(expr, e.TupleExpression):
        return all(_is_trivial_expr(en.value, resolver) for en in expr.expressions)
    if isinstance(expr, e.CallExpression) and isinstance(expr.function, e.NamedExpression):
        # Constructor call to a known class with literal args — the
        # global_codegen pattern-match emits this as a static struct.
        found = resolver.find_type(expr.function.name)
        if len(found) == 1 and isinstance(found[0].statement, s.ClassStatement):
            return _is_trivial_expr(expr.parameter, resolver)
    return False


def _is_literal_init(stmt: s.LetStatement, resolver: g.Resolver) -> bool:
    return _is_trivial_expr(stmt.default_value, resolver)


def _promote_non_trivial_globals(statements: list[s.Statement]) -> list[s.Statement]:
    """Auto-mark every top-level let whose init can't be emitted as a
    direct C static (per `_is_trivial_expr`) as `[lazy]`, so it routes
    through the lazy-thunk framework instead."""
    resolver = g.ResolverRoot(statements)
    out: list[s.Statement] = []
    for stmt in statements:
        if (isinstance(stmt, s.LetStatement)
                and not stmt.is_deferred_init()
                and stmt.default_value is not None
                and stmt.declared_type is not None
                and not _is_literal_init(stmt, resolver)):
            new_attrs = dict(stmt.attributes)
            new_attrs["lazy"] = None
            stmt = dataclasses.replace(stmt, attributes=new_attrs)
        out.append(stmt)
    return out


def lower_lazy_lets(statements: list[s.Statement]) -> list[s.Statement]:
    """Rewrite every `[lazy]` let and its reference sites.  Auto-promotes
    non-literal top-level lets to `[lazy]` so all non-trivial globals
    run through the same framework as user-marked lazies.

    Returns a new statement list (input is not mutated)."""

    statements = _promote_non_trivial_globals(statements)

    # Pass 1 — collect the unique name + declared type of every `[lazy]` let
    # reachable from `statements`.  After compile() local names are
    # uniquified (`name@hash`), so the global dictionary suffices.
    lazy_lets: dict[str, t.TypeSpec] = {}

    def _collect(_resolver: g.Resolver, thing: Any) -> Any:
        if (isinstance(thing, s.LetStatement)
                and thing.is_deferred_init()
                and thing.declared_type is not None):
            lazy_lets[thing.name] = thing.declared_type
        return thing

    root = g.ResolverRoot(statements)
    for stmt in statements:
        stmt.search_and_replace(root, _collect)

    if not lazy_lets:
        return statements

    # Pass 2 — rewrite references to LazyExpression and wrap each `[lazy]`
    # let's RHS in a `()=>expr` lambda.  Bottom-up traversal: inner
    # NamedExpressions are rewritten before the enclosing LetStatement is
    # visited, so by the time we wrap the let's RHS the references it
    # contained have already been converted (matters for lazies that read
    # other lazies).
    def _rewrite(resolver: g.Resolver, thing: Any) -> Any:
        if isinstance(thing, e.NamedExpression) and thing.name in lazy_lets:
            return e.LazyExpression(
                line_ref    = thing.line_ref,
                stub_name   = thing.name,
                target_type = lazy_lets[thing.name],
            )
        if (isinstance(thing, s.LetStatement)
                and thing.is_deferred_init()
                and thing.default_value is not None
                and not isinstance(thing.default_value, e.LambdaExpression)):
            T = thing.declared_type
            assert T is not None  # check() guarantees this
            wrapped = e.LambdaExpression(
                line_ref    = thing.line_ref,
                parameters  = _make_empty_lambda_params(thing.line_ref),
                expression  = thing.default_value,
                return_type = t.CallableSpec(thing.line_ref,
                                             t.TupleSpec(thing.line_ref, []),
                                             T),
            )
            return dataclasses.replace(thing, default_value=wrapped)
        return thing

    return [stmt.search_and_replace(root, _rewrite) for stmt in statements]
