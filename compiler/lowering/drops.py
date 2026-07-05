"""Affine drop insertion — scope-exit auto-release of unused linear bindings.

A `[linear]` binding that is never referenced in its scope would fail the
linearity check ("never used; must be consumed once"). When the binding's type
has a `Drop` instance in scope, this pass consumes it by policy instead: the
scope's result is bound to a temporary, a `drop(x)` call is appended for each
such binding (scope-EXIT timing — after the value is computed, so a derived
view like `asStream`'s StreamIO is fully drained first), and the temporary is
returned. The rewritten calls then resolve through the ordinary compile
fixpoint (the caller re-converges), and the linearity checker sees plain
consumption — it needs no knowledge of drops at all.

Deliberately narrow (phase 1): only WHOLE bindings (params, block lets,
destructure targets) that are referenced NOWHERE in their scope. A binding
consumed on some paths but not others, a partially-moved aggregate's leftover
field, and `_`-named linear bindings all keep today's linearity errors.
Early-returning scopes also keep erroring: the appended drop only covers the
fall-through path, and the checker's branch merge reports the inconsistency.

Droppability is decided HERE, pre-monomorphisation, so error reporting never
moves: a concrete type must have a `[trait]` instance implementing
`System::Drop<T>` in the program; a `[linear] T` placeholder must appear in
the enclosing function's own `where Drop<T>` (current constraint semantics —
the caller then proves it at the call site).
"""
from __future__ import annotations

import dataclasses
import pyast.rewrite as rw

import pyast.expression as e
import pyast.statement as s
import pyast.typespec as t
import pyast.resolver as g
import pyast.utils as u
from lowering.linearity import _Checker


def insert_drops(statements: list[s.Statement]) -> tuple[list[s.Statement], bool]:
    """Rewrite `statements`, appending scope-exit `drop(x)` calls for unused
    droppable linear bindings. Returns (new_statements, changed)."""
    resolver = g.ResolverRoot(statements)
    inserter = _Inserter(resolver, statements)
    new_statements = [inserter.rewrite_toplevel(stmt) for stmt in statements]
    return (new_statements, True) if inserter.changed else (statements, False)


