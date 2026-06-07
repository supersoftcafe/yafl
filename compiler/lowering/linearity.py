"""Linear-type checking — every linear value is used exactly once.

A class marked `[linear]` (and a `<[linear] T>` type parameter) denotes a
value that must be consumed exactly once on every execution path: not zero
times (a leak), not twice (an alias / double-close).

This is a whole-program analysis run after the type-check pass, on the
converged templates (pre-monomorphisation).  It is sound (never accepts a
linearity violation) but intentionally incomplete (rejects some safe
programs — see the conservative rejections below).

Terminology:
  * obligation — a linear leaf reachable from a binding, identified by
    `(root_binding_name, field_path)`.
  * move      — a path expression whose result type carries linearity;
    consumes every obligation leaf at or under that path.
  * borrow    — a path expression whose result type is non-linear; consumes
    nothing (e.g. reading `this._io`, `r.v`, `s.pos`).
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from parsing.parselib import Error
from parsing.tokenizer import LineRef

import pyast.expression as e
import pyast.match as m
import pyast.statement as s
import pyast.typespec as t
import pyast.resolver as g


# An obligation is (root binding name, field-path to a linear leaf).
Path = tuple[str, ...]
Obligation = tuple[str, Path]


def check_linearity(statements: list[s.Statement], resolver: g.Resolver) -> list[Error]:
    """Entry point — return a list of linearity errors (empty if clean)."""
    checker = _Checker(resolver)
    for stmt in statements:
        checker.visit_toplevel(stmt)
    checker.check_instantiations(statements)
    return checker.errors


# ─── linearity of types ──────────────────────────────────────────────────

class _Checker:
    def __init__(self, resolver: g.Resolver):
        self.resolver = resolver
        self.errors: list[Error] = []

    # --- type helpers ----------------------------------------------------

    def _class_stmt(self, spec: t.TypeSpec) -> s.ClassStatement | None:
        if not isinstance(spec, t.ClassSpec):
            return None
        found = self.resolver.find_type(spec.name)
        if len(found) == 1 and isinstance(found[0].statement, s.ClassStatement):
            return found[0].statement
        return None

    def _is_linear_class(self, spec: t.TypeSpec) -> bool:
        cs = self._class_stmt(spec)
        return cs is not None and "linear" in cs.attributes

    def leaves(self, spec: t.TypeSpec | None, _seen: frozenset[str] = frozenset()) -> set[Path]:
        """Field-paths from a value of `spec` to its linear leaves."""
        if spec is None:
            return set()
        if isinstance(spec, t.GenericPlaceholderSpec):
            return {()} if spec.is_linear else set()
        if isinstance(spec, t.ClassSpec):
            if not self._is_linear_class(spec):
                return set()
            if spec.name in _seen:        # guard against recursive linear types
                return {()}
            cs = self._class_stmt(spec)
            seen = _seen | {spec.name}
            mapping = {tp.name: ct for tp, ct in zip(cs.type_params, spec.type_params)}
            out: set[Path] = set()
            for fld in cs.get_fields(self.resolver):
                ftype = fld.declared_type
                if ftype is None:
                    continue
                if mapping:
                    ftype = self._subst(ftype, mapping)
                for sub in self.leaves(ftype, seen):
                    out.add((fld.name,) + sub)
            # A linear class with no linear fields is itself the leaf.
            return out if out else {()}
        if isinstance(spec, t.TupleSpec):
            out = set()
            for entry in spec.entries:
                if entry.name is None or entry.type is None:
                    continue
                for sub in self.leaves(entry.type, _seen):
                    out.add((entry.name,) + sub)
            return out
        if isinstance(spec, t.CombinationSpec):
            # A union carrying a linear member is one linear leaf: the union
            # value must be consumed (by `match`) exactly once; the typed
            # `match` arms then bind and discharge any inner linear value.
            if any(self.carries_linearity(member, _seen) for member in spec.types):
                return {()}
            return set()
        return set()

    def carries_linearity(self, spec: t.TypeSpec | None,
                          _seen: frozenset[str] = frozenset()) -> bool:
        return bool(self.leaves(spec, _seen))

    def _subst(self, spec: t.TypeSpec, mapping: dict[str, t.TypeSpec]) -> t.TypeSpec:
        def fn(_, thing):
            if isinstance(thing, t.GenericPlaceholderSpec) and thing.name in mapping:
                return mapping[thing.name]
            return thing
        return spec.search_and_replace(self.resolver, fn)

    # --- structural (conservative) rejections ----------------------------

    def _check_type_position(self, spec: t.TypeSpec | None, line_ref: LineRef) -> None:
        """Reject linear types in positions the flow analysis cannot trace:
        as a container's generic argument. A linear type *inside a union*
        is allowed — the union is one obligation, discharged by `match`."""
        if spec is None:
            return
        if isinstance(spec, t.CombinationSpec):
            for member in spec.types:
                self._check_type_position(member, line_ref)
            return
        if isinstance(spec, t.ClassSpec):
            # A linear class is a leaf; do not descend (its fields were
            # validated where the class was declared). Non-linear generic
            # classes must not carry a linear argument.
            if not self._is_linear_class(spec):
                for arg in spec.type_params:
                    if self.carries_linearity(arg):
                        self.errors.append(Error(line_ref,
                            "linear type not allowed as a generic type argument"))
                    self._check_type_position(arg, line_ref)
            return
        if isinstance(spec, t.TupleSpec):
            for entry in spec.entries:
                self._check_type_position(entry.type, line_ref)
            return
        if isinstance(spec, t.CallableSpec):
            self._check_type_position(spec.parameters, line_ref)
            self._check_type_position(spec.result, line_ref)

    # --- top-level traversal --------------------------------------------

    def visit_toplevel(self, stmt: s.Statement) -> None:
        if isinstance(stmt, s.FunctionStatement):
            self._check_function(stmt, this_type=None)
        elif isinstance(stmt, s.ClassStatement):
            self._check_class(stmt)
        elif isinstance(stmt, s.EnumStatement):
            self._check_enum(stmt)
        elif isinstance(stmt, s.LetStatement):
            # A global linear value can never be discharged.
            if self.carries_linearity(stmt.declared_type):
                self.errors.append(Error(stmt.line_ref,
                    "linear value not allowed in a global let"))

    def _check_enum(self, enum: s.EnumStatement) -> None:
        # v1 does not trace a linear value stored in an enum variant — reject
        # it at the declaration so it cannot be leaked or aliased through the
        # enum. `_collect_data_fields` flattens fields across all variants.
        for _fname, ftype in enum._collect_data_fields():
            if self.carries_linearity(ftype):
                self.errors.append(Error(enum.line_ref,
                    "a linear value may not be stored in an enum"))
            self._check_type_position(ftype, enum.line_ref)

    def _check_class(self, cls: s.ClassStatement) -> None:
        is_linear = "linear" in cls.attributes
        for fld in cls.get_fields(self.resolver):
            if not is_linear and self.carries_linearity(fld.declared_type):
                self.errors.append(Error(cls.line_ref,
                    "a class with a linear field must be declared [linear]"))
            self._check_type_position(fld.declared_type, fld.line_ref)
        this_type = cls.get_type() if is_linear else None
        for member in cls.statements:
            if isinstance(member, s.FunctionStatement):
                self._check_function(member, this_type=this_type)

    def _check_function(self, fn: s.FunctionStatement, this_type: t.ClassSpec | None) -> None:
        params = fn.parameters.flatten()
        # Structural checks on the signature.
        for prm in params:
            self._check_type_position(prm.declared_type, prm.line_ref)
        self._check_type_position(fn.return_type, fn.line_ref)

        # [foreign] functions: the C side is unchecked; forbid linear types
        # crossing the boundary entirely.
        if "foreign" in fn.attributes:
            if any(self.carries_linearity(p.declared_type) for p in params) \
                    or self.carries_linearity(fn.return_type):
                self.errors.append(Error(fn.line_ref,
                    "[foreign] functions may not name a linear type"))
            return
        if fn.body is None:
            return

        # A linear parameter must be consumed exactly once — unless it is
        # explicitly opted out with `[terminal]`. `[terminal]` on the method
        # itself opts out the implicit `this` (e.g. IO.close()); `[terminal]`
        # on a parameter opts out that parameter. There is no implicit drop:
        # a function that quietly discards a linear value is an error.
        env: dict[str, t.TypeSpec] = {}
        if this_type is not None and "terminal" not in fn.attributes:
            env["this"] = this_type
        for prm in params:
            if (prm.declared_type is not None
                    and self.carries_linearity(prm.declared_type)
                    and "terminal" not in prm.attributes):
                env[prm.name] = prm.declared_type

        body_resolver = g.ResolverData(
            g.ResolverType(self.resolver, fn._find_generic_types),
            self._params_finder(params))
        self._analyze_scope(fn.body, env, fn.line_ref, body_resolver)

    def _analyze_scope(self, body: e.Expression, env: dict[str, t.TypeSpec],
                       line_ref: LineRef, resolver: g.Resolver) -> None:
        """Check a function/lambda body: every linear binding discharged once."""
        counts = self._count(body, env, resolver)
        for name, spec in env.items():
            self._discharge(name, self.leaves(spec), counts, line_ref, is_param=True)

    # --- the count flow analysis ----------------------------------------

    def _count(self, expr: e.Expression, env: dict[str, t.TypeSpec],
               resolver: g.Resolver) -> Counter:
        """Per-execution-path consumption of `env`'s obligations by `expr`."""
        if isinstance(expr, (e.NamedExpression, e.DotExpression)):
            return self._count_path(expr, env)

        if isinstance(expr, e.CallExpression):
            fn = expr.function
            # A method call `recv.method(args)` passes `recv` as `this`.
            # Counting the method-access DotExpression directly would treat
            # the receiver as a borrow; count the receiver itself instead.
            if isinstance(fn, e.DotExpression):
                return self._count(fn.base, env, resolver) + self._count(expr.parameter, env, resolver)
            return self._count(fn, env, resolver) + self._count(expr.parameter, env, resolver)

        if isinstance(expr, e.TupleExpression):
            total: Counter = Counter()
            for entry in expr.expressions:
                total += self._count(entry.value, env, resolver)
            return total

        if isinstance(expr, e.NewExpression):
            return self._count(expr.parameter, env, resolver)

        if isinstance(expr, e.ArrayReadExpression):
            return self._count(expr.object, env, resolver) + self._count(expr.index, env, resolver)

        if isinstance(expr, e.NewEnumExpression):
            acc: Counter = Counter()
            for arg in expr.field_args.values():
                acc += self._count(arg, env, resolver)
            return acc

        if isinstance(expr, e.BuiltinOpExpression):
            return self._count(expr.params, env, resolver)

        # BoxExpression wraps a sub-expression to widen it into a union. It may
        # not be present this early in the pipeline, but recursing into `inner`
        # is correct whether or not it is.
        if isinstance(expr, e.BoxExpression):
            return self._count(expr.inner, env, resolver)

        if isinstance(expr, e.TernaryExpression):
            cond = self._count(expr.condition, env, resolver)
            t_branch = self._count(expr.trueResult, env, resolver)
            f_branch = self._count(expr.falseResult, env, resolver)
            return cond + self._merge(t_branch, f_branch, expr.line_ref)

        if isinstance(expr, m.MatchExpression):
            total = self._count(expr.subject, env, resolver)
            arm_counts: list[Counter] = []
            for arm in expr.arms:
                arm_env = dict(env)
                arm_obls: list[tuple[str, set[Path]]] = []
                arm_resolver = resolver
                if arm.name and arm.name != "_":
                    arm_resolver = g.ResolverData(resolver, self._arm_finder(arm))
                if arm.name and arm.name != "_" and arm.type_spec is not None \
                        and self.carries_linearity(arm.type_spec):
                    arm_env[arm.name] = arm.type_spec
                    arm_obls.append((arm.name, self.leaves(arm.type_spec)))
                c = self._count(arm.body, arm_env, arm_resolver)
                for nm, leaves in arm_obls:
                    self._discharge(nm, leaves, c, arm.line_ref)
                    for leaf in leaves:
                        c.pop((nm, leaf), None)
                arm_counts.append(c)
            merged: Counter = Counter()
            first = True
            for c in arm_counts:
                merged = c if first else self._merge(merged, c, expr.line_ref)
                first = False
            return total + merged

        if isinstance(expr, e.BlockExpression):
            return self._count_block(expr, env, resolver)

        if isinstance(expr, e.LambdaExpression):
            self._check_capture(expr.expression, env, expr.line_ref)
            self._check_lambda(expr, resolver)
            return Counter()

        if isinstance(expr, e.ParallelExpression):
            for sub in expr.exprs:
                self._check_capture(sub, env, expr.line_ref)
                self._count(sub, env, resolver)
            return Counter()

        # Literals carry no linear value. Any other node is unexpected —
        # fail loudly rather than silently miss a possible consumption.
        if isinstance(expr, (e.StringExpression, e.IntegerExpression,
                             e.FloatExpression, e.BoolExpression, e.NothingExpression)):
            return Counter()
        raise AssertionError(
            f"linearity: unhandled expression node {type(expr).__name__}")

    def _count_block(self, block: e.BlockExpression, env: dict[str, t.TypeSpec],
                     resolver: g.Resolver) -> Counter:
        resolver = g.ResolverData(resolver, block._find_locals())
        return self._count_statement_list(block.statements, env, resolver,
                                          trailing_value=block.value)

    def _count_statement_list(self, stmts: list[s.Statement],
                              env: dict[str, t.TypeSpec], resolver: g.Resolver,
                              trailing_value: e.Expression | None = None) -> Counter:
        """Count linearity uses across a list of statements forming a scope.

        Used both for `BlockExpression` (with a trailing value) and for
        `if`/`else` branches (no trailing value). Lets declared here are
        local to the scope and are discharged before returning.
        """
        local_env = dict(env)
        local_bindings: list[tuple[str, t.TypeSpec, LineRef]] = []
        total: Counter = Counter()

        for stmt in stmts:
            if isinstance(stmt, s.FunctionStatement):
                # A nested function is its own scope; it may not capture
                # an enclosing linear binding.  Returning a linear type
                # is fine — each invocation mints one obligation that
                # the caller threads (see stdlib's `?>` continuations).
                if stmt.body is not None:
                    self._check_capture(stmt.body, local_env, stmt.line_ref)
                self._check_function(stmt, this_type=None)
                continue
            if isinstance(stmt, s.DestructureStatement):
                total += self._count(stmt.default_value, local_env, resolver) if stmt.default_value else Counter()
                for tgt in stmt.targets:
                    if tgt.declared_type is not None and self.carries_linearity(tgt.declared_type):
                        local_env[tgt.name] = tgt.declared_type
                        local_bindings.append((tgt.name, tgt.declared_type, tgt.line_ref))
                continue
            if isinstance(stmt, s.LetStatement):
                # `[lazy]` lets defer their RHS into a closure that
                # memoises the result across forces.  A linear value
                # held in the stub would be readable many times via
                # repeat forces, and free variables of linear type
                # captured by the synthesised closure body fall under
                # the same "captured by a nested function or lambda"
                # rule.  Reject both at declaration.
                if stmt.is_deferred_init():
                    if (stmt.declared_type is not None
                            and self.carries_linearity(stmt.declared_type)):
                        self.errors.append(Error(stmt.line_ref,
                            f"[lazy] let '{stmt.name}' may not hold a "
                            f"linear value — the stub memoises across "
                            f"forces, so multiple reads would yield "
                            f"the same linear instance"))
                    if stmt.default_value is not None:
                        self._check_capture(stmt.default_value, local_env, stmt.line_ref)
                total += self._count(stmt.default_value, local_env, resolver) if stmt.default_value else Counter()
                if stmt.declared_type is not None and self.carries_linearity(stmt.declared_type):
                    local_env[stmt.name] = stmt.declared_type
                    local_bindings.append((stmt.name, stmt.declared_type, stmt.line_ref))
                continue
            if isinstance(stmt, s.ReturnStatement):
                total += self._count(stmt.value, local_env, resolver)
                continue
            if isinstance(stmt, s.ActionStatement):
                # A statement-expression may consume a linear binding (e.g.
                # `io.close()`) — that is fine. But a *fresh* linear value
                # produced and dropped here leaks: bind and consume it.
                total += self._count(stmt.action, local_env, resolver)
                if self._expr_is_linear(stmt.action, resolver):
                    self.errors.append(Error(stmt.line_ref,
                        "linear value is discarded; bind it and consume it"))
                continue
            if isinstance(stmt, s.IfStatement):
                # Condition runs unconditionally; the two branches are
                # alternative paths and must be merged. Each branch is its
                # own scope — lets inside a branch are branch-local.
                total += self._count(stmt.condition, local_env, resolver)
                t_res = g.ResolverData(resolver, stmt._branch_finder(stmt.true_block))
                f_res = g.ResolverData(resolver, stmt._branch_finder(stmt.false_block))
                t_branch = self._count_statement_list(stmt.true_block, local_env, t_res)
                f_branch = self._count_statement_list(stmt.false_block, local_env, f_res)
                total += self._merge(t_branch, f_branch, stmt.line_ref)
                continue
            if isinstance(stmt, (s.ClassStatement, s.EnumStatement)):
                # A nested type declaration — check it as its own scope.
                self.visit_toplevel(stmt)
                continue
            if isinstance(stmt, (s.TypeAliasStatement, s.ImportStatement,
                                 s.NamespaceStatement)):
                continue  # carries no linear-consuming expression
            # Any other statement kind could silently miss a linear use —
            # fail loudly so a new node type is handled deliberately.
            raise AssertionError(
                f"linearity: unhandled statement node {type(stmt).__name__}")

        if trailing_value is not None:
            total += self._count(trailing_value, local_env, resolver)

        # Discharge every linear binding declared in this scope, then drop
        # its obligations so they don't leak into the enclosing merge.
        for name, spec, lr in local_bindings:
            leaves = self.leaves(spec)
            self._discharge(name, leaves, total, lr)
            for leaf in leaves:
                total.pop((name, leaf), None)
        return total

    def _count_path(self, expr: e.Expression, env: dict[str, t.TypeSpec]) -> Counter:
        resolved = _resolve_path(expr)
        if resolved is None:
            return Counter()
        root, path = resolved
        if root not in env:
            return Counter()
        leaves = self.leaves(env[root])
        # A path-expr moves every leaf that has `path` as a prefix; a path
        # that runs past a leaf (into a non-linear field) moves nothing.
        return Counter((root, leaf) for leaf in leaves if _is_prefix(path, leaf))

    # --- helpers ---------------------------------------------------------

    def _merge(self, c1: Counter, c2: Counter, line_ref: LineRef) -> Counter:
        for obl in set(c1) | set(c2):
            if c1.get(obl, 0) != c2.get(obl, 0):
                name = obl[0]
                self.errors.append(Error(line_ref,
                    f"linear value '{name}' is used inconsistently across branches"))
        return c1 if c1 else c2

    def _discharge(self, name: str, leaves: set[Path], counts: Counter,
                   line_ref: LineRef, is_param: bool = False) -> None:
        """Check one binding's obligations: each must be consumed exactly once.
        `is_param` adds a `[terminal]` hint (only a parameter can be marked)."""
        for leaf in leaves:
            n = counts.get((name, leaf), 0)
            if n > 1:
                self.errors.append(Error(line_ref,
                    f"linear value '{name}' is used {n} times; must be used once"))
            elif n == 0:
                hint = (" (mark the parameter [terminal] if this is its terminus)"
                        if is_param else "")
                self.errors.append(Error(line_ref,
                    f"linear value '{name}' is never used; it must be consumed once"
                    + hint))

    def _params_finder(self, params: list[s.LetStatement]):
        """A resolver scope exposing `params` as locals — enough for typing
        the action expressions in a body (trait data is not needed here)."""
        def finder(query: str) -> list:
            return [g.Resolved(p.name, p, g.ResolvedScope.LOCAL)
                    for p in params if g.name_matches(p.name, query)]
        return finder

    def _arm_finder(self, arm: m.MatchArm):
        """A resolver scope exposing a match arm's bound variable."""
        def finder(query: str) -> list:
            if arm.name and arm.name != "_" and g.name_matches(arm.name, query):
                let = s.LetStatement(arm.line_ref, arm.name, None, {}, (),
                                     None, arm.type_spec)
                return [g.Resolved(arm.name, let, g.ResolvedScope.LOCAL)]
            return []
        return finder

    def _check_capture(self, body: e.Expression, env: dict[str, t.TypeSpec],
                       line_ref: LineRef) -> None:
        """A lambda / nested function must not reference an enclosing linear
        binding — it may run zero or many times, which would break linearity.

        This is a blind name scan; it is sound only because every binding is
        given a path-unique name before this pass runs, so an inner parameter
        can never collide with an outer linear binding's name."""
        captured: set[str] = set()

        def visit(_, thing):
            if isinstance(thing, e.NamedExpression) and thing.name in env:
                captured.add(thing.name)
            return thing
        body.search_and_replace(self.resolver, visit)
        for name in sorted(captured):
            self.errors.append(Error(line_ref,
                f"linear value '{name}' captured by a nested function or lambda"))

    # --- generic instantiation kind check -------------------------------

    def check_instantiations(self, statements: list[s.Statement]) -> None:
        """A linear type argument may only be bound to a `[linear]` type
        parameter. Plain `<T>` parameters and all generic classes/enums are
        unrestricted and reject linear arguments."""
        def visit(_, thing):
            if isinstance(thing, e.NamedExpression) and thing.type_params:
                self._check_instantiation(thing.name, thing.type_params,
                                          thing.line_ref, is_type=False)
            elif isinstance(thing, t.ClassSpec) and thing.type_params:
                self._check_instantiation(thing.name, thing.type_params,
                                          thing.line_ref, is_type=True)
            elif isinstance(thing, t.EnumSpec) and thing.type_params:
                self._check_instantiation(thing.root_name, thing.type_params,
                                          thing.line_ref, is_type=True)
            return thing
        for stmt in statements:
            stmt.search_and_replace(self.resolver, visit)

    def _check_instantiation(self, name: str, type_args: tuple[t.TypeSpec, ...],
                             line_ref: LineRef, is_type: bool) -> None:
        found = (self.resolver.find_type(name) if is_type
                 else self.resolver.find_data(name))
        if len(found) != 1:
            return
        tparams = getattr(found[0].statement, "type_params", ()) or ()
        for tp, ta in zip(tparams, type_args):
            if self.carries_linearity(ta) and "linear" not in tp.attributes:
                self.errors.append(Error(line_ref,
                    "linear type cannot be passed to an unrestricted type parameter"))

    def _check_lambda(self, lam: e.LambdaExpression, resolver: g.Resolver) -> None:
        env: dict[str, t.TypeSpec] = {}
        for prm in lam.parameters.flatten():
            if (prm.declared_type is not None
                    and self.carries_linearity(prm.declared_type)
                    and "terminal" not in prm.attributes):
                env[prm.name] = prm.declared_type
        lam_resolver = g.ResolverData(resolver, lam._find_locals)
        self._analyze_scope(lam.expression, env, lam.line_ref, lam_resolver)

    def _expr_is_linear(self, expr: e.Expression, resolver: g.Resolver) -> bool:
        """True if `expr`'s result type carries linearity. Used to flag a
        fresh linear value dropped by a bare statement. Best-effort: if the
        type cannot be resolved, returns False (a documented v1 gap rather
        than a false positive)."""
        try:
            xtype = expr.get_type(resolver)
        except Exception:
            return False
        return self.carries_linearity(xtype)


# ─── path resolution ─────────────────────────────────────────────────────

def _resolve_path(expr: e.Expression) -> tuple[str, Path] | None:
    """A NamedExpression or DotExpression chain → (root name, field path)."""
    fields: list[str] = []
    while isinstance(expr, e.DotExpression):
        fields.append(expr.name)
        expr = expr.base
    if isinstance(expr, e.NamedExpression):
        return expr.name, tuple(reversed(fields))
    return None


def _is_prefix(prefix: Path, full: Path) -> bool:
    return len(prefix) <= len(full) and full[:len(prefix)] == prefix
