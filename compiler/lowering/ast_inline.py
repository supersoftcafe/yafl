"""AST-level inlining, run before lambda lifting.

Two transformations applied to fixpoint:

1. **Function inlining.** A direct call `f(a1, …, an)` that appears as the
   whole value of a `ret`, `let`, or `action` statement is replaced with the
   callee's body nested as a `BlockExpression`: its parameters become fresh
   `let` statements at the head of the block, its statements follow, and its
   trailing value is the block's value. Nesting (rather than splicing the
   statements into the caller) keeps a callee's early `return` scoped to the
   inlined block — a `return` branches to the end of its nearest enclosing
   block, so it behaves as the call's value with no special handling.

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
from typing import Any, Callable, cast

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
# Cheap-expression test — gates *whether* a lambda application is worth inlining
# ─────────────────────────────────────────────────────────────────────────────

def _is_cheap(expr: e.Expression) -> bool:
    """True for a trivial argument (a name, literal, or dotted name). Used to
    decide *whether* to inline a lambda application — inlining one whose argument
    is a computed call would cascade into the recursive stdlib combinators and
    blow up the inline fixpoint. (It no longer governs *how* parameters are
    bound: they are always let-bound, never substituted.)"""
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
    if not isinstance(fn.body, e.BlockExpression):
        return False
    if fn.type_params:
        return False  # still generic — monomorphisation should have run first
    if "inline" in fn.attributes:
        return True
    return _node_count(fn.body) < _SIZE_THRESHOLD


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
        name: _collect_called_names(fn.body.statements) & candidates.keys()
        for name, fn in candidates.items()
        if isinstance(fn.body, e.BlockExpression)
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

    The prologue consists of lets that bind each parameter to its argument,
    followed by the target's body statements.  The target's body value is
    returned as the expression that replaces the original call site.

    Returns None if the call can't be inlined (argument count mismatch, etc.)."""
    if not isinstance(target.body, e.BlockExpression):
        return None
    params = list(target.parameters.flatten())
    if not isinstance(call.parameter, e.TupleExpression):
        return None
    args = [te.value for te in call.parameter.expressions]
    if len(args) != len(params):
        return None

    suffix = _fresh_suffix()

    # Clone body statements with renamed lets AND match arm patterns.
    body_stmts, let_rename = _rename_let_vars(list(target.body.statements), suffix)
    body_stmts = cast(list[s.Statement], _rename_match_patterns(body_stmts, suffix))

    # Apply the same renames to the body value expression.
    body_value: e.Expression = target.body.value
    if let_rename:
        body_value = _substitute_names(body_value,
            {old: e.NamedExpression(line_ref, new) for old, new in let_rename.items()})
    body_value = cast(e.Expression, _rename_match_patterns(body_value, suffix))

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

    # Apply param substitutions to the body.
    body_stmts = cast(list[s.Statement], _substitute_names(body_stmts, param_subst))
    body_value = cast(e.Expression, _substitute_names(body_value, param_subst))

    prologue.extend(body_stmts)
    return prologue, body_value


def _try_inline_call_at_stmt(
        stmt: s.Statement,
        catalog: dict[str, s.FunctionStatement],
        currently_inlining: set[str]) -> list[s.Statement] | None:
    """Inline when stmt's top-level expression is a direct call to a catalog
    function. Returns the replacement list or None if no inline happened."""
    if isinstance(stmt, s.ReturnStatement):
        call = stmt.value
        def wrap(expr): return dataclasses.replace(stmt, value=expr)
    elif isinstance(stmt, s.LetStatement) and not isinstance(stmt, s.DestructureStatement):
        if stmt.default_value is None:
            return None
        # A deferred-init let's RHS becomes the body of a deferred
        # closure (currently via `lower_lazy_lets` for `[lazy]`).  Lifting
        # an inlined call's args into outer `let`s would move references
        # out of that body and *before* the let's textual position —
        # defeating forward-ref-between-lazies (the references would
        # evaluate at the wrong time).  Expression-level beta-reduction
        # still inlines inside the RHS.
        if stmt.is_deferred_init():
            return None
        call = stmt.default_value
        def wrap(expr): return dataclasses.replace(stmt, default_value=expr)
    elif isinstance(stmt, s.ActionStatement):
        call = stmt.action
        def wrap(expr): return dataclasses.replace(stmt, action=expr)
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
    # Nest the callee body as a BlockExpression rather than splicing its
    # statements into the caller. A `return` inside the callee then branches to
    # the end of *this* inlined block (not the caller's body), so an early
    # return is scoped correctly with no special handling — the same way
    # expression-position inlining already nests. A callee that is a single
    # value (no prologue) needs no block.
    inlined: e.Expression = (e.BlockExpression(stmt.line_ref, prologue, final_expr)
                             if prologue else final_expr)
    return [wrap(inlined)]


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 — lambda beta-reduction
# ─────────────────────────────────────────────────────────────────────────────

