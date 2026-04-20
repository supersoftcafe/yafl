"""AST-level inlining, run before lambda lifting.

Two transformations applied to fixpoint:

1. **Function inlining.** A direct call `f(a1, …, an)` that appears as the
   whole value of a `ret`, `let`, or `action` statement is replaced with the
   callee's body: its parameters become fresh `let` statements, and the
   body's intermediate statements are spliced in before the original,
   with the body's final `ret` supplying the value that replaces the
   original call site.

   A function is inlinable when it is a free (non-class-member) function,
   not foreign, not part of a call-graph cycle, and either carries an
   `[inline]` attribute or has an AST node count under a threshold.

2. **Lambda beta-reduction at expression position.** Two sub-cases:
   - IIFE — `(λ)(args)` substitutes args directly into the lambda body.
   - Let-bound single-use lambda — `let f = λ; … f(args) …` where `f`
     is used exactly once and as the function of a call, inlines the
     call and drops the `let`.

Lambdas have no side effects so substitution may duplicate evaluation of
arg expressions safely — but for clarity the pass restricts beta-reduction
to "cheap" argument expressions (variable references, literals, dot-chains
rooted at a local). Other cases are left alone.

Class member methods are out of scope for this pass.
"""
from __future__ import annotations

import dataclasses
from typing import Any, Callable

import pyast.expression as e
import pyast.match as m
import pyast.resolver as g
import pyast.statement as s
import pyast.typespec as t

from parsing.tokenizer import LineRef


_SIZE_THRESHOLD = 10

_EMPTY_IMPORTS = s.ImportGroup(tuple())


# ─────────────────────────────────────────────────────────────────────────────
# Node counting, name reference collection, substitution
# ─────────────────────────────────────────────────────────────────────────────

def _node_count(obj: Any) -> int:
    """Rough AST-size measure: counts Expression and Statement instances
    reachable from obj (including itself)."""
    total = [0]

    def visit(_resolver, thing):
        if isinstance(thing, (e.Expression, s.Statement, m.MatchArm)):
            total[0] += 1
        return thing

    if isinstance(obj, list):
        for item in obj:
            if isinstance(item, s.Statement):
                item.search_and_replace(g.ResolverRoot([]), visit)
    elif isinstance(obj, (s.Statement, e.Expression)):
        obj.search_and_replace(g.ResolverRoot([]), visit)
    return total[0]


def _collect_called_names(stmts: list[s.Statement]) -> set[str]:
    """Names that appear as the function of a CallExpression anywhere in stmts."""
    names: set[str] = set()

    def visit(_resolver, thing):
        if isinstance(thing, e.CallExpression) and isinstance(thing.function, e.NamedExpression):
            names.add(thing.function.name)
        return thing

    for stmt in stmts:
        stmt.search_and_replace(g.ResolverRoot([]), visit)
    return names


def _count_name_refs(obj: Any, name: str) -> int:
    """Count references to `name` as a plain NamedExpression (any position)."""
    count = [0]

    def visit(_resolver, thing):
        if isinstance(thing, e.NamedExpression) and thing.name == name:
            count[0] += 1
        return thing

    if isinstance(obj, list):
        for item in obj:
            if isinstance(item, s.Statement):
                item.search_and_replace(g.ResolverRoot([]), visit)
    elif isinstance(obj, (s.Statement, e.Expression, m.MatchArm)):
        obj.search_and_replace(g.ResolverRoot([]), visit)
    return count[0]


def _substitute_names(obj: Any, mapping: dict[str, e.Expression]) -> Any:
    """Replace every NamedExpression whose name is a key in `mapping` with the
    corresponding expression. Works over Expression, Statement, MatchArm, and
    lists of Statement."""
    def replace(_resolver, thing):
        if isinstance(thing, e.NamedExpression) and thing.name in mapping:
            return mapping[thing.name]
        return thing

    resolver = g.ResolverRoot([])
    if isinstance(obj, list):
        return [item.search_and_replace(resolver, replace) if isinstance(item, s.Statement) else item
                for item in obj]
    if isinstance(obj, (s.Statement, e.Expression, m.MatchArm)):
        return obj.search_and_replace(resolver, replace)
    return obj


