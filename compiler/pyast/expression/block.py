from __future__ import annotations

from typing import Callable, Any
import dataclasses
import random
from dataclasses import dataclass, field
from functools import reduce

from langtools import cast
from parsing.tokenizer import LineRef
from parsing.parselib import Error

import codegen.ops as cg_o
import codegen.param as cg_p
import codegen.typedecl as cg_t

import pyast.resolver as g
import pyast.statement as s
import pyast.typespec as t
import pyast.utils as u
from pyast.expression.base import Expression


def _bottom(b: g.OperationBundle) -> bool:
    """True if `b` ends by transferring control elsewhere and so never falls
    through to what follows (mirrors TernaryExpression's bottom test)."""
    return bool(b.operations) and isinstance(
        b.operations[-1],
        (cg_o.Jump, cg_o.Return, cg_o.ReturnVoid, cg_o.Abort, cg_o.SwitchJump))


def _stmts_fall_through(statements: list[s.Statement]) -> bool:
    """True if control can reach the end of this statement sequence — and hence
    the block's trailing value. False when every path diverges, e.g. the last
    statement is an `if`/`else` whose branches all `return`. A dead fall-through
    must contribute no Phi source, exactly as a bottom ternary branch doesn't."""
    return not any(_stmt_diverges(stmt) for stmt in statements)


def _stmt_diverges(stmt: s.Statement) -> bool:
    if isinstance(stmt, s.ReturnStatement):
        return True
    if isinstance(stmt, s.IfStatement):
        # Diverges only with a present else where neither branch falls through;
        # else-if chains are already folded into nested IfStatements by now.
        return (bool(stmt.false_block)
                and not _stmts_fall_through(stmt.true_block)
                and not _stmts_fall_through(stmt.false_block))
    return False


@dataclass(frozen=True)
class _BlockFrame:
    """Immutable generation-time context for one BlockExpression: a unique
    '@'-bearing `tag` so the block's end label and a nested `return`'s jump stay
    string-matched through `with_prefix`. Carried *down* to nested
    ReturnStatements via the resolver (g.ResolverBlock); the exit phi sources
    flow the other way, *up* through OperationBundle.exit_sources, so no mutable
    state crosses calls — the block-exit analogue of `_LoopFrame`."""
    tag: str

    @property
    def end_label(self) -> str:
        return f"blockend${self.tag}"   # tag carries '@' → with_prefix spares it


