"""Statement-position control flow: `return` (a block-scoped exit), action
expressions, and the if/elseif/else chain (collapse_else_if folds the parsed
chain into ternaries).
"""
from __future__ import annotations

from functools import reduce
from collections.abc import Sequence
from typing import Callable, Iterable, Any
from dataclasses import dataclass, field
import dataclasses
import pyast.rewrite as rw

from langtools import checked_cast
from parsing.tokenizer import LineRef
from parsing.parselib import Error

import codegen.ops as cg_o
import codegen.param as cg_p

import pyast.resolver as g
import pyast.expression as e
import pyast.typespec as t

import pyast.utils as u

from pyast.statement.base import Statement, DataStatement
from pyast.statement.lets import LetStatement
from pyast.statement.function import FunctionStatement


@dataclass
class ReturnStatement(Statement):
    value: e.Expression
    # Per-block ordinal assigned by the `block_exits` lowering pass, making this
    # return's exit-label and value-var names unique among the returns sharing
    # an enclosing block — the block-exit analogue of RecurExpression.index.
    index: int = 0

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,Any],Any]) -> Statement:
        return rw.rewrite(self, replace, resolver,
            value=self.value.search_and_replace(resolver, replace))

    def compile(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> tuple[Statement | None, list[Statement]]:
        new_value, stmts = self.value.compile(resolver, func_ret_type)
        return dataclasses.replace(self, value=new_value), stmts

    def check(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> list[Error]:
        xtype = self.value.get_type(resolver)
        if xtype is not None and t.trivially_assignable_equals(resolver, func_ret_type, xtype) is False:
            return [Error(self.line_ref, "Incorrect return type")]
        return self.value.check(resolver, func_ret_type)

    def generate(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> g.OperationBundle:
        # A `return` never emits a function `Return` — only the function's own
        # tail does that. It branches to the end of the nearest enclosing
        # BlockExpression, supplying its value as one source of that block's end
        # Phi. The value is coerced to the *block's* result type (a narrow value
        # flowing out of a union-typed block is boxed here); the (exit-label,
        # value) pair flows up to the block via exit_sources. Because the block
        # is substituted whole when a call is inlined, this makes an inlined
        # early return behave correctly with no special handling — the jump
        # targets the inlined block, not the surrounding function.
        frame = resolver.get_block_frame()
        assert frame is not None, "ReturnStatement generated outside any BlockExpression"
        # Coerce the value to the block's result type, exactly like the trailing
        # fall-through value and every other recipient (let, parameter, match arm).
        # A narrow value or a subset union flowing into a wider union is widened
        # here — `return` is not special.
        vb = self.value.generate_to(resolver, frame.result_type)
        if vb.operations and isinstance(
                vb.operations[-1],
                (cg_o.Jump, cg_o.Return, cg_o.ReturnVoid, cg_o.Abort, cg_o.SwitchJump)):
            # The value itself transferred control away (a [tail] recur, an
            # inner return): there is no fall-through to jump from, and the
            # block Phi must not receive a source for this dead edge — the
            # same bottom-handling the ternary and the block fall-through do.
            return g.OperationBundle(
                stack_vars=vb.stack_vars,
                operations=vb.operations,
                result_var=None,
                recur_sources=vb.recur_sources,
                exit_sources=vb.exit_sources)
        exit_label = f"blockexit${frame.tag}${self.index}"
        tail = (cg_o.Label(exit_label), cg_o.Jump(frame.end_label))
        if vb.result_var is None:
            # Unit / control-only block: no value to carry to the merge.
            return g.OperationBundle(
                stack_vars=vb.stack_vars,
                operations=vb.operations + tail,
                result_var=None,
                recur_sources=vb.recur_sources,
                exit_sources=vb.exit_sources + ((exit_label, None),))
        valvar = cg_p.StackVar(vb.result_var.get_type(), f"blockval${frame.tag}${self.index}")
        return g.OperationBundle(
            stack_vars=vb.stack_vars + (valvar,),
            operations=vb.operations + (cg_o.Move(valvar, vb.result_var),) + tail,
            result_var=None,
            recur_sources=vb.recur_sources,
            exit_sources=vb.exit_sources + ((exit_label, valvar),))


@dataclass
class ActionStatement(Statement):
    action: e.Expression

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,Any],Any]) -> Statement:
        return rw.rewrite(self, replace, resolver,
            action=self.action.search_and_replace(resolver, replace))

    def compile(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> tuple[Statement | None, list[Statement]]:
        new_action, stmts = self.action.compile(resolver, None)
        return dataclasses.replace(self, action = new_action), stmts

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        errors = self.action.check(resolver, None)
        # No value vanishes silently: a statement-position expression discards
        # its result. Unit (None, the empty tuple) carries nothing and is fine;
        # anything else — often an error union like `IOError|None` — warns.
        # `let _ = expr` is the explicit discard.
        xtype = self.action.get_type(resolver)
        if xtype is not None and not (isinstance(xtype, t.TupleSpec) and not xtype.entries):
            errors = errors + [Error.warning(
                self.line_ref, "statement value is discarded — bind it to '_' to discard explicitly")]
        return errors

    def generate(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> g.OperationBundle:
        return self.action.generate(resolver)


@dataclass
class IfStatement(Statement):
    """A first-class conditional statement.

    Branches are pure scopes — any `let`s inside a branch are branch-local
    and do not escape. There is no required structure (per the "only
    ambiguity is an error" principle): a branch may contain anything,
    including nothing. A branch ending in `ret` exits the function;
    otherwise control falls through to the statements after the `if`.
    """
    condition: e.Expression
    true_block: list[Statement]
    false_block: list[Statement]   # empty when there is no `else`

    def _branch_finder(self, stmts: list[Statement]) -> Callable[[str], list[g.Resolved[DataStatement]]]:
        def finder(query: str) -> list[g.Resolved[DataStatement]]:
            lets = [g.Resolved(let.name, let, g.ResolvedScope.LOCAL)
                    for x in stmts if isinstance(x, LetStatement)
                    for let in x.flatten() if g.name_matches(let.name, query)]
            funs = [g.Resolved(fun.name, fun, g.ResolvedScope.LOCAL)
                    for fun in stmts if isinstance(fun, FunctionStatement) and g.name_matches(fun.name, query)]
            return lets + funs
        return finder

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,Any],Any]) -> Statement:
        true_resolver = g.ResolverData(resolver, self._branch_finder(self.true_block))
        false_resolver = g.ResolverData(resolver, self._branch_finder(self.false_block))
        return rw.rewrite(self, replace, resolver,
            condition=self.condition.search_and_replace(resolver, replace),
            true_block=rw.seq(self.true_block, true_resolver, replace),
            false_block=rw.seq(self.false_block, false_resolver, replace))

    def compile(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> tuple[Statement | None, list[Statement]]:
        new_cond, cond_glb = self.condition.compile(resolver, t.BuiltinSpec(self.line_ref, "bool"))

        def compile_branch(stmts: list[Statement]) -> tuple[list[Statement], list[Statement]]:
            stmts = collapse_else_if(stmts)
            nested = g.ResolverData(resolver, self._branch_finder(stmts))
            results = [x.compile(nested, func_ret_type) for x in stmts]
            new_stmts = [r[0] for r in results if r[0] is not None]
            glbs = [g for r in results for g in r[1]]
            return new_stmts, glbs

        new_true, true_glb = compile_branch(self.true_block)
        new_false, false_glb = compile_branch(self.false_block)
        return dataclasses.replace(self, condition=new_cond,
                                    true_block=new_true,
                                    false_block=new_false), cond_glb + true_glb + false_glb

    def check(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> list[Error]:
        errs: list[Error] = list(self.condition.check(resolver, t.BuiltinSpec(self.line_ref, "bool")))
        cond_type = self.condition.get_type(resolver)
        if cond_type is not None and not t.trivially_assignable_equals(
                resolver, t.BuiltinSpec(self.line_ref, "bool"), cond_type):
            errs.append(Error(self.condition.line_ref, "if condition must be Bool"))
        for stmts in (self.true_block, self.false_block):
            nested = g.ResolverData(resolver, self._branch_finder(stmts))
            for x in stmts:
                errs += x.check(nested, func_ret_type)
        return errs

    def generate(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> g.OperationBundle:
        cond_bundle = self.condition.generate(resolver).with_prefix("cond")

        def gen_branch(stmts: list[Statement], prefix: str) -> g.OperationBundle:
            nested = g.ResolverData(resolver, self._branch_finder(stmts))
            bundle = g.OperationBundle()
            for i, stmt in enumerate(stmts):
                bundle = bundle + stmt.generate(nested, func_ret_type).with_prefix(f"{prefix}s{i}")
            return bundle

        true_bundle = gen_branch(self.true_block, "T")
        false_bundle = gen_branch(self.false_block, "F")

        return (
            cond_bundle
            + g.OperationBundle(operations=(
                cg_o.JumpIf("T_branch", cond_bundle.result_var),
                cg_o.Label("F_branch"),
            ))
            + false_bundle
            + g.OperationBundle(operations=(
                cg_o.Jump("if_end"),
                cg_o.Label("T_branch"),
            ))
            + true_bundle
            + g.OperationBundle(operations=(
                cg_o.Label("if_end"),
            ))
        )


@dataclass
class ElseIfStatement(Statement):
    """Parsed as a standalone statement; `collapse_else_if` folds proper
    `if`/`else if`/`else` sequences into nested `IfStatement`s. A surviving
    ElseIfStatement is an orphan (no preceding `if`) and `check()` reports it."""
    condition: e.Expression
    body: list[Statement]

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,Any],Any]) -> Statement:
        return rw.rewrite(self, replace, resolver,
            condition=self.condition.search_and_replace(resolver, replace),
            body=rw.seq(self.body, resolver, replace))

    def compile(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> tuple[Statement | None, list[Statement]]:
        return self, []

    def check(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> list[Error]:
        return [Error(self.line_ref, "`else if` without a matching preceding `if`")]

    def generate(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> g.OperationBundle:
        raise AssertionError("ElseIfStatement reached generate(); check() should have rejected it")


@dataclass
class ElseStatement(Statement):
    """See ElseIfStatement — same orphan-or-folded story."""
    body: list[Statement]

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,Any],Any]) -> Statement:
        return rw.rewrite(self, replace, resolver,
            body=rw.seq(self.body, resolver, replace))

    def compile(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> tuple[Statement | None, list[Statement]]:
        return self, []

    def check(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> list[Error]:
        return [Error(self.line_ref, "`else` without a matching preceding `if`")]

    def generate(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> g.OperationBundle:
        raise AssertionError("ElseStatement reached generate(); check() should have rejected it")


def collapse_else_if(stmts: list[Statement]) -> list[Statement]:
    """Fold `IfStatement` followed by zero or more `ElseIfStatement`s and
    at most one `ElseStatement` into a single right-nested `IfStatement`.
    Orphan `ElseIfStatement`/`ElseStatement` are passed through unchanged;
    their `check()` will report the error.

    Idempotent: if an `IfStatement` has no following `else if`/`else` it
    is passed through unchanged, preserving any `false_block` populated by
    a previous pass."""
    result: list[Statement] = []
    i = 0
    while i < len(stmts):
        stmt = stmts[i]
        if not isinstance(stmt, IfStatement):
            result.append(stmt)
            i += 1
            continue
        chain: list[tuple[e.Expression, list[Statement], LineRef]] = []
        else_body: list[Statement] | None = None
        i += 1
        while i < len(stmts):
            nxt = stmts[i]
            if isinstance(nxt, ElseIfStatement):
                chain.append((nxt.condition, nxt.body, nxt.line_ref))
                i += 1
            elif isinstance(nxt, ElseStatement):
                else_body = nxt.body
                i += 1
                break
            else:
                break
        if not chain and else_body is None:
            result.append(stmt)
            continue
        tail: list[Statement] = else_body if else_body is not None else []
        for cond, body, lr in reversed(chain):
            tail = [IfStatement(lr, cond, body, tail)]
        result.append(dataclasses.replace(stmt, false_block=tail))
    return result