def _rename_match_patterns(body: "e.Expression | list[s.Statement]", suffix: str) -> "e.Expression | list[s.Statement]":
    """Rename all match arm pattern variables in body by appending suffix.

    Prevents pattern variable names (e.g., the `x` in `?>`) from being captured
    when the inlined body is substituted into a context that also has a binding
    with the same name (e.g., a nested inlining of the same function).
    """
    bound: set[str] = set()

    def _collect(_r, thing):
        if isinstance(thing, m.MatchExpression):
            for arm in thing.arms:
                if arm.name and arm.name != "_":
                    bound.add(arm.name)
        return thing

    resolver = g.ResolverRoot([])
    if isinstance(body, list):
        for stmt in body:
            stmt.search_and_replace(resolver, _collect)
    else:
        body.search_and_replace(resolver, _collect)

    if not bound:
        return body

    renames = {n: n + suffix for n in bound}

    def _rename(_r, thing):
        if isinstance(thing, e.NamedExpression) and thing.name in renames:
            return dataclasses.replace(thing, name=renames[thing.name])
        if isinstance(thing, m.MatchExpression):
            new_arms = [
                dataclasses.replace(arm, name=renames[arm.name])
                if arm.name and arm.name in renames else arm
                for arm in thing.arms
            ]
            if any(na is not oa for na, oa in zip(new_arms, thing.arms)):
                return dataclasses.replace(thing, arms=new_arms)
        return thing

    if isinstance(body, list):
        return [stmt.search_and_replace(resolver, _rename) for stmt in body]
    return body.search_and_replace(resolver, _rename)


def _rename_let_vars(stmts: list[s.Statement], suffix: str) -> tuple[list[s.Statement], dict[str, str]]:
    """Rename every let-bound name in `stmts` by appending `suffix`, so that
    inlining the same function at two sites doesn't create duplicate
    identifiers. Returns (new_stmts, rename_map)."""
    rename: dict[str, str] = {}
    for stmt in stmts:
        if isinstance(stmt, s.LetStatement) and not isinstance(stmt, s.DestructureStatement):
            rename[stmt.name] = stmt.name + suffix

    def replace(_resolver, thing):
        if isinstance(thing, e.NamedExpression) and thing.name in rename:
            return dataclasses.replace(thing, name=rename[thing.name])
        if isinstance(thing, s.LetStatement) and not isinstance(thing, s.DestructureStatement) \
                and thing.name in rename:
            return dataclasses.replace(thing, name=rename[thing.name])
        return thing

    resolver = g.ResolverRoot([])
    new_stmts = [stm.search_and_replace(resolver, replace) for stm in stmts]
    return new_stmts, rename


# ─────────────────────────────────────────────────────────────────────────────
# Cheap-expression test for safe beta-reduction
# ─────────────────────────────────────────────────────────────────────────────

def _is_cheap(expr: e.Expression) -> bool:
    """True when substituting `expr` in for multiple uses of a parameter won't
    duplicate any side effect or meaningful work."""
    if isinstance(expr, (e.NamedExpression, e.IntegerExpression, e.StringExpression,
                         e.NothingExpression)):
        return True
    if isinstance(expr, e.DotExpression):
        return _is_cheap(expr.base)
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Inlinability
# ─────────────────────────────────────────────────────────────────────────────

def _is_inlinable_function(fn: s.FunctionStatement, class_members: set[str]) -> bool:
    if fn.name in class_members:
        return False
    if "foreign" in fn.attributes:
        return False
    if not fn.statements:
        return False
    if not isinstance(fn.statements[-1], s.ReturnStatement):
        return False
    if fn.type_params:
        return False  # still generic — monomorphisation should have run first
    if "inline" in fn.attributes:
        return True
    return _node_count(fn.statements) < _SIZE_THRESHOLD


def _find_class_member_names(statements: list[s.Statement]) -> set[str]:
    names: set[str] = set()
    for stmt in statements:
        if isinstance(stmt, s.ClassStatement):
            for inner in stmt.statements:
                if isinstance(inner, s.FunctionStatement):
                    names.add(inner.name)
    return names


def _build_catalog(statements: list[s.Statement]) -> dict[str, s.FunctionStatement]:
    """Map of inlinable function name → FunctionStatement. Excludes any
    function that is part of a call-graph cycle."""
    class_members = _find_class_member_names(statements)
    candidates: dict[str, s.FunctionStatement] = {}
    for stmt in statements:
        if isinstance(stmt, s.FunctionStatement) and _is_inlinable_function(stmt, class_members):
            candidates[stmt.name] = stmt

    # Prune cycles (including self-recursion). Build call graph over
    # candidates and keep only functions whose reachable call set doesn't
    # include themselves.
    callees: dict[str, set[str]] = {
        name: _collect_called_names(fn.statements) & candidates.keys()
        for name, fn in candidates.items()
    }

    def reaches_self(start: str) -> bool:
        seen: set[str] = set()
        stack = [start]
        while stack:
            cur = stack.pop()
            for callee in callees.get(cur, ()):
                if callee == start:
                    return True
                if callee not in seen:
                    seen.add(callee)
                    stack.append(callee)
        return False

    return {name: fn for name, fn in candidates.items() if not reaches_self(name)}


# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 — function inlining at statement positions
# ─────────────────────────────────────────────────────────────────────────────

_inline_counter = [0]


def _fresh_suffix() -> str:
    _inline_counter[0] += 1
    return f"$inl{_inline_counter[0]}"


def _inline_function_call(
        call: e.CallExpression,
        target: s.FunctionStatement,
        line_ref: LineRef) -> tuple[list[s.Statement], e.Expression] | None:
    """Expand a call to `target` into (prologue statements, final value expr).

    The prologue consists of lets that bind each parameter to its corresponding
    argument, followed by the target's body minus its final ReturnStatement.
    The final return value (from target's last ReturnStatement) is returned
    as the expression that replaces the original call.

    Returns None if the call can't be inlined (e.g., argument count mismatch
    or target lacks a trailing ReturnStatement)."""
    params = list(target.parameters.flatten())
    if not isinstance(call.parameter, e.TupleExpression):
        return None
    args = [te.value for te in call.parameter.expressions]
    if len(args) != len(params):
        return None
    if not target.statements or not isinstance(target.statements[-1], s.ReturnStatement):
        return None

    suffix = _fresh_suffix()

    # Clone body with renamed lets AND match arm patterns so multiple inlinings don't collide.
    body, let_rename = _rename_let_vars(list(target.statements), suffix)
    body = _rename_match_patterns(body, suffix)

    # Build the param → argument mapping.
    param_subst: dict[str, e.Expression] = {}
    prologue: list[s.Statement] = []
    for param, arg in zip(params, args):
        new_param_name = param.name + suffix
        param_subst[param.name] = e.NamedExpression(line_ref, new_param_name)
        prologue.append(s.LetStatement(
            line_ref,
            new_param_name,
            _EMPTY_IMPORTS,
            {},
            (),
            arg,
            param.declared_type,
        ))

    # Apply param substitutions to the (renamed) body.
    body = _substitute_names(body, param_subst)

    # Emit body statements except the last ReturnStatement; that one's value
    # becomes the replacement expression.
    final_ret = body[-1]
    prologue.extend(body[:-1])
    assert isinstance(final_ret, s.ReturnStatement)
    return prologue, final_ret.value


def _try_inline_call_at_stmt(
        stmt: s.Statement,
        catalog: dict[str, s.FunctionStatement],
        currently_inlining: set[str]) -> list[s.Statement] | None:
    """Inline when stmt's top-level expression is a direct call to a catalog
    function. Returns the replacement list or None if no inline happened."""
    if isinstance(stmt, s.ReturnStatement):
        call = stmt.value
        wrap = lambda expr: dataclasses.replace(stmt, value=expr)
    elif isinstance(stmt, s.LetStatement) and not isinstance(stmt, s.DestructureStatement):
        if stmt.default_value is None:
            return None
        call = stmt.default_value
        wrap = lambda expr: dataclasses.replace(stmt, default_value=expr)
    elif isinstance(stmt, s.ActionStatement):
        call = stmt.action
        wrap = lambda expr: dataclasses.replace(stmt, action=expr)
    else:
        return None

    if not isinstance(call, e.CallExpression) or not isinstance(call.function, e.NamedExpression):
        return None
    target_name = call.function.name
    if target_name not in catalog or target_name in currently_inlining:
        return None
    target = catalog[target_name]

    result = _inline_function_call(call, target, stmt.line_ref)
    if result is None:
        return None
    prologue, final_expr = result
    return prologue + [wrap(final_expr)]


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 — lambda beta-reduction
# ─────────────────────────────────────────────────────────────────────────────