def _inline_let_bound(body: e.Expression,
                      params: list[s.LetStatement],
                      args: list[e.Expression],
                      return_type: "t.TypeSpec | None",
                      resolver: "g.Resolver | None") -> e.Expression | None:
    """Inline a function/lambda by binding each parameter to a `let` holding its
    argument, then running the (alpha-renamed) body.

    One recursive pass freshens every name *bound by the body* — the parameters
    and every let, at any depth — with a unique suffix, rewriting both the
    binding sites and every use. Because the parameters are renamed in that same
    pass, turning each into a `let` is then trivial: it already has a unique name
    that the body's references (including those held as strings inside a
    `LoopExpression`, which tracks them through its `search_and_replace`) point
    at. Parameters are never substituted with their argument expression, so a
    loop-carried parameter (re-bound by a back-edge), a union-typed parameter
    (whose let preserves the declared type for match dispatch and coercion), and
    an argument used many times or with side effects all behave the same, with
    no special-casing and no clashes across inline sites."""
    if len(params) != len(args):
        return None

    suffix = _fresh_suffix()
    root = g.ResolverRoot([])

    # Every name the body binds: the parameters plus every let, collected
    # recursively (so lets nested inside blocks, loops and match arms are caught).
    bound: set[str] = {p.name for p in params}
    def collect(_r, thing):
        if isinstance(thing, s.LetStatement) and not isinstance(thing, s.DestructureStatement):
            bound.add(thing.name)
        return thing
    body.search_and_replace(root, collect)
    rename = {n: n + suffix for n in bound}

    def apply_rename(_r, thing):
        if isinstance(thing, e.NamedExpression) and thing.name in rename:
            return dataclasses.replace(thing, name=rename[thing.name])
        if isinstance(thing, s.LetStatement) and not isinstance(thing, s.DestructureStatement) \
                and thing.name in rename:
            return dataclasses.replace(thing, name=rename[thing.name])
        return thing
    renamed = cast(e.Expression, body.search_and_replace(root, apply_rename))
    renamed = cast(e.Expression, _rename_match_patterns(renamed, suffix))

    if isinstance(renamed, e.BlockExpression):
        body_stmts: list[s.Statement] = list(renamed.statements)
        body_value: e.Expression = renamed.value
        lr = renamed.line_ref
    else:
        body_stmts, body_value, lr = [], renamed, renamed.line_ref

    # Each parameter becomes a simple let — its uses in the body already carry
    # the renamed name from the pass above.
    prologue: list[s.Statement] = []
    for p, arg in zip(params, args):
        # The let takes the parameter's declared type — for a generic
        # specialisation that is the concrete (monomorphised) type, whereas the
        # argument's inferred type can still be the pruned generic. Fall back to
        # the argument's type only when the parameter is untyped.
        bind_type: t.TypeSpec | None = p.declared_type
        if bind_type is None and resolver is not None:
            bind_type = arg.get_type(resolver)
        if bind_type is None:
            return None
        prologue.append(s.LetStatement(arg.line_ref, p.name + suffix, None, {}, (), arg, bind_type))

    all_stmts = prologue + body_stmts
    result: e.Expression = e.BlockExpression(lr, all_stmts, body_value) if all_stmts else body_value
    if isinstance(return_type, t.CombinationSpec):
        return e.BoxExpression(lr, result, return_type)
    return result


