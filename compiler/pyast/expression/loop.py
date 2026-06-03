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
from pyast.expression.access import NamedExpression


@dataclass(frozen=True)
class _LoopFrame:
    """Immutable generation-time context for one [tail] loop: the loop-head
    label and the parameters' *generated* IR types (post-boxing, taken from live
    param references so the loop vars match the body's references exactly).
    Read-only — carried *down* to nested RecurExpressions via the resolver
    (g.ResolverLoop). The back-edge phi sources flow the other way, *up* through
    OperationBundle.recur_sources, so no mutable state crosses calls."""
    funcname: str
    param_ctypes: tuple

    @property
    def head(self) -> str:
        return f"loophead${self.funcname}"   # funcname carries '@' → with_prefix spares it



@dataclass
class RecurExpression(Expression):
    """A `[tail]`-loop back-edge: re-bind the loop variables (the enclosing
    function's parameters) to `args` and jump to the loop head. Bottom-typed —
    it transfers control and never produces a value, so it contributes no Phi
    source and is legal only in tail position of a `LoopExpression`. `index` is a
    per-function ordinal assigned at lowering, making this recur's phi-input and
    exit-label names unique without a generation-time counter. Introduced by the
    `tail_loop` lowering pass; never written in source."""
    args: tuple[Expression, ...]
    index: int

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver, Any], Any]) -> Expression:
        return cast(Expression, replace(resolver, dataclasses.replace(self,
            args=tuple(a.search_and_replace(resolver, replace) for a in self.args))))

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        return None  # bottom

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement]]:
        return self, []

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        return [err for a in self.args for err in a.check(resolver, None)]

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        frame = resolver.get_loop_frame()
        assert frame is not None, "RecurExpression generated outside its LoopExpression"
        assert len(self.args) == len(frame.param_ctypes), (
            f"recur arity {len(self.args)} != loop parameter count {len(frame.param_ctypes)}")
        k = self.index
        # Evaluate each arg (reading current loop values), then move it into a
        # single-def, '@'-named phi-input var. The '@' makes with_prefix leave
        # the name alone, so the head Phi (built by LoopExpression) can refer to
        # it even though enclosing control flow prefixes the rest of this block.
        bundle = g.OperationBundle()
        phi_inputs: list[cg_p.RParam] = []
        for i, a in enumerate(self.args):
            ab = a.generate(resolver).with_prefix(f"recur{i}")
            phiin = cg_p.StackVar(frame.param_ctypes[i],
                                  f"phiin${frame.funcname}${k}${i}")
            phi_inputs.append(phiin)
            bundle = bundle + ab + g.OperationBundle(
                stack_vars=(phiin,), operations=(cg_o.Move(phiin, ab.result_var),))
        exit_label = f"recurexit{k}${frame.funcname}"
        # Hand this back-edge up to the enclosing LoopExpression via the bundle
        # (immutable) rather than mutating shared state.
        return g.OperationBundle(
            stack_vars=bundle.stack_vars,
            operations=bundle.operations + (cg_o.Label(exit_label), cg_o.Jump(frame.head)),
            result_var=None,
            recur_sources=bundle.recur_sources + ((exit_label, tuple(phi_inputs)),))



@dataclass
class LoopExpression(Expression):
    """Wraps a `[tail]` function body as an SSA loop. Each parameter becomes a
    loop-carried var defined once by a back-edge `Phi` at the head: the entry
    edge supplies the incoming param, each `recur` supplies its args. Loop-var
    and label names embed the (mangled, '@'-bearing) function name so
    `with_prefix` leaves them un-prefixed — keeping them consistent across
    nested control flow — and, being ordinary single-def SSA vars (not `$sv_`
    scratch), async lowering's liveness promotion moves them into the task-heap
    state across suspensions automatically. The param→loop-var rename is applied
    here at generate time, so the body AST still refers to the parameters by
    their normal names (type/scope checking sees an ordinary body)."""
    body: Expression
    param_names: tuple[str, ...]
    funcname: str

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver, Any], Any]) -> Expression:
        return cast(Expression, replace(resolver, dataclasses.replace(self,
            body=self.body.search_and_replace(resolver, replace))))

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        return self.body.get_type(resolver)

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement]]:
        return self, []

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        return self.body.check(resolver, expected_type)

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        # Resolve each parameter to its *live* StackVar — the actual current IR
        # type (post-boxing), identical to what the body's references use. This
        # is the single source of truth for the loop var, its Phi, and the
        # renamed body references; deriving it from a stored TypeSpec captured
        # before the boxing pass is what produced the earlier type mismatch.
        param_refs = [NamedExpression(self.line_ref, p).generate(resolver).result_var
                      for p in self.param_names]
        param_ctypes = tuple(pv.get_type() for pv in param_refs)

        # Carry the (immutable) frame down to nested recurs via the resolver.
        frame = _LoopFrame(self.funcname, param_ctypes)
        body_bundle = self.body.generate(g.ResolverLoop(resolver, frame))

        # Body refers to params by name; rename those references to the loop
        # vars (the Phi outputs). Param/loop-var names carry '@', so they were
        # never prefixed and this single rename catches every occurrence.
        lv = {p: f"loopvar${self.funcname}${p}" for p in self.param_names}
        body_renamed = g.OperationBundle(
            stack_vars=tuple(sv.rename_vars(lv) for sv in body_bundle.stack_vars),
            operations=tuple(op.rename_vars(lv) for op in body_bundle.operations),
            result_var=body_bundle.result_var.rename_vars(lv) if body_bundle.result_var else None)

        entry = f"loopentry${self.funcname}"
        lv_stackvars: list[cg_p.StackVar] = []
        phis: list[cg_o.Op] = []
        for i, p in enumerate(self.param_names):
            lvsv = cg_p.StackVar(param_ctypes[i], lv[p])
            lv_stackvars.append(lvsv)
            sources = [(entry, param_refs[i])]  # entry edge: the live incoming param
            for rec_exit, argvals in body_bundle.recur_sources:  # back-edges, flowed up
                sources.append((rec_exit, argvals[i]))
            phis.append(cg_o.Phi(target=lvsv, sources=tuple(sources)))

        # Entry edge is a *fall-through* from `loopentry` into `loophead`, not a
        # `Jump` — a jump to the immediately-following label is redundant and
        # gets collapsed by control-flow simplification, which would delete the
        # `loophead` label the back-edge recurs jump to. `loophead` therefore has
        # predecessors {loopentry (fall-through), recurexit… (back-edges)}.
        ops = ((cg_o.Label(entry), cg_o.Label(frame.head))
               + tuple(phis) + body_renamed.operations)
        return g.OperationBundle(
            stack_vars=tuple(lv_stackvars) + body_renamed.stack_vars,
            operations=ops,
            result_var=body_renamed.result_var)