def _beta_reduce_lambda(lambda_expr: e.LambdaExpression,
                        args: list[e.Expression]) -> e.Expression | None:
    """Substitute the lambda's parameters with args in its body.
    Returns None if any arg is not 'cheap' (avoids duplicating work), the
    arg count is wrong, or any param's declared type is a union — the
    latter because substituting a narrower value for a union-typed param
    would bypass the boxing pass and break later type checks/codegen.
    """
    params = list(lambda_expr.parameters.flatten())
    if len(params) != len(args):
        return None
    for p in params:
        if isinstance(p.declared_type, (t.CombinationSpec, t.TupleSpec, t.CallableSpec)):
            return None
    for arg in args:
        if not _is_cheap(arg):
            return None
    mapping: dict[str, e.Expression] = {
        p.name: a for p, a in zip(params, args)
    }
    return _substitute_names(lambda_expr.expression, mapping)


def _expr_inline_function(
        target: s.FunctionStatement,
        args: list[e.Expression],
        resolver: "g.Resolver | None" = None) -> e.Expression | None:
    """Substitute args into the return-value expression of `target` and return
    the resulting expression, wrapping non-cheap multi-use args in
    LetInExpressions to avoid duplicating side effects.

    Only applicable when `target` has a single ReturnStatement body.
    Narrowing guard: if the declared return type is a union/tuple/callable
    and the body is a concrete leaf, substitution would hide the widening the
    boxing pass relies on, so those cases are still rejected."""
    if len(target.statements) != 1:
        return None
    ret_stmt = target.statements[0]
    if not isinstance(ret_stmt, s.ReturnStatement):
        return None
    if isinstance(target.return_type, (t.CombinationSpec, t.TupleSpec, t.CallableSpec)):
        if not isinstance(ret_stmt.value, (e.CallExpression, m.MatchExpression)):
            return None
    params = list(target.parameters.flatten())
    if len(params) != len(args):
        return None

    suffix = _fresh_suffix()
    mapping: dict[str, e.Expression] = {}
    # (bind_name, declared_type, arg_expr) for params that need a let-in binding
    wrappers: list[tuple[str, t.TypeSpec, e.Expression]] = []

    for p, arg in zip(params, args):
        use_count = _count_name_refs(ret_stmt.value, p.name)
        # CombinationSpec params always need a let-in to preserve the union type
        # for match dispatch — a cheap/single-use narrow arg (e.g. a String for a
        # String|None param) substituted directly would change the match subject
        # type and break codegen.  Non-cheap args used more than once also need a
        # let-in to avoid duplicating side effects.
        need_let_in = (isinstance(p.declared_type, t.CombinationSpec)
                       or (not _is_cheap(arg) and use_count > 1))
        if need_let_in:
            if p.declared_type is None:
                return None
            bind_name = p.name + suffix
            mapping[p.name] = e.NamedExpression(arg.line_ref, bind_name)
            # For union params, use the declared type to preserve match dispatch.
            # For other params (e.g. tuples), use the arg's actual type so the
            # LetInExpression C variable has the correct struct layout — the
            # declared parameter type may use a wider representation (e.g.
            # object_t* for IO) that differs from the concrete argument type.
            if isinstance(p.declared_type, t.CombinationSpec):
                bind_type = p.declared_type
            elif resolver is not None:
                actual = arg.get_type(resolver)
                bind_type = actual if actual is not None else p.declared_type
            else:
                bind_type = p.declared_type
            wrappers.append((bind_name, bind_type, arg))
        else:
            mapping[p.name] = arg

    body = _rename_match_patterns(_substitute_names(ret_stmt.value, mapping), suffix)

    # Wrap innermost-first so each LetInExpression is in scope for the next.
    for bind_name, bind_type, bind_val in reversed(wrappers):
        body = e.LetInExpression(bind_val.line_ref, bind_name, bind_type, bind_val, body)

    return body