def _flatten_block_values(statements: list[s.Statement]) -> list[s.Statement]:
    """Merge a `BlockExpression` whose value is itself a `BlockExpression` into a
    single block. Let-bound inlining readily produces such nesting (e.g.
    `length(show(v))` becomes `{let v=…; {let s=show(v); length(s)}}`), and at
    code generation the inner block's statements would share the outer block's
    `s{i}` prefixes — distinct stack vars then collide on one name. Merging the
    statement sequences gives each statement its own index; all names are already
    uniquely suffixed by inlining, so the merge cannot capture."""
    def flatten(_resolver: g.Resolver, thing: Any) -> Any:
        if isinstance(thing, e.BlockExpression) and isinstance(thing.value, e.BlockExpression):
            merged = list(thing.statements)
            value: e.Expression = thing.value
            while isinstance(value, e.BlockExpression):
                merged.extend(value.statements)
                value = value.value
            return dataclasses.replace(thing, statements=merged, value=value)
        return thing
    resolver = g.ResolverRoot(statements)
    return [stmt.search_and_replace(resolver, flatten) for stmt in statements]


def _beta_reduce_lambda(lambda_expr: e.LambdaExpression,
                        args: list[e.Expression]) -> e.Expression | None:
    """Inline a lambda application by binding its parameters to lets (see
    `_inline_let_bound`).

    Higher-order lambdas — those taking a callable/tuple/union parameter — are
    left alone: they are the recursive/closure combinators whose unbounded
    inlining would not terminate. (With let-binding there is no
    substitution-duplication concern, so the old cheap-argument restriction is
    gone — only this termination guard remains.)"""
    params = list(lambda_expr.parameters.flatten())
    if len(params) != len(args):
        return None
    for p in params:
        if isinstance(p.declared_type, (t.CombinationSpec, t.TupleSpec, t.CallableSpec)):
            return None
    for arg in args:
        if not _is_cheap(arg):
            return None
    ret_t = (lambda_expr.return_type.result
             if isinstance(lambda_expr.return_type, t.CallableSpec) else None)
    return _inline_let_bound(lambda_expr.expression, params, args, ret_t, None)


def _expr_inline_function(
        target: s.FunctionStatement,
        args: list[e.Expression],
        resolver: "g.Resolver | None" = None) -> e.Expression | None:
    """Inline `target` at expression position by binding its parameters to lets
    (see `_inline_let_bound`)."""
    if not isinstance(target.body, e.BlockExpression):
        return None
    return _inline_let_bound(target.body, list(target.parameters.flatten()),
                             args, target.return_type, resolver)


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
        # A nested block carries its own let-bound single-use lambdas (e.g. the
        # `let f = <lambda>` that let-bound `?>` inlining produces) which the
        # outer statement scan cannot see. Re-reduce it against its own
        # statement scope so those lambdas reach call position and beta-reduce
        # rather than surviving to be lifted into closures. (search_and_replace
        # visits children first, so this fires bottom-up.)
        if isinstance(thing, e.BlockExpression):
            inner = list(thing.statements) + [s.ReturnStatement(thing.value.line_ref, thing.value)]
            reduced = _beta_reduce_expressions(inner, catalog_for_expr_inline, global_resolver)
            if reduced and isinstance(reduced[-1], s.ReturnStatement):
                return dataclasses.replace(thing, statements=reduced[:-1], value=reduced[-1].value)
            return thing
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
    if not isinstance(fn.body, e.BlockExpression):
        return fn, False

    changed = False
    currently_inlining = {fn.name}

    # Temporarily represent the body as a flat list ending with a ReturnStatement
    # so the existing statement-level inlining logic can work unchanged.
    value_line = fn.body.value.line_ref
    stmts: list[s.Statement] = list(fn.body.statements) + [s.ReturnStatement(value_line, fn.body.value)]

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
    # expression-position inlining of catalog functions.
    reduced = _beta_reduce_expressions(stmts, catalog, global_resolver)
    if reduced != stmts:
        changed = True
        stmts = reduced

    if not changed:
        return fn, False

    # Extract the final ReturnStatement's value back out as the block value.
    assert isinstance(stmts[-1], s.ReturnStatement)
    new_value = stmts[-1].value
    new_body = dataclasses.replace(fn.body, statements=stmts[:-1], value=new_value)
    return dataclasses.replace(fn, body=new_body), True


