"""`let` and destructuring bindings — including the untyped-let type refinement
(t.refine) and the constructor-parameter flattening the other kinds build on.
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
import codegen.typedecl as cg_t
import codegen.ir as cg_ir

import pyast.resolver as g
import pyast.expression as e
import pyast.typespec as t

import pyast.utils as u

from pyast.statement.base import Statement, NamedStatement, DataStatement, ImportGroup


@dataclass
class LetStatement(DataStatement):
    default_value: e.Expression|None
    declared_type: t.TypeSpec|None
    # True once inference has FILLED an untyped let's type. A declared type is
    # fixed (its holes fill by refinement); an inferred one converges on the RHS
    # and must be free to WIDEN as a match/branch RHS broadens — the same
    # distinction FunctionStatement draws for its return. Provenance, not
    # identity: excluded from equality/hash.
    type_inferred: bool = field(default=False, compare=False, kw_only=True)

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,Any],Any]) -> Statement:
        return rw.rewrite(self, replace, resolver,
            default_value=rw.opt(self.default_value, resolver, replace),
            declared_type=rw.opt(self.declared_type, resolver, replace))

    def get_type(self) -> t.TypeSpec|None:
        return self.declared_type

    def is_deferred_init(self) -> bool:
        """True if this let is initialised lazily — its RHS is wrapped in
        a closure and evaluation is deferred until first force.  Today
        that means `[lazy]`; future deferred-eval attributes route through
        the same predicate so callers don't need to enumerate them.

        Used to keep multiple compiler stages in lock-step:
        `ast_inline` skips statement-level inlining; `lower_lazy_lets`
        wraps the RHS in a `()=>expr` lambda; `NamedExpression.generate`
        returns DataPointer-typed storage (the stub pointer);
        `BlockExpression.generate` hoists stub allocation to block entry.
        Any new pass that special-cases lazy lets should consult this
        predicate rather than spelling out `"lazy" in attributes`.
        """
        return "lazy" in self.attributes

    def add_namespace(self, path: str):
        return self if self.name == '_' else super().add_namespace(path)

    def to_c_destructure(self, root: cg_p.RParam | None, resolver: g.Resolver = None) -> g.OperationBundle:
        if root:
            # Leaf node, move the value into a stack var
            var = cg_p.StackVar(self.get_type().generate(resolver), self.name)
            return g.OperationBundle(
                stack_vars=(var,),
                operations=(cg_o.Move(var, root),),
                result_var=None)
        else:
            # Just a value, no work, caller does it
            return g.OperationBundle()

    def compile(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> tuple[LetStatement | None, list[Statement]]:
        # A generic trait-instance let (`let [trait] _x<S,T>: … where Box<S,T>`)
        # carries a `where` clause that must be compiled. The generic scope
        # itself (S/T) is supplied by the caller via _initialiser_resolver
        # (see compiler.__stmt_scope_resolver), so do NOT re-wrap here — that
        # would shadow each placeholder and make references ambiguous.
        trts, trts_glb = u.flatten_lists(tp.compile(resolver) for tp in self.trait_params)
        dv, dv_glb = self.default_value.compile(resolver, self.declared_type) if self.default_value else (None, [])
        dt, dt_glb = self.declared_type.compile(resolver) if self.declared_type else (None, [])
        # A DECLARED type is fixed (refine only fills its holes); an UNTYPED let
        # converges on the RHS and must be free to widen as a match/branch RHS
        # broadens (`A`, then `A|None`) — the shared receiver-convergence step,
        # gated on the RHS still changing this pass.
        declared = self.declared_type is not None and not self.type_inferred
        new_type_inferred = self.type_inferred
        if dv is not None:
            if declared:
                dt = t.refine(dt, resolver, lambda: dv.get_type(resolver))
            else:
                new_type_inferred = True
                dt = t.refine_widening(dt, resolver, lambda: dv.get_type(resolver),
                                       dv != self.default_value)
        stmt = dataclasses.replace(self, default_value=dv, declared_type=dt, trait_params=tuple(trts),
                                   type_inferred=new_type_inferred)
        return stmt, dv_glb+dt_glb+trts_glb

    def check(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> list[Error]:
        # Generic scope (S/T) is supplied by _initialiser_resolver, as in compile.
        if self.default_value and self.declared_type:
            xtype = self.default_value.get_type(resolver)
            if xtype is not None and t.trivially_assignable_equals(resolver, self.declared_type, xtype) is False:
                return [Error(self.line_ref, "Incorrect type")]
        err1 = self.default_value.check(resolver, self.declared_type) if self.default_value else []
        err2 = self.declared_type.check(resolver) if self.declared_type else []
        const_err: list[Error] = []
        if "const" in self.attributes:
            if self.attributes.get("const") is not None:
                const_err.append(Error(self.line_ref, "[const] takes no arguments"))
            if not isinstance(self.default_value, (e.IntegerExpression, e.FloatExpression, e.StringExpression, e.BoolExpression)):
                const_err.append(Error(self.line_ref, "[const] requires a literal value"))
        lazy_err: list[Error] = []
        if "lazy" in self.attributes:
            if self.attributes.get("lazy") is not None:
                lazy_err.append(Error(self.line_ref, "[lazy] takes no arguments"))
            if self.default_value is None:
                lazy_err.append(Error(self.line_ref, "[lazy] requires an initialiser"))
        where_err = [e for x in self.trait_params for e in x.check(resolver)]
        return err1 + err2 + const_err + lazy_err + where_err

    def generate(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> g.OperationBundle:
        # `[lazy]` lets are handled out-of-band by `BlockExpression.generate`:
        # it hoists `generate_lazy_alloc` to block entry and emits
        # `generate_lazy_populate` at the let's textual position.  Any
        # other call site is a bug — silently emitting only the
        # closure-population half would leave the stub unallocated and
        # crash at force.  Surface the bug instead of papering over it.
        if self.is_deferred_init():
            raise RuntimeError(
                f"[lazy] let {self.name!r} reached LetStatement.generate "
                f"directly — this should only happen via "
                f"BlockExpression.generate's two-phase emission. "
                f"A new generate-site that holds nested LetStatements "
                f"needs the same hoist treatment.")
        expr_bundle = self.default_value.generate_to(resolver, self.declared_type).with_prefix("expr")
        sv = cg_p.StackVar(self.declared_type.generate(resolver), self.name)
        init_bundle = g.OperationBundle(
            stack_vars=(sv,),
            operations=(cg_o.Move(sv, expr_bundle.result_var),),
            result_var=None
        )
        unpack_bundle = self.to_c_destructure(None).with_prefix("unpack")
        return expr_bundle + init_bundle + unpack_bundle

    def generate_lazy_alloc(self, resolver: g.Resolver) -> g.OperationBundle:
        """Stub allocation half of a `[lazy]` local let — emit at block
        entry so forward references inside other lazies see the stub
        slot pointing at a real heap object.

        Allocates the `Lazy$<irmangle>` stub, clears `flag` and `closure`
        to zero.  Closure population happens later via `generate_lazy_populate`
        at the let's original textual position.
        """
        import lowering.lazy_thunks as lt

        ir_t = self.declared_type.generate(resolver)
        lt._ir_mangle(ir_t)
        cls = lt.stub_class_name(ir_t)

        sv_stub   = cg_p.StackVar(cg_t.DataPointer(), self.name)
        flag_f    = cg_p.ObjectField(cg_t.DataPointer(), sv_stub, cls, "flag",    None)
        closure_f = cg_p.ObjectField(cg_t.FuncPointer(), sv_stub, cls, "closure", None)
        return g.OperationBundle(
            stack_vars=(sv_stub,),
            operations=(
                cg_o.NewObject(cls, sv_stub),
                cg_o.Move(flag_f,    cg_p.NullPointer()),
                cg_o.Move(closure_f, cg_p.ZeroOf(cg_t.FuncPointer())),
            ),
            result_var=None,
        )

    def generate_lazy_populate(self, resolver: g.Resolver) -> g.OperationBundle:
        """Closure-population half of a `[lazy]` local let — emit at the
        let's original textual position.

        Pre-condition: `lower_lazy_lets` has wrapped the RHS in a
        `() => expr` LambdaExpression, the lambdas pass has converted it
        to a fun_t-valued expression (`DotExpression(NewExpression(...))`
        for capturing closures, `NamedExpression` for captureless ones),
        and `generate_lazy_alloc` has already emitted the stub allocation
        at block entry — so the stub stack var is bound and the slot
        points at a real heap object by the time we get here.
        """
        import lowering.lazy_thunks as lt

        ir_t = self.declared_type.generate(resolver)
        cls  = lt.stub_class_name(ir_t)

        closure_bundle = self.default_value.generate(resolver).with_prefix("closure")
        sv_stub   = cg_p.StackVar(cg_t.DataPointer(), self.name)
        closure_f = cg_p.ObjectField(cg_t.FuncPointer(), sv_stub, cls, "closure", None)
        return closure_bundle + g.OperationBundle(
            stack_vars=(),
            operations=(cg_o.Move(closure_f, closure_bundle.result_var),),
            result_var=None,
        )

    def global_codegen(self, resolver: g.Resolver) -> tuple[list[cg_ir.Global], list[cg_ir.Function]]:
        if self.is_deferred_init():
            return self.__global_codegen_lazy(resolver)

        # Non-`[lazy]` globals reach here only when `lower_lazy_lets` did
        # *not* auto-promote them — meaning `_is_trivial_expr` accepted
        # the AST shape.  Three direct-emission paths:
        #
        #   1. literal scalar / string → single-RParam Global.
        #   2. `ClassName(literal, …)` → static class-instance Global
        #      whose `init` is a NewStruct of the literal args.
        #   3. tuple of literals → flat-struct Global.
        #
        # None of these go through `$lazy$init`.
        if self.default_value is not None:
            static = self.__try_static_class_init(resolver)
            if static is not None:
                return [static], []

        xtype = self.get_type().generate(resolver)
        rparam: cg_p.RParam | None = None
        if self.default_value is not None:
            init = self.default_value.generate_to(resolver, self.declared_type)
            if init.operations or init.stack_vars or init.result_var is None:
                raise RuntimeError(
                    f"non-lazy global {self.name!r} produced a non-trivial "
                    f"init bundle — lower_lazy_lets should have auto-promoted "
                    f"it to [lazy].")
            rparam = init.result_var
        return [cg_ir.Global(self.name, xtype, rparam)], []

    def __try_static_class_init(self, resolver: g.Resolver) -> cg_ir.Global | None:
        """Match `let x: T = ClassName(literal, …)` and emit `x` directly
        as a static class-instance Global with `object_name=ClassName`
        and `init=NewStruct((field, literal_rparam), …)`.

        Returns the Global on a successful match, or None to fall back
        to the generic generate() path.  The match is the AST counterpart
        of the legacy staticinit + resolve_flat_struct_global_inits
        optimisations — performed upfront so we never spin up the lazy
        framework for a global the compiler can statically initialise.
        """
        # Deferred: lets ← classdef would be an import cycle (a class's fields
        # are LetStatements); this only runs long after both initialise.
        from pyast.statement.classdef import ClassStatement

        dv = self.default_value
        if not isinstance(dv, e.CallExpression):
            return None
        if not isinstance(dv.function, e.NamedExpression):
            return None
        if not isinstance(dv.parameter, e.TupleExpression):
            return None
        found = resolver.find_type(dv.function.name)
        if len(found) != 1 or not isinstance(found[0].statement, ClassStatement):
            return None
        cls = found[0].statement
        field_defs = list(cls.parameters.flatten())
        args = dv.parameter.expressions
        if len(args) != len(field_defs):
            return None

        init_pairs: list[tuple[str, cg_p.RParam]] = []
        for arg_entry, field_def in zip(args, field_defs):
            # Any arg whose generate() produces a single RParam with no
            # operations / stack vars is acceptable as a static
            # initialiser — covers literals AND tuples of literals
            # (whose generate() produces a NewStruct of literal RParams).
            ab = arg_entry.value.generate_to(resolver, field_def.declared_type)
            if ab.operations or ab.stack_vars or ab.result_var is None:
                return None
            init_pairs.append((field_def.name, ab.result_var))

        return cg_ir.Global(
            name=self.name,
            type=cg_t.DataPointer(),
            init=cg_p.NewStruct(tuple(init_pairs)),
            object_name=cls.name,
        )

    def __global_codegen_lazy(self, resolver: g.Resolver) -> tuple[list[cg_ir.Global], list[cg_ir.Function]]:
        """`[lazy]` global lowering — emit a static `Lazy$<irmangle>`
        instance whose `closure` points at the lifted init function.

        Pre-condition: `lower_lazy_lets` has wrapped the RHS in a
        `() => expr` LambdaExpression, and the lambdas pass has converted
        it to a fun_t-valued NamedExpression of the lifted captureless
        function (globals can't reference function-locals, so the
        closure is always captureless).
        """
        import lowering.lazy_thunks as lt

        if self.default_value is None:
            raise ValueError(f"[lazy] global {self.name!r} requires an initialiser")

        xtype = self.get_type().generate(resolver)
        lt._ir_mangle(xtype)  # raise NotImplementedError early for unsupported types
        stub_cls = lt.stub_class_name(xtype)

        init = self.default_value.generate(resolver)
        if init.operations or init.stack_vars:
            raise ValueError(
                f"[lazy] global {self.name!r}: closure expression must reduce "
                f"to a single fun_t value — lambdas pass should have lifted "
                f"the captureless lambda.  Got default_value={type(self.default_value).__name__!r}, "
                f"ops={len(init.operations)}, stack_vars={len(init.stack_vars)}")
        closure_value = init.result_var
        assert closure_value is not None

        stub_init = cg_p.NewStruct((
            ("flag",    cg_p.NullPointer()),
            ("closure", closure_value),
            ("value",   cg_p.ZeroOf(xtype)),
        ))
        return [cg_ir.Global(
            name=self.name,
            type=cg_t.DataPointer(),
            init=stub_init,
            object_name=stub_cls,
        )], []

    def map_leaf_paths(self, make_leaf, path):
        return [make_leaf(path + [self])]

    def flatten(self) -> list[LetStatement]:
        return self.map_leaf_paths(lambda path: path[-1], [])


@dataclass
class DestructureStatement(LetStatement):
    targets: list[LetStatement]

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,Any],Any]) -> Statement:
        return rw.rewrite(self, replace, resolver,
            default_value=rw.opt(self.default_value, resolver, replace),
            declared_type=rw.opt(self.declared_type, resolver, replace),
            targets=rw.seq(self.targets, resolver, replace))

    def get_type(self) -> t.TupleSpec:
        return t.TupleSpec(self.line_ref, [t.TupleEntrySpec(x.name, x.get_type(), None) for x in self.targets])

    def to_c_destructure(self, root: cg_p.RParam | None, resolver: g.Resolver = None) -> g.OperationBundle:
        if not root:
            # The first attempt should declare the root var
            root = cg_p.StackVar(self.get_type().generate(resolver), self.name)
        bundles = [
            target.to_c_destructure(cg_p.StructField(root, f"_{index}"), resolver).with_prefix(f"f{index}")
            for index, target in enumerate(self.targets)
        ]
        return reduce(lambda a, b: a + b, bundles) if bundles else g.OperationBundle()

    def generate(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> g.OperationBundle:
        # The slot is the TARGETS' tuple type, not the RHS's own: an annotated
        # target may be WIDER than its entry — `(s: String|None, n) = (None, 7)`,
        # the shape a `|>`-lambda beta-block binds. The widening itself is an
        # explicit ConvertExpression inserted by lowering/boxing.py (generate never
        # coerces); this only sizes the slot to match.
        slot_type: t.TypeSpec | None = self.get_type()
        if any(entry.type is None for entry in slot_type.entries):
            slot_type = self.declared_type
        expr_bundle = self.default_value.generate_to(resolver, slot_type).with_prefix("expr")
        sv = cg_p.StackVar(slot_type.generate(resolver), self.name)
        init_bundle = g.OperationBundle(
            stack_vars=(sv,),
            operations=(cg_o.Move(sv, expr_bundle.result_var),),
            result_var=None
        )
        # `sv` is at the un-prefixed root of init_bundle; pass it directly as
        # the destructure root rather than predicting a renamed name.
        unpack_bundle = self.to_c_destructure(sv, resolver).with_prefix("unpack")
        return expr_bundle + init_bundle + unpack_bundle

    def add_namespace(self, path: str):
        x: DestructureStatement = checked_cast(DestructureStatement, super().add_namespace(path))
        return dataclasses.replace(x, targets=[l.add_namespace(path) for l in self.targets])

    def compile(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> tuple[DestructureStatement, list[Statement]]:
        stmt, stmt_glb = super().compile(resolver, func_ret_type)
        # Propagate the parent tuple's entry types onto the targets. A target
        # with no type adopts the entry's (which may itself still be a generic
        # placeholder, needed inside a generic body); a target whose type still
        # carries a HOLE — a bare unbound placeholder, or a compound with a free
        # placeholder inside (`E|IOError|None` before `E` discharges) — keeps
        # refining via t.refine, the single gate/threshold/merge rule. A target
        # with its own resolved (or merely still-unresolved NamedSpec) annotation
        # keeps it: refine never overwrites a declaration.
        parent_type = stmt.declared_type
        targets = stmt.targets
        if isinstance(parent_type, t.TupleSpec) and len(parent_type.entries) == len(targets):
            def _refine(tgt, entry):
                if entry.type is None:
                    return tgt
                if tgt.declared_type is None:
                    return dataclasses.replace(tgt, declared_type=entry.type)
                new_dt = t.refine(tgt.declared_type, resolver, lambda: entry.type)
                if new_dt is not tgt.declared_type:
                    return dataclasses.replace(tgt, declared_type=new_dt)
                return tgt
            targets = [_refine(tgt, entry) for tgt, entry in zip(targets, parent_type.entries)]
            stmt = dataclasses.replace(stmt, targets=targets)
        results = [x.compile(resolver, None) for x in stmt.targets]
        tgts = [x[0] for x in results]
        tgts_glb = [g for x in results for g in x[1]]
        stmt = dataclasses.replace(stmt, targets=tgts)
        return checked_cast(DestructureStatement, stmt), stmt_glb+tgts_glb

    def map_leaf_paths(self, make_leaf, path):
        return [make_leaf(path + [entry]) for target in self.targets for entry in target.flatten()]
