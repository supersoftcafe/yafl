"""`[tail]` self-recursion → loop lowering.

For a `[tail]`-marked function that is self-recursive with *every* self-call in
tail position, wrap the body in a `LoopExpression` and rewrite each tail
self-call into a `RecurExpression`, then strip the `[tail]` attribute. The loop
becomes a real back-edge in the generated IR, so the function compiles to a
constant-stack loop. Sync functions become plain loops; async functions become
loops *inside* the async state machine — async lowering promotes the
loop-carried vars into the task-heap state across suspensions, and the loop head
(in the pre-first-suspend block) is reachable from the back-edge. There is no
trampoline.

Applies to top-level *and* nested functions. Runs before inlining / closure
conversion, while every self-call is still a direct, name-resolved call, so the
recursion can be turned into a loop while it is detectable. A nested `[tail]`
function that captures outer variables is later closure-converted as usual; the
`LoopExpression` survives that (it tracks renames through `search_and_replace`
and its labels are function-local), so the captured state lives on the closure
and the loop-carried params stay a constant-stack back-edge.

Union widening is no longer an AST pass, so this lowering has no ordering
dependency on it: a `[tail]` body's non-recursive exits are coerced to the
function's return type when the `LoopExpression` generates its body (it threads
the return type down via `generate_to`), and the recursive call (now a
`RecurExpression`) coerces its arguments to the parameter types at the back-edge.

A `[tail]` function that is not self-recursive, or has a self-call in a non-tail
position, is a hard error — `[tail]` asserts "I am a tail-recursive loop", and
an unconverted self-call would silently lose that guarantee. A self-call reaching
this function from inside a nested lambda is a normal recursive call, not a tail
call, and is ignored.
"""
from __future__ import annotations

import dataclasses

from parsing.parselib import Error

import pyast.expression as e
import pyast.match as m
import pyast.statement as s
import pyast.resolver as g


def lower_tail_loops(statements: list[s.Statement], resolver: g.Resolver) -> tuple[list[s.Statement], list[Error]]:
    errors: list[Error] = []
    lowered = [_transform(stmt, resolver, errors) for stmt in statements]
    return lowered, errors


def _transform(stmt: s.Statement, resolver: g.Resolver, errors: list[Error]) -> s.Statement:
    # Recurse into nested functions and class methods first (bottom-up), so a
    # `[tail]` function nested inside another is lowered too.
    if isinstance(stmt, s.FunctionStatement) and isinstance(stmt.body, e.BlockExpression):
        stmt = dataclasses.replace(stmt, body=dataclasses.replace(
            stmt.body,
            statements=[_transform(st, resolver, errors) for st in stmt.body.statements]))
    elif isinstance(stmt, s.ClassStatement):
        return dataclasses.replace(stmt,
            statements=[_transform(m_, resolver, errors) for m_ in stmt.statements])

    if not (isinstance(stmt, s.FunctionStatement)
            and "tail" in stmt.attributes
            and stmt.body is not None):
        return stmt

    params = tuple(e.NamedExpression(stmt.line_ref, prm.name) for prm in stmt.parameters.targets)

    def is_self_call(expr: object) -> bool:
        return (isinstance(expr, e.CallExpression)
                and isinstance(expr.function, e.NamedExpression)
                and expr.function.name == stmt.name)

    # Count self-calls in the function's own body, ignoring any inside a lambda:
    # a self-call captured in a surviving closure is a normal recursive call to
    # this (now loop-based) function, not a tail call to convert. `rewrite_tail`
    # likewise never descends into lambdas, so both walkers agree — otherwise a
    # self-call in an un-inlined closure would spuriously trip the non-tail
    # error below. (Blank lambdas to a leaf, then count what remains.)
    def blank_lambdas(_r, thing):
        return e.NothingExpression(thing.line_ref) if isinstance(thing, e.LambdaExpression) else thing
    own_body = stmt.body.search_and_replace(resolver, blank_lambdas)

    total = [0]
    def counter(_r, thing):
        if is_self_call(thing):
            total[0] += 1
        return thing
    own_body.search_and_replace(resolver, counter)

    recurred = [0]
    def to_recur(call: e.CallExpression) -> e.RecurExpression:
        # Per-recur ordinal — gives each back-edge's phi-input/exit-label names a
        # stable discriminator without a generation-time counter.
        idx = recurred[0]
        recurred[0] += 1
        args = tuple(entry.value for entry in call.parameter.expressions)
        return e.RecurExpression(call.line_ref, args, idx)

    def rewrite_tail(expr: e.Expression) -> e.Expression:
        if is_self_call(expr):
            return to_recur(expr)
        if isinstance(expr, e.BlockExpression):
            # The block's value expression is in tail position; its statements
            # are not (they run before the result).
            return dataclasses.replace(expr, value=rewrite_tail(expr.value))
        if isinstance(expr, e.TernaryExpression):
            return dataclasses.replace(
                expr,
                trueResult=rewrite_tail(expr.trueResult),
                falseResult=rewrite_tail(expr.falseResult))
        if isinstance(expr, m.MatchExpression):
            return dataclasses.replace(
                expr,
                arms=[dataclasses.replace(arm, body=rewrite_tail(arm.body)) for arm in expr.arms])
        return expr  # non-tail-bearing position: a base-case value, leave it

    new_body = rewrite_tail(stmt.body)

    if total[0] == 0:
        errors.append(Error(stmt.line_ref,
            "[tail] requires direct self-recursion, but this function never calls "
            "itself directly (mutual recursion between functions is not supported)"))
        return stmt
    if recurred[0] != total[0]:
        errors.append(Error(stmt.line_ref,
            "[tail] function has a call to itself in a non-tail position; "
            "[tail] requires every self-call to be in tail position"))
        return stmt

    loop = e.LoopExpression(stmt.body.line_ref, new_body, params)
    # Wrap the loop in a block: this lowering runs before inlining / closure
    # conversion, and those passes gate on the body being a BlockExpression
    # (to find nested functions, lift captures, etc.). A bare LoopExpression
    # body would be skipped by them.
    block = e.BlockExpression(stmt.body.line_ref, [], loop)
    new_attrs = {k: v for k, v in stmt.attributes.items() if k != "tail"}
    return dataclasses.replace(stmt, body=block, attributes=new_attrs)