# ─────────────────────────────────────────────────────────────────────────────
# Hoist remaining nested functions to global scope
# ─────────────────────────────────────────────────────────────────────────────

def _to_let_lambda(fn: s.FunctionStatement) -> s.LetStatement:
    """Convert a nested FunctionStatement to a LetStatement(LambdaExpression).
    Used only when the function captures outer variables — lambdas.py will
    then lift it to global scope with closure capture."""
    callable_type = fn.get_type()
    lambda_expr = e.LambdaExpression(
        line_ref=fn.line_ref,
        parameters=fn.parameters,
        expression=fn.body,
        return_type=callable_type,
    )
    return s.LetStatement(
        line_ref=fn.line_ref,
        name=fn.name,
        imports=fn.imports,
        attributes={},
        type_params=(),
        default_value=lambda_expr,
        declared_type=callable_type,
    )


def _free_refs(fn: s.FunctionStatement, also_exclude: set[str]) -> set[str]:
    """Names referenced in fn's body that are not fn's own params/lets/funs or also_exclude."""
    own: set[str] = {p.name for p in fn.parameters.flatten()}
    if isinstance(fn.body, e.BlockExpression):
        for stmt in fn.body.statements:
            if isinstance(stmt, s.LetStatement) and not isinstance(stmt, s.DestructureStatement):
                own.add(stmt.name)
            elif isinstance(stmt, s.FunctionStatement):
                own.add(stmt.name)
    exclude = own | also_exclude
    refs: set[str] = set()
    def visit(_r, thing):
        if isinstance(thing, e.NamedExpression) and thing.name not in exclude:
            refs.add(thing.name)
        return thing
    if isinstance(fn.body, e.BlockExpression):
        fn.body.search_and_replace(g.ResolverRoot([]), visit)
    return refs


def _specialization_suffix(parent_name: str) -> str:
    """Return the '$generic$…' tail of parent_name, or '' if not a specialisation."""
    idx = parent_name.find('$generic$')
    return parent_name[idx:] if idx >= 0 else ''


