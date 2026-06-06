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
    """Immutable generation-time context for one [tail] loop: a unique '@'-bearing
    `tag` that seeds this loop's labels (so a deeply-nested recur's back-edge jump
    stays string-matched to the head label through `with_prefix`), the parameters'
    *generated* IR types (taken from live param references so the loop vars match
    the body's references exactly), and the parameters' TypeSpecs (so a recur
    back-edge can coerce each argument to its parameter type). Read-only — carried
    *down* to nested RecurExpressions via the resolver (g.ResolverLoop). The
    back-edge phi sources flow the other way, *up* through
    OperationBundle.recur_sources, so no mutable state crosses calls."""
    tag: str
    param_ctypes: tuple
    param_specs: tuple

    @property
    def head(self) -> str:
        return f"loophead${self.tag}"   # tag carries '@' → with_prefix spares it



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
            # Coerce each argument to its parameter type — the self-call's
            # union-widening, which the boxing pass used to do before tail
            # lowering turned the call into this recur.
            ab = a.generate_to(resolver, frame.param_specs[i]).with_prefix(f"recur{i}")
            phiin = cg_p.StackVar(frame.param_ctypes[i],
                                  f"phiin${frame.tag}${k}${i}")
            phi_inputs.append(phiin)
            bundle = bundle + ab + g.OperationBundle(
                stack_vars=(phiin,), operations=(cg_o.Move(phiin, ab.result_var),))
        exit_label = f"recurexit{k}${frame.tag}"
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
    edge supplies the incoming param, each `recur` supplies its args. The
    loop-carried parameters are held as `NamedExpression` *references*, so the
    ordinary renaming passes (inliner alpha-renaming, closure conversion, generic
    specialisation) rewrite them along with the body's uses — no special handling.

    The loop's labels are seeded from a `tag` derived from the parameter names
    (see `generate`): the parameters are already unique per loop and per inline
    copy and carry '@', so the tag inherits both — '@' makes `with_prefix` leave
    the labels un-prefixed, so a deeply-nested `recur`'s back-edge jump stays
    string-matched to the head label when codegen pairs jumps to labels, and the
    per-copy uniqueness keeps two inlined loops from cross-pairing. Loop vars are
    ordinary single-def SSA vars (not `$sv_` scratch), so async lowering's
    liveness promotion moves them into the task-heap state across suspensions
    automatically. The param→loop-var rename is applied here at generate time, so
    the body AST still refers to the parameters normally."""
    body: Expression
    params: tuple[NamedExpression, ...]

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver, Any], Any]) -> Expression:
        return cast(Expression, replace(resolver, dataclasses.replace(self,
            body=self.body.search_and_replace(resolver, replace),
            params=tuple(cast(NamedExpression, p.search_and_replace(resolver, replace))
                         for p in self.params))))

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        return self.body.get_type(resolver)

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement]]:
        return self, []

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        return self.body.check(resolver, expected_type)

    def generate_to(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> g.OperationBundle:
        # The body's non-recursive exits are coerced to the function's return
        # type *inside* generate (the boxing pass used to widen them before tail
        # lowering wrapped the body in this loop); nothing remains to coerce.
        return self.generate(resolver, expected_type)

    def generate(self, resolver: g.Resolver, expected_type: t.TypeSpec | None = None) -> g.OperationBundle:
        # Resolve each parameter to its *live* StackVar — the actual current IR
        # type (post-boxing), identical to what the body's references use. This
        # is the single source of truth for the loop var, its Phi, and the
        # renamed body references; deriving it from a stored TypeSpec captured
        # before the boxing pass is what produced the earlier type mismatch.
        param_refs = [p.generate(resolver).result_var for p in self.params]
        param_ctypes = tuple(pv.get_type() for pv in param_refs)
        # The parameters' TypeSpecs, so a recur can coerce its args to them.
        param_specs = tuple(p.get_type(resolver) for p in self.params)

        # A unique '@'-bearing tag seeds this loop's labels. The parameters are
        # already unique per loop and per inline copy and carry '@', so the first
        # one serves directly; a (rare) parameterless loop falls back to a
        # position-derived tag.
        tag = self.params[0].name if self.params else f"loop@{self.line_ref.hash6()}"

        # Carry the (immutable) frame down to nested recurs via the resolver.
        # Thread the expected (function return) type into the body so its
        # non-recursive exits are widened to the return type at their merges.
        frame = _LoopFrame(tag, param_ctypes, param_specs)
        body_bundle = self.body.generate_to(g.ResolverLoop(resolver, frame), expected_type)

        # Body refers to params by name; rename those references to the loop
        # vars (the Phi outputs). Param names carry '@' and are loop-unique, so
        # the loop-var names inherit both and this single rename catches every
        # occurrence without ever being prefixed.
        lv = {p.name: f"loopvar${p.name}" for p in self.params}
        body_renamed = g.OperationBundle(
            stack_vars=tuple(sv.rename_vars(lv) for sv in body_bundle.stack_vars),
            operations=tuple(op.rename_vars(lv) for op in body_bundle.operations),
            result_var=body_bundle.result_var.rename_vars(lv) if body_bundle.result_var else None)

        entry = f"loopentry${tag}"
        lv_stackvars: list[cg_p.StackVar] = []
        phis: list[cg_o.Op] = []
        for i, p in enumerate(self.params):
            lvsv = cg_p.StackVar(param_ctypes[i], lv[p.name])
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



