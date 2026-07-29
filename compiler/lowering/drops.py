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

Two granularities, both WHOLE bindings only (params, block lets, destructure
targets); a partially-moved aggregate's leftover field and `_`-named linear
bindings keep today's linearity errors:

1. Scope level: a binding referenced NOWHERE in its scope drops at the
   scope's exit (batched, one `$drop_keep` temporary per scope).
2. Path level: a binding consumed on some control paths but not others gets
   its drop inserted on each abandoning path — the non-consuming branch of a
   ternary or match, and the value of an early `ret` whose path skips the
   consumption. Mirrors the linearity checker's per-path exactly-once merge;
   any shape outside it (double use, a reference under a lambda or match
   guard) bails out and keeps the checker's error.

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
import pyast.match as m
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
        params = fn.parameters.flatten()
        referenced = u.referenced_names(body)
        drops = self.__unused_droppable(params, referenced, fn.trait_params)
        if drops:
            body = self.__with_drops(body, drops)
            self.changed = True
        for let in self.__partially_used_droppable(params, referenced, fn.trait_params):
            body = self.__balance(body, let)
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
        if drops:
            self.changed = True
            block = self.__with_drops(block, drops)
        for let in self.__partially_used_droppable(lets, referenced, fn_trait_params):
            block = self.__balance(block, let)
        return block

    def __rewrite_lambda(self, lam: e.LambdaExpression,
                         fn_trait_params: tuple[t.TypeSpec, ...]) -> e.LambdaExpression:
        params = lam.parameters.flatten()
        referenced = u.referenced_names(lam.expression)
        expression = lam.expression
        drops = self.__unused_droppable(params, referenced, fn_trait_params)
        if drops:
            self.changed = True
            expression = self.__with_drops(expression, drops)
        for let in self.__partially_used_droppable(params, referenced, fn_trait_params):
            expression = self.__balance(expression, let)
        return (dataclasses.replace(lam, expression=expression)
                if expression is not lam.expression else lam)

    def __eligible(self, let: s.LetStatement,
                   fn_trait_params: tuple[t.TypeSpec, ...]) -> bool:
        return (not g.bare_name(let.name).startswith("_")
                and g.bare_name(let.name) != "this"
                and "terminal" not in let.attributes
                and not let.is_deferred_init()
                and self.__droppable(let.declared_type, fn_trait_params))

    def __unused_droppable(self, lets: list[s.LetStatement], referenced: set[str],
                           fn_trait_params: tuple[t.TypeSpec, ...]) -> list[s.LetStatement]:
        return [let for let in lets
                if let.name not in referenced and self.__eligible(let, fn_trait_params)]

    def __partially_used_droppable(self, lets: list[s.LetStatement], referenced: set[str],
                                   fn_trait_params: tuple[t.TypeSpec, ...]) -> list[s.LetStatement]:
        return [let for let in lets
                if let.name in referenced and self.__eligible(let, fn_trait_params)]

    def __drop_call(self, let: s.LetStatement) -> s.Statement:
        # dropIndirect, not drop: a bare call to a GENERIC instance's
        # member can't infer the instance's type params; the trampoline
        # latches T from its argument and discharges `where Drop<T>` at
        # monomorphisation (generic instances included).
        return s.ActionStatement(let.line_ref, e.CallExpression(
            let.line_ref,
            e.NamedExpression(let.line_ref, "dropIndirect"),
            e.TupleExpression(let.line_ref, [
                e.TupleEntryExpression(None, e.NamedExpression(let.line_ref, let.name))])))

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
        stmts = (stmts
                 + [s.LetStatement(lr, keep, None, {}, (), value, None)]
                 + [self.__drop_call(let) for let in drops])
        return e.BlockExpression(lr, stmts, e.NamedExpression(lr, keep))

    # ── path-level balancing ──────────────────────────────────────────────

    def __balance(self, body: e.Expression, let: s.LetStatement) -> e.Expression:
        """`body`'s scope references droppable `let` on SOME paths: insert a
        drop on each path that abandons it, so every path consumes it exactly
        once (the linearity checker's merge rule). Anything outside that shape
        — double use, a reference under a lambda or a match guard — bails out
        unchanged, keeping the checker's error."""
        name = let.name
        did = [False]

        def refs(node) -> bool:
            return node is not None and name in u.referenced_names(node)

        def refs_any(stmts) -> bool:
            return any(refs(st) for st in stmts)

        def dropped(expr: e.Expression) -> e.Expression:
            did[0] = True
            return self.__with_drops(expr, [let])

        # Divergence INSIDE an expression: ternary/match branches. Bottom-up,
        # so a fixed inner branch counts as consumption for its parent.
        def visit(_, thing):
            # A reference under a lambda or nested function is a capture;
            # keep the checker's error.
            if isinstance(thing, (e.LambdaExpression, s.FunctionStatement)) and refs(thing):
                raise _Bail()
            if isinstance(thing, e.TernaryExpression):
                return fix_ternary(thing)
            if isinstance(thing, m.MatchExpression):
                return fix_match(thing)
            return rw.UNCHANGED

        def fix_expr(expr: e.Expression) -> e.Expression:
            return rw.resolved(expr.search_and_replace(None, visit), expr)

        def fix_stmt(st: s.Statement) -> s.Statement:
            return rw.resolved(st.search_and_replace(None, visit), st)

        def fix_ternary(tern: e.TernaryExpression):
            if refs(tern.condition):
                if refs(tern.trueResult) or refs(tern.falseResult):
                    raise _Bail()   # condition consumed it; branch re-use is an error
                return rw.UNCHANGED
            t_refs, f_refs = refs(tern.trueResult), refs(tern.falseResult)
            if t_refs == f_refs:
                return rw.UNCHANGED
            if t_refs:
                return dataclasses.replace(tern, falseResult=dropped(tern.falseResult))
            return dataclasses.replace(tern, trueResult=dropped(tern.trueResult))

        def fix_match(match: m.MatchExpression):
            if any(refs(arm.guard) for arm in match.arms):
                raise _Bail()   # a guard runs on fall-through paths too
            if refs(match.subject):
                if any(refs(arm.body) for arm in match.arms):
                    raise _Bail()
                return rw.UNCHANGED
            arm_refs = [refs(arm.body) for arm in match.arms]
            if all(arm_refs) or not any(arm_refs):
                return rw.UNCHANGED
            return dataclasses.replace(match, arms=[
                arm if consumed else dataclasses.replace(arm, body=dropped(arm.body))
                for arm, consumed in zip(match.arms, arm_refs)])

        # Path accounting through a statement list. `tail_consumes` says the
        # caller's continuation consumes on fall-through. Every path must
        # total exactly one consumption.
        def ensure_stmts(stmts: list[s.Statement], value: e.Expression | None,
                         tail_consumes: bool) -> tuple[list[s.Statement], e.Expression | None]:
            out: list[s.Statement] = []
            consumed = False
            for i, st in enumerate(stmts):
                later = refs_any(stmts[i + 1:]) or refs(value) or tail_consumes
                if isinstance(st, s.ReturnStatement):
                    # This path exits the function here; the tail never runs.
                    need = 1 - int(consumed) - int(refs(st.value))
                    if need < 0:
                        raise _Bail()
                    new_value = fix_expr(st.value) if refs(st.value) else st.value
                    if need == 1:
                        new_value = dropped(new_value)
                    out.append(dataclasses.replace(st, value=new_value)
                               if new_value is not st.value else st)
                    out.extend(stmts[i + 1:])   # unreachable; keep as-is
                    return out, value
                if isinstance(st, s.IfStatement):
                    out.append(ensure_if(st, consumed, later))
                    # Falling branches were made to consume exactly when
                    # nothing before or after this `if` does.
                    if not (_Checker._terminates(st.true_block)
                            and _Checker._terminates(st.false_block)):
                        consumed = consumed or not later
                    continue
                if refs(st):
                    if consumed:
                        raise _Bail()
                    out.append(fix_stmt(st))
                    consumed = True
                else:
                    out.append(st)
            need = 1 - int(consumed) - int(refs(value)) - int(tail_consumes)
            if need < 0:
                raise _Bail()
            new_value = fix_expr(value) if refs(value) else value
            if need == 1:
                if new_value is None:
                    out.append(self.__drop_call(let))
                    did[0] = True
                else:
                    new_value = dropped(new_value)
            return out, new_value

        def ensure_if(st: s.IfStatement, consumed: bool, later: bool) -> s.IfStatement:
            if refs(st.condition):
                if consumed or later or refs_any(st.true_block) or refs_any(st.false_block):
                    raise _Bail()
                return dataclasses.replace(st, condition=fix_expr(st.condition))
            def branch(blk: list[s.Statement]) -> list[s.Statement]:
                terminates = _Checker._terminates(blk)
                # A terminating branch never reaches the tail; a falling one does.
                need = 1 - int(consumed) - (0 if terminates else int(later))
                if need < 0:
                    raise _Bail()
                if need == 0:
                    if refs_any(blk):
                        raise _Bail()
                    return blk
                new_blk, _ = ensure_stmts(blk, None, tail_consumes=False)
                return new_blk
            true_block = branch(st.true_block)
            false_block = branch(st.false_block)
            if true_block is st.true_block and false_block is st.false_block:
                return st
            return dataclasses.replace(st, true_block=true_block, false_block=false_block)

        stmts = list(body.statements) if isinstance(body, e.BlockExpression) else []
        value = body.value if isinstance(body, e.BlockExpression) else body
        try:
            new_stmts, new_value = ensure_stmts(stmts, value, tail_consumes=False)
        except _Bail:
            return body
        if not did[0]:
            return body
        self.changed = True
        return e.BlockExpression(body.line_ref, new_stmts, new_value)


class _Bail(Exception):
    """Path-level balancing met a shape outside the exactly-once rule; the
    binding keeps its linearity-checker error."""