def _tarjan_sccs(nodes: list[str], edges: dict[str, set[str]]) -> list[list[str]]:
    """Tarjan's SCC algorithm.  Returns SCCs in reverse topological order
    (callees before callers).  Each SCC is a list of node names in
    discovery order; node order across SCCs preserves the input ordering
    of `nodes` as the tiebreak."""
    index_of: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    counter = [0]
    result: list[list[str]] = []

    def strongconnect(v: str) -> None:
        index_of[v] = counter[0]
        lowlink[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on_stack.add(v)
        for w in edges.get(v, set()):
            if w not in index_of:
                strongconnect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif w in on_stack:
                lowlink[v] = min(lowlink[v], index_of[w])
        if lowlink[v] == index_of[v]:
            scc: list[str] = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                scc.append(w)
                if w == v:
                    break
            result.append(scc)

    for n in nodes:
        if n not in index_of:
            strongconnect(n)
    return result


def _rewrite_for_class_method(body: e.Expression, this_target: dict[str, str]) -> e.Expression:
    """Rewrite NamedExpression(`name`) inside a class method body to
    `this.<this_target[name]>` for any `name` in the map — used to expose
    captured outer-scope variables (target == name) and same-class sibling
    methods (target == renamed method) through the implicit `this`
    parameter, mirroring lambdas.py's single-method redirect."""
    def visit(_resolver: g.Resolver, thing: Any) -> Any:
        if isinstance(thing, e.NamedExpression) and thing.name in this_target:
            lr = thing.line_ref
            return e.DotExpression(lr, e.NamedExpression(lr, "this"), this_target[thing.name])
        return thing
    return body.search_and_replace(g.ResolverRoot([]), visit)


def _gather_outer_var_types(fn: s.FunctionStatement) -> dict[str, t.TypeSpec]:
    """Map name → declared type for fn's parameters and top-level let-bindings.
    Used to type the fields of a synthesised closure class."""
    types: dict[str, t.TypeSpec] = {}
    for p in fn.parameters.flatten():
        ptype = p.declared_type or (p.get_type() if hasattr(p, 'get_type') else None)
        if ptype is not None:
            types[p.name] = ptype
    if isinstance(fn.body, e.BlockExpression):
        for stmt in fn.body.statements:
            if isinstance(stmt, s.LetStatement) and not isinstance(stmt, s.DestructureStatement):
                stype = stmt.declared_type or stmt.get_type()
                if stype is not None:
                    types[stmt.name] = stype
    return types


def _coalesce_mutual_scc(scc_fns: list[s.FunctionStatement],
                         outer_var_types: dict[str, t.TypeSpec],
                         sibling_fn_names: set[str],
                         spec_suffix: str) -> tuple[s.ClassStatement, list[s.LetStatement]]:
    """Pack a strongly-connected group of mutually-recursive capturing
    nested functions into a single class with one method per function.

    Mutual letrec across separate per-fn closure objects can't be expressed
    safely — each closure would capture the other's still-unbound
    let-binding at construction time, yielding null fields and a runtime
    crash.  Coalescing makes every cross-call route through `this`, so the
    single shared object owns all the closure fields and no
    forward-reference is needed.  Returns the class plus the parent-scope
    let-bindings that expose each method as a callable named after the
    original nested function."""
    scc_names = {fn.name for fn in scc_fns}
    lr = scc_fns[0].line_ref

    # Union captures: every outer var referenced by any SCC member, in a
    # stable order (first encounter wins).
    seen_captures: set[str] = set()
    union_captures: list[tuple[str, t.TypeSpec]] = []
    for fn in scc_fns:
        for ref in _free_refs(fn, sibling_fn_names):
            if ref in outer_var_types and ref not in seen_captures:
                seen_captures.add(ref)
                union_captures.append((ref, outer_var_types[ref]))

    capture_names = {n for n, _ in union_captures}

    # Give each method a class-unique name distinct from the original
    # nested-fn name.  The let-binding in the parent body keeps the
    # original name (so external callers in fn's body still resolve),
    # while the class method's C symbol won't collide with the local
    # variable for that let-binding.
    method_renames = {fn.name: f"$mut::{fn.name}@{lr.hash6()}" + spec_suffix
                      for fn in scc_fns}
    this_target = {name: name for name in capture_names}
    this_target.update(method_renames)

    # Rewrite each method body so capture refs and sibling-method refs go
    # through `this`, and rename the method itself.
    rewritten_methods: list[s.FunctionStatement] = []
    for fn in scc_fns:
        new_body = _rewrite_for_class_method(fn.body, this_target)
        rewritten_methods.append(dataclasses.replace(fn,
                                                      name=method_renames[fn.name],
                                                      body=new_body))

    cls_name = f"$mutual::class@{lr.hash6()}" + spec_suffix
    cls_params = [s.LetStatement(lr, name, _EMPTY_IMPORTS, {}, (), None, xtype)
                  for name, xtype in union_captures]
    cls_param_type = t.TupleSpec(lr, [t.TupleEntrySpec(name, xtype) for name, xtype in union_captures])
    cls_param = s.DestructureStatement(lr, "_", _EMPTY_IMPORTS, {}, (), None,
                                        cls_param_type, cls_params)
    attributes = {"final": e.IntegerExpression(lr, 1, 32)}
    cls = s.ClassStatement(lr, cls_name, _EMPTY_IMPORTS, attributes, (),
                           cls_param, list(rewritten_methods), [], False, set(), [])

    # One shared instance, then one let-binding per method.  Sharing keeps
    # the closure object identity stable across cross-method calls; cheaper
    # too — single allocation.
    shared_name = f"$mutual::shared@{lr.hash6()}" + spec_suffix
    capture_args = [e.TupleEntryExpression(name, e.NamedExpression(lr, name))
                    for name, _ in union_captures]
    cls_type = t.ClassSpec(lr, cls_name)
    shared_expr = e.NewExpression(lr, cls_type, e.TupleExpression(lr, capture_args))
    shared_let = s.LetStatement(lr, shared_name, _EMPTY_IMPORTS, {}, (),
                                 shared_expr, cls_type)
    method_lets: list[s.LetStatement] = [shared_let]
    for fn in scc_fns:
        method_expr = e.DotExpression(lr, e.NamedExpression(lr, shared_name),
                                       method_renames[fn.name])
        method_lets.append(s.LetStatement(lr, fn.name, _EMPTY_IMPORTS, {}, (),
                                           method_expr, fn.get_type()))
    return cls, method_lets


def _hoist_from_body(fn: s.FunctionStatement) -> tuple[list[s.Statement], dict[str, str], list[s.Statement]]:
    """Scan fn's body for nested FunctionStatements and decide how to handle each.

    Returns (new_body_stmts, renames, hoisted).  Strategy per
    strongly-connected component of the sibling-call graph:

    - SCC that neither directly captures outer params/lets nor transitively
      calls a capturing SCC → all members hoisted to global scope (no
      closure needed; mutual references resolve via global names).
    - SCC of size 1 that needs a closure → converted to LetStatement(lambda)
      so lambdas.py applies the existing single-class closure capture.
    - SCC of size >1 that needs a closure → coalesced into one class with
      N methods; this avoids the forward-reference hazard that mutually
      recursive single-method closures would hit at construction time.

    When fn is a generic specialisation (its name contains '$generic$'),
    directly-hoisted inner functions are renamed by appending fn's
    specialisation suffix to prevent name collisions across instantiations.
    renames maps old → new name; callers must apply it to all remaining
    references in fn's body.
    """
    if not isinstance(fn.body, e.BlockExpression):
        stmts = list(fn.body.statements) if hasattr(fn.body, 'statements') else []
        return stmts, {}, []
    body_stmts = list(fn.body.statements)
    outer_params = {p.name for p in fn.parameters.flatten()}
    outer_lets = {stmt.name for stmt in body_stmts
                  if isinstance(stmt, s.LetStatement) and not isinstance(stmt, s.DestructureStatement)}
    outer_var_names = outer_params | outer_lets

    nested_fns = [stmt for stmt in body_stmts
                  if isinstance(stmt, s.FunctionStatement) and isinstance(stmt.body, e.BlockExpression)]
    sibling_fn_names = {nf.name for nf in nested_fns}
    nested_by_name = {nf.name: nf for nf in nested_fns}

    if not nested_fns:
        return body_stmts, {}, []

    spec_suffix = _specialization_suffix(fn.name)

    # Sibling-call edges
    sibling_calls = {nf.name: _free_refs(nf, set()) & sibling_fn_names for nf in nested_fns}

    # Direct captures: a free reference into outer params/lets (excluding
    # sibling names, which can't be captures because they're co-resident).
    direct_captures = {nf.name for nf in nested_fns
                       if _free_refs(nf, sibling_fn_names) & outer_var_names}

    # SCCs in reverse topological order (callees first).
    sccs = _tarjan_sccs([nf.name for nf in nested_fns], sibling_calls)
    scc_index = {n: i for i, scc in enumerate(sccs) for n in scc}

    # Propagate "needs closure" along sibling-call edges: an SCC needs a
    # closure when any member directly captures, or when any sibling call
    # out of the SCC lands in a closure-needing SCC.  Reverse-topo
    # traversal converges in one pass.
    scc_needs_closure = [False] * len(sccs)
    for i, scc in enumerate(sccs):
        if any(n in direct_captures for n in scc):
            scc_needs_closure[i] = True
            continue
        for n in scc:
            for callee in sibling_calls[n]:
                callee_scc = scc_index[callee]
                if callee_scc != i and scc_needs_closure[callee_scc]:
                    scc_needs_closure[i] = True
                    break
            if scc_needs_closure[i]:
                break

    outer_var_types = _gather_outer_var_types(fn) if any(scc_needs_closure) else {}

    new_body: list[s.Statement] = []
    renames: dict[str, str] = {}
    hoisted: list[s.Statement] = []
    processed_scc: set[int] = set()

    for stmt in body_stmts:
        if not (isinstance(stmt, s.FunctionStatement) and isinstance(stmt.body, e.BlockExpression)):
            new_body.append(stmt)
            continue
        if stmt.name not in scc_index:
            new_body.append(stmt)
            continue
        idx = scc_index[stmt.name]
        if idx in processed_scc:
            continue
        processed_scc.add(idx)
        scc_member_fns = [nested_by_name[n] for n in sccs[idx]]

        if not scc_needs_closure[idx]:
            for member in scc_member_fns:
                if spec_suffix and not member.name.endswith(spec_suffix):
                    unique_name = member.name + spec_suffix
                    renames[member.name] = unique_name
                    hoisted.append(dataclasses.replace(member, name=unique_name))
                else:
                    hoisted.append(member)
        elif len(scc_member_fns) == 1:
            new_body.append(_to_let_lambda(scc_member_fns[0]))
        else:
            cls, lets = _coalesce_mutual_scc(scc_member_fns, outer_var_types,
                                              sibling_fn_names, spec_suffix)
            hoisted.append(cls)
            new_body.extend(lets)

    return new_body, renames, hoisted



def _hoist_nested_fns_to_lambdas(statements: list[s.Statement]) -> list[s.Statement]:
    """After the inlining fixpoint, hoist any FunctionStatement still nested inside
    a function body.

    If the nested function captures outer parameters or let-bindings it is
    converted to a LetStatement(lambda) for lambdas.py to lift with closure
    capture.  Otherwise it is extracted directly to global scope — no closure
    needed, mutual-recursion-safe.  Applied recursively so that nested-inside-
    nested functions are also hoisted.
    """
    result: list[s.Statement] = []
    extra: list[s.Statement] = []
    for stmt in statements:
        if isinstance(stmt, s.FunctionStatement) and isinstance(stmt.body, e.BlockExpression):
            new_body_stmts, renames, hoisted = _hoist_from_body(stmt)
            if renames:
                def _rename(_r, thing, _rn=renames):
                    if isinstance(thing, e.NamedExpression) and thing.name in _rn:
                        return dataclasses.replace(thing, name=_rn[thing.name])
                    return thing
                resolver = g.ResolverRoot([])
                new_body_stmts = [st.search_and_replace(resolver, _rename) for st in new_body_stmts]
                new_body_value = stmt.body.value.search_and_replace(resolver, _rename)
                hoisted = [cast(s.Statement, h.search_and_replace(resolver, _rename)) for h in hoisted]
                new_body = dataclasses.replace(stmt.body, statements=new_body_stmts, value=new_body_value)
            else:
                new_body = dataclasses.replace(stmt.body, statements=new_body_stmts)
            result.append(dataclasses.replace(stmt, body=new_body))
            extra.extend(hoisted)
        else:
            result.append(stmt)
    if extra:
        extra = _hoist_nested_fns_to_lambdas(extra)
        return result + extra
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

_MAX_ITERATIONS = 10


def inline_ast(statements: list[s.Statement]) -> list[s.Statement]:
    """Run function inlining and lambda beta-reduction to fixpoint.

    Runs before lambda lifting so that lambdas inlined away here never
    become heap-allocated closure classes.
    """
    _inline_counter[0] = 0
    current = _hoist_nested_fns_to_lambdas(list(statements))
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
    # Normalise away block-valued blocks created by let-bound inlining, so
    # nested blocks don't collide on their `s{i}` generation prefixes.
    return _flatten_block_values(current)