class _Inserter:
    def __init__(self, resolver: g.Resolver, statements: list[s.Statement]):
        self.resolver = resolver
        self.checker = _Checker(resolver)
        found = resolver.find_type("System::Drop")
        # None when the program has no Drop interface at all (no stdlib):
        # nothing is droppable and every unused linear binding keeps its error.
        self._drop_name: str | None = (
            found[0].statement.name if len(found) == 1 else None)
        self.droppable_ids = self.__droppable_type_ids(statements)
        self.changed = False

    def __droppable_type_ids(self, statements: list[s.Statement]) -> frozenset[str]:
        """Unique ids of every concrete T with a `[trait]` instance whose
        witness implements System::Drop<T>."""
        if self._drop_name is None:
            return frozenset()
        out: set[str] = set()
        for st in self.resolver.get_traits():
            dt = st.declared_type
            if not isinstance(dt, t.ClassSpec):
                continue
            found = self.resolver.find_type(dt.name)
            if len(found) != 1 or not isinstance(found[0].statement, s.ClassStatement):
                continue
            cls = found[0].statement
            if cls._all_parents is None:
                continue
            for parent in cls._all_parents:
                if (isinstance(parent, t.ClassSpec) and parent.name == self._drop_name
                        and len(parent.type_params) == 1):
                    uid = parent.type_params[0].as_unique_id_str()
                    if uid is not None:
                        out.add(uid)
        return frozenset(out)

    # ── droppability ──────────────────────────────────────────────────────

    def __droppable(self, spec: t.TypeSpec | None,
                    fn_trait_params: tuple[t.TypeSpec, ...]) -> bool:
        if spec is None or not self.checker.carries_linearity(spec):
            return False
        uid = spec.as_unique_id_str()
        if uid is not None:
            return uid in self.droppable_ids
        # A generic placeholder is droppable iff the enclosing function itself
        # declares `where Drop<T>` for it (current constraint semantics).
        if isinstance(spec, t.GenericPlaceholderSpec) and self._drop_name is not None:
            return any(isinstance(wc, t.ClassSpec) and wc.name == self._drop_name
                       and len(wc.type_params) == 1
                       and isinstance(wc.type_params[0], t.GenericPlaceholderSpec)
                       and wc.type_params[0].name == spec.name
                       for wc in fn_trait_params)
        return False

    # ── rewriting ─────────────────────────────────────────────────────────

    def rewrite_toplevel(self, stmt: s.Statement) -> s.Statement:
        if isinstance(stmt, s.ClassStatement):
            return dataclasses.replace(stmt, statements=[
                self.__rewrite_fn(m) if isinstance(m, s.FunctionStatement) else m
                for m in stmt.statements])
        if isinstance(stmt, s.FunctionStatement):
            return self.__rewrite_fn(stmt)
        return stmt

    def __rewrite_fn(self, fn: s.FunctionStatement) -> s.FunctionStatement:
        if fn.body is None or "foreign" in fn.attributes:
            return fn
        body = self.__rewrite_expr(fn.body, fn.trait_params)
        # Unused droppable parameters drop at the body's exit.
        drops = self.__unused_droppable(
            fn.parameters.flatten(), u.referenced_names(body), fn.trait_params)
        if drops:
            body = self.__with_drops(body, drops)
            self.changed = True
        return dataclasses.replace(fn, body=body) if body is not fn.body else fn

    def __rewrite_expr(self, expr: e.Expression,
                       fn_trait_params: tuple[t.TypeSpec, ...]) -> e.Expression:
        def visit(_, thing):
            if isinstance(thing, e.BlockExpression):
                return self.__rewrite_block(thing, fn_trait_params)
            if isinstance(thing, e.LambdaExpression):
                return self.__rewrite_lambda(thing, fn_trait_params)
            return rw.UNCHANGED
        return rw.resolved(expr.search_and_replace(None, visit), expr)

    def __rewrite_block(self, block: e.BlockExpression,
                        fn_trait_params: tuple[t.TypeSpec, ...]) -> e.BlockExpression:
        # (children are already rewritten: search_and_replace is bottom-up)
        lets = u.binding_lets(block.statements)
        referenced: set[str] = set()
        for stmt in block.statements:
            referenced |= u.referenced_names(stmt)
        referenced |= u.referenced_names(block.value)
        drops = self.__unused_droppable(lets, referenced, fn_trait_params)
        if not drops:
            return block
        self.changed = True
        rewritten = self.__with_drops(block, drops)
        return rewritten

    def __rewrite_lambda(self, lam: e.LambdaExpression,
                         fn_trait_params: tuple[t.TypeSpec, ...]) -> e.LambdaExpression:
        drops = self.__unused_droppable(
            lam.parameters.flatten(), u.referenced_names(lam.expression), fn_trait_params)
        if not drops:
            return lam
        self.changed = True
        return dataclasses.replace(
            lam, expression=self.__with_drops(lam.expression, drops))

    def __unused_droppable(self, lets: list[s.LetStatement], referenced: set[str],
                           fn_trait_params: tuple[t.TypeSpec, ...]) -> list[s.LetStatement]:
        return [let for let in lets
                if let.name not in referenced
                and not g.bare_name(let.name).startswith("_")
                and g.bare_name(let.name) != "this"
                and "terminal" not in let.attributes
                and not let.is_deferred_init()
                and self.__droppable(let.declared_type, fn_trait_params)]

    def __with_drops(self, body: e.Expression,
                     drops: list[s.LetStatement]) -> e.BlockExpression:
        """`body` extended so each of `drops` is released at scope exit: the
        original value is computed FIRST (a derived non-linear view of a
        dropped handle must be drained before the close), then the drops run,
        then the saved value is the result."""
        lr = body.line_ref
        stmts = list(body.statements) if isinstance(body, e.BlockExpression) else []
        value = body.value if isinstance(body, e.BlockExpression) else body
        keep = f"$drop_keep@{lr.hash6()}"
        def drop_call(let: s.LetStatement) -> s.Statement:
            return s.ActionStatement(let.line_ref, e.CallExpression(
                let.line_ref,
                e.NamedExpression(let.line_ref, "drop"),
                e.TupleExpression(let.line_ref, [
                    e.TupleEntryExpression(None, e.NamedExpression(let.line_ref, let.name))])))
        stmts = (stmts
                 + [s.LetStatement(lr, keep, None, {}, (), value, None)]
                 + [drop_call(let) for let in drops])
        return e.BlockExpression(lr, stmts, e.NamedExpression(lr, keep))