def _beta_reduce_expressions(stmts: list[s.Statement],
                             catalog_for_expr_inline: dict[str, s.FunctionStatement],
                             global_resolver: "g.Resolver | None" = None) -> list[s.Statement]:
    """Apply lambda beta-reduction throughout statements. Two cases:
       (a) `(lambda)(args)` — IIFE.
       (b) `f(args)` where f resolves via a prior `let f = lambda` and f is
           referenced exactly once in the enclosing body (that call)."""

    # Identify let-bound single-use lambdas in the current sequence.
    # A let like `let f = lambda_expr` is replaceable when `f` appears
    # exactly once after its binding and that occurrence is the function
    # of a CallExpression. We approximate "scope" as the remaining
    # statements after the let, which works because our lets don't escape
    # function boundaries.

    single_use_lambdas: dict[str, e.LambdaExpression] = {}
    for i, stmt in enumerate(stmts):
        if not isinstance(stmt, s.LetStatement) or isinstance(stmt, s.DestructureStatement):
            continue
        if not isinstance(stmt.default_value, e.LambdaExpression):
            continue
        # Count usages across the remaining statements.
        rest = stmts[i+1:]
        uses = sum(_count_name_refs(r, stmt.name) for r in rest)
        if uses == 1:
            single_use_lambdas[stmt.name] = stmt.default_value

    def replace(_resolver, thing):
        # IIFE
        if isinstance(thing, e.CallExpression) and isinstance(thing.function, e.LambdaExpression):
            if isinstance(thing.parameter, e.TupleExpression):
                args = [te.value for te in thing.parameter.expressions]
                reduced = _beta_reduce_lambda(thing.function, args)
                if reduced is not None:
                    return reduced
        # Let-bound single-use lambda
        if isinstance(thing, e.CallExpression) and isinstance(thing.function, e.NamedExpression):
            lam = single_use_lambdas.get(thing.function.name)
            if lam is not None and isinstance(thing.parameter, e.TupleExpression):
                args = [te.value for te in thing.parameter.expressions]
                reduced = _beta_reduce_lambda(lam, args)
                if reduced is not None:
                    return reduced
        # Catalog function with pure-return body + all-cheap args: substitute
        # into the return expression directly. This lets the bind operator
        # collapse even when it appears inside a match arm.
        if isinstance(thing, e.CallExpression) and isinstance(thing.function, e.NamedExpression):
            target = catalog_for_expr_inline.get(thing.function.name)
            if target is not None and isinstance(thing.parameter, e.TupleExpression):
                args = [te.value for te in thing.parameter.expressions]
                reduced = _expr_inline_function(target, args, _resolver)
                if reduced is not None:
                    return reduced
        return thing

    resolver = global_resolver if global_resolver is not None else g.ResolverRoot([])
    new_stmts = [stmt.search_and_replace(resolver, replace) for stmt in stmts]

    # Drop `let` statements whose lambda was successfully inlined (they are
    # now dead — no remaining references).
    new_stmts = [
        stm for stm in new_stmts
        if not (isinstance(stm, s.LetStatement)
                and not isinstance(stm, s.DestructureStatement)
                and stm.name in single_use_lambdas
                and sum(_count_name_refs(other, stm.name) for other in new_stmts
                        if other is not stm) == 0)
    ]
    return new_stmts


# ─────────────────────────────────────────────────────────────────────────────
# Function-body rewriting
# ─────────────────────────────────────────────────────────────────────────────

def _rewrite_function(fn: s.FunctionStatement,
                      catalog: dict[str, s.FunctionStatement],
                      global_resolver: "g.Resolver | None" = None) -> tuple[s.FunctionStatement, bool]:
    """Inline within fn's body. Returns (new_fn, changed)."""
    changed = False
    currently_inlining = {fn.name}
    stmts = list(fn.statements)

    # Pass 1: statement-level function inlining.
    new_stmts: list[s.Statement] = []
    for stmt in stmts:
        replaced = _try_inline_call_at_stmt(stmt, catalog, currently_inlining)
        if replaced is not None:
            new_stmts.extend(replaced)
            changed = True
        else:
            new_stmts.append(stmt)
    stmts = new_stmts

    # Pass 2: beta-reduce lambdas (IIFE + let-bound single-use) and
    # expression-position inlining of catalog functions whose body is a pure
    # single-return expression (so no prologue lets are needed).
    reduced = _beta_reduce_expressions(stmts, catalog, global_resolver)
    if reduced != stmts:
        changed = True
        stmts = reduced

    if not changed:
        return fn, False
    return dataclasses.replace(fn, statements=stmts), True


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

_MAX_ITERATIONS = 10


def inline_ast(statements: list[s.Statement]) -> list[s.Statement]:
    """Run function inlining and lambda beta-reduction to fixpoint.

    Runs before lambda lifting so that lambdas inlined away here never
    become heap-allocated closure classes.
    """
    current = list(statements)
    for _ in range(_MAX_ITERATIONS):
        catalog = _build_catalog(current)
        if not catalog:
            break
        changed = False
        global_resolver = g.ResolverRoot(current)
        new_stmts: list[s.Statement] = []
        for stmt in current:
            if isinstance(stmt, s.FunctionStatement):
                new_fn, fn_changed = _rewrite_function(stmt, catalog, global_resolver)
                new_stmts.append(new_fn)
                changed = changed or fn_changed
            else:
                new_stmts.append(stmt)
        current = new_stmts
        if not changed:
            break
    return current