@dataclass
class BlockExpression(Expression):
    """A sequence of statements followed by a value expression.

    Used as the body of FunctionStatement and produced by the inliner
    when a call is substituted at expression position.

    The block is the unit a `return` exits: a `ReturnStatement` anywhere inside
    (however deeply nested in if/match) branches to this block's end, supplying
    its value as one source of the end Phi. The trailing `value` is the
    fall-through source. `tag` is a unique '@'-bearing identifier assigned by the
    `block_exits` lowering pass; it seeds the end label and the per-return exit
    labels so they survive `with_prefix` matched. A block with no `return`s
    inside generates exactly as a plain statements-then-value sequence.
    """
    statements: list[s.Statement]
    value: Expression
    tag: str | None = None

    def _find_locals(self) -> Callable[[str], list[g.Resolved]]:
        def finder(query: str) -> list[g.Resolved]:
            lets = [g.Resolved(let.name, let, g.ResolvedScope.LOCAL)
                    for x in self.statements if isinstance(x, s.LetStatement)
                    for let in x.flatten() if g.name_matches(let.name, query)]
            funs = [g.Resolved(fun.name, fun, g.ResolvedScope.LOCAL)
                    for fun in self.statements if isinstance(fun, s.FunctionStatement) and g.name_matches(fun.name, query)]
            return lets + funs
        return finder

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver, Any], Any]) -> Expression:
        nested = g.ResolverData(resolver, self._find_locals())
        new_stmts = [x.search_and_replace(nested, replace) for x in self.statements]
        new_val = self.value.search_and_replace(nested, replace)
        return cast(Expression, replace(resolver, dataclasses.replace(self, statements=new_stmts, value=new_val)))

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        nested = g.ResolverData(resolver, self._find_locals())
        return self.value.get_type(nested)

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement]]:
        statements = s.collapse_else_if(self.statements)
        nested = g.ResolverData(resolver, self._find_locals())
        stmt_results = [x.compile(nested, expected_type) for x in statements]
        new_stmts = [r[0] for r in stmt_results if r[0]]
        glbs: list[s.Statement] = [glb for r in stmt_results for glb in r[1]]
        new_val, val_glbs = self.value.compile(nested, expected_type)
        return dataclasses.replace(self, statements=new_stmts, value=new_val), glbs + val_glbs

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        nested = g.ResolverData(resolver, self._find_locals())
        stmt_errs = [err for x in self.statements for err in x.check(nested, expected_type)]
        val_errs = self.value.check(nested, expected_type)
        if not val_errs and expected_type is not None:
            xtype = self.value.get_type(nested)
            if xtype is not None and t.trivially_assignable_equals(nested, expected_type, xtype) is False:
                val_errs = [Error(self.value.line_ref, "Incorrect type")]
        return stmt_errs + val_errs

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        return self.generate_to(resolver, None)

    def generate_to(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> g.OperationBundle:
        # The block's value is in tail/value position, so the expected type flows
        # straight through to it (statements coerce themselves at their own sinks).
        # `slot_type` is the block's result type — shared by the trailing value
        # (fall-through) and every `return` (which coerces its value to it). A
        # ResolverBlock carries the exit frame down so a nested ReturnStatement
        # finds the end label and result type; the returns flow their
        # (exit-label, value) pairs back up via OperationBundle.exit_sources.
        slot_type = expected_type if expected_type is not None else self.get_type(resolver)
        tag = self.tag if self.tag is not None else f"blk@{self.line_ref.hash6()}"
        frame = _BlockFrame(tag)
        nested = g.ResolverData(g.ResolverBlock(resolver, frame), self._find_locals())
        bundle = g.OperationBundle()
        # Phase 1: hoist deferred-init stub allocations to block entry
        # so a forward reference inside one lazy body sees the
        # later-declared stub's slot already pointing at a real heap
        # object.  Block-local (not function-wide) — a deferred-init
        # let inside an if/match arm only allocates when that arm runs.
        for i, stmt in enumerate(self.statements):
            if (isinstance(stmt, s.LetStatement)
                    and stmt.is_deferred_init()
                    and stmt.declared_type is not None):
                bundle = bundle + stmt.generate_lazy_alloc(nested).with_prefix(f"alloc_s{i}")
        # Phase 2: walk statements in order.  Deferred-init lets emit
        # only the closure-population Move now — their stub allocation
        # was hoisted above.
        for i, stmt in enumerate(self.statements):
            if (isinstance(stmt, s.LetStatement)
                    and stmt.is_deferred_init()
                    and stmt.declared_type is not None):
                bundle = bundle + stmt.generate_lazy_populate(nested).with_prefix(f"s{i}")
            else:
                bundle = bundle + stmt.generate(nested, None).with_prefix(f"s{i}")
        stmts_bundle = bundle

        # No `return` reached this block — generate exactly as a plain
        # statements-then-value sequence (the overwhelmingly common case).
        if not stmts_bundle.exit_sources:
            return stmts_bundle + self.value.generate_to(nested, slot_type)

        # `return`s are present: merge their values with the fall-through value
        # at the block's end label via a Phi. The end label and the fall-through
        # exit label carry the '@'-bearing tag so they survive with_prefix and
        # string-match the returns' jumps and up-flowed exit_sources.
        end_label = frame.end_label
        ft_exit = f"blockftexit${tag}"
        ops = list(stmts_bundle.operations)
        stack_vars = list(stmts_bundle.stack_vars)
        recur = stmts_bundle.recur_sources
        sources = list(stmts_bundle.exit_sources)

        # The fall-through to the trailing value reaches the end label only when
        # control can actually fall off the statements (not every path returned)
        # *and* the value itself doesn't divert (a [tail] recur, say). When it
        # can't, the value is dead: don't generate it, and terminate the
        # statements' dead tail so the end label has no spurious predecessor —
        # the same bottom-handling the ternary does, so we never feed a Phi a
        # source for an unreachable edge (which a later pass would prune away).
        ft_value: cg_p.RParam | None = None
        reaches_end = False
        if _stmts_fall_through(self.statements):
            vbun = self.value.generate_to(nested, slot_type)
            ops += list(vbun.operations)
            stack_vars += list(vbun.stack_vars)
            recur = recur + vbun.recur_sources
            sources += list(vbun.exit_sources)
            if not _bottom(vbun):
                reaches_end = True
                ft_value = vbun.result_var
        else:
            ops.append(cg_o.Abort("unreachable: every path through the block returned"))

        if slot_type is None:
            # Unit / control-only block: no value to merge, just a merge point.
            if reaches_end:
                ops.append(cg_o.Label(ft_exit))
            ops.append(cg_o.Label(end_label))
            return g.OperationBundle(tuple(stack_vars), tuple(ops),
                                     result_var=None, recur_sources=recur)

        result_var = cg_p.StackVar(slot_type.generate(resolver), f"blockresult${tag}")
        if reaches_end:
            fv = ft_value if ft_value is not None else cg_p.ZeroOf(result_var.get_type())
            ops.append(cg_o.Label(ft_exit))
            sources.append((ft_exit, fv))
        ops += [cg_o.Label(end_label), cg_o.Phi(target=result_var, sources=tuple(sources))]
        stack_vars.append(result_var)
        return g.OperationBundle(tuple(stack_vars), tuple(ops),
                                 result_var=result_var, recur_sources=recur)



