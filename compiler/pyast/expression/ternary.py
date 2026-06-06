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


@dataclass
class TernaryExpression(Expression):
    condition: Expression
    trueResult: Expression
    falseResult: Expression

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,Any],Any]) -> Expression:
        return cast(Expression, replace(resolver, dataclasses.replace(self,
            condition=self.condition.search_and_replace(resolver, replace),
            trueResult=self.trueResult.search_and_replace(resolver, replace),
            falseResult=self.falseResult.search_and_replace(resolver, replace))))

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        trueType = self.trueResult.get_type(resolver)
        falseType = self.falseResult.get_type(resolver)
        if not trueType: return falseType
        if not falseType: return trueType
        return falseType if falseType.trivially_assignable_from(resolver, trueType) else trueType

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement]]:
        condition, conditionStatements = self.condition.compile(resolver, t.Bool())
        trueResult, trueStatements = self.trueResult.compile(resolver, self.falseResult.get_type(resolver))
        falseResult, falseStatements = self.falseResult.compile(resolver, self.trueResult.get_type(resolver))
        return (dataclasses.replace(self, condition=condition, trueResult=trueResult, falseResult=falseResult),
                conditionStatements + trueStatements + falseStatements)

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        cond_err = self.condition.check(resolver, t.Bool())
        true_err = self.trueResult.check(resolver, expected_type)
        false_err = self.falseResult.check(resolver, expected_type)
        self_err = [] if self.get_type(resolver) else [Error(self.line_ref, "Failed to resolve type of ternery expression")]
        return cond_err + true_err + false_err + self_err

    def generate_to(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> g.OperationBundle:
        # The branches share one result slot, so coercion to the union happens
        # *inside* generate (each branch is widened to the slot type before the
        # Phi); there is nothing left to coerce afterwards.
        return self.generate(resolver, expected_type)

    def generate(self, resolver: g.Resolver, expected_type: t.TypeSpec | None = None) -> g.OperationBundle:
        # SSA shape: each branch's result has its own path-derived name
        # (F/... and T/...). A Phi at the `join` label collects them.
        #
        # `F_exit` and `T_exit` are explicit labels placed immediately before
        # each branch leaves to the join. They name the *actual* predecessor
        # block at Phi-lowering time, which matters when a branch contains
        # its own nested control flow (e.g. a nested ternary's `join` label
        # is the "most recent label" right before this outer ternary's exit).
        # Without these explicit labels, the Phi would name the start of the
        # branch (`F_branch` / `T_branch`), but control may have passed
        # through additional intermediate labels first.
        #
        # `slot_type` is the shared result type. When a sink supplies it (a union
        # the branches widen into) we use it; otherwise both branches already
        # agree and `get_type` is exact. Each branch is generated *to* that type
        # so a narrow branch is boxed before reaching the Phi.
        slot_type = expected_type if expected_type is not None else self.get_type(resolver)
        cond_bundle = self.condition.generate(resolver).with_prefix("cond")
        false_bundle = self.falseResult.generate_to(resolver, slot_type).with_prefix("F")
        true_bundle  = self.trueResult.generate_to(resolver, slot_type).with_prefix("T")

        # A *bottom* branch transfers control elsewhere and never reaches the
        # join (e.g. a [tail] `recur`, which jumps to the loop head). It's
        # detected by ending in an unconditional control-transfer op — NOT by a
        # None result_var, which a unit-valued branch also has. A bottom branch
        # contributes no Phi source; the ternary's value is the other branch's.
        def _bottom(b: g.OperationBundle) -> bool:
            return bool(b.operations) and isinstance(
                b.operations[-1],
                (cg_o.Jump, cg_o.Return, cg_o.ReturnVoid, cg_o.Abort, cg_o.SwitchJump))
        f_bottom = _bottom(false_bundle)
        t_bottom = _bottom(true_bundle)
        if f_bottom or t_bottom:
            head = cond_bundle + g.OperationBundle(operations=(
                cg_o.JumpIf("T_branch", cond_bundle.result_var),
                cg_o.Label("F_branch"),
            ))
            if f_bottom and t_bottom:
                # Both branches leave; the whole ternary is bottom.
                return (head + false_bundle
                        + g.OperationBundle(operations=(cg_o.Label("T_branch"),)) + true_bundle)
            if f_bottom:
                # False leaves; control reaches here only via the true branch.
                return (head + false_bundle
                        + g.OperationBundle(operations=(cg_o.Label("T_branch"),))
                        + true_bundle)
            # true is bottom: false falls through and must hop over the true block.
            return (head + false_bundle
                    + g.OperationBundle(operations=(cg_o.Jump("join"), cg_o.Label("T_branch")))
                    + true_bundle
                    + g.OperationBundle(operations=(cg_o.Label("join"),), result_var=false_bundle.result_var))

        result_var = cg_p.StackVar(slot_type.generate(resolver), "result")
        phi = cg_o.Phi(
            target=result_var,
            sources=(
                ("F_exit", false_bundle.result_var),
                ("T_exit", true_bundle.result_var),
            ))

        return (
            cond_bundle
            + g.OperationBundle(operations=(
                cg_o.JumpIf("T_branch", cond_bundle.result_var),
                cg_o.Label("F_branch"),
            ))
            + false_bundle
            + g.OperationBundle(operations=(
                cg_o.Label("F_exit"),
                cg_o.Jump("join"),
                cg_o.Label("T_branch"),
            ))
            + true_bundle
            + g.OperationBundle(
                stack_vars=(result_var,),
                operations=(
                    cg_o.Label("T_exit"),
                    cg_o.Label("join"),
                    phi,
                ),
                result_var=result_var)
        )




