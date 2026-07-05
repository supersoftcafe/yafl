"""The conversion node and its engine: every representation change, in one place.

Generate never converts on its own authority — the converged AST is the
absolute source of truth for program correctness (docs/compiler-internals.md
§2), so every semantically required representation change exists in the tree
as an explicit `ConvertExpression`, inserted by `lowering/boxing.py` (via
`converted(...)`) at the sink that needs it. This module holds the whole
story:

  ConvertExpression            the node — represent `inner`'s value as `target`
  converted(expr, expected)    compile-side insertion (identity when no change
                               is needed or types aren't ground yet)
  needs_conversion(src, tgt)   THE decision predicate, shared by the insertion
                               and by Expression.generate_to's assertion
  emit_conversion(value, …)    the emission engine: tag-pack a variant into a
                               union, widen union→union, rebuild a wider tuple,
                               or materialise a zero of the target for the
                               uninhabited `Never` (dead code, shape only)
  matching_tuple_variant(…)    the one spelling of "which union variant does
                               this tuple fit"
"""
from __future__ import annotations

from typing import Callable, Any
import dataclasses
import pyast.rewrite as rw
from dataclasses import dataclass

from langtools import checked_cast
from parsing.parselib import Error

import codegen.param as cg_p

import pyast.resolver as g
import pyast.statement as s
import pyast.typespec as t
from pyast import union_repr
from pyast.expression.base import Expression


@dataclass
class ConvertExpression(Expression):
    """Represent `inner`'s value as type `target` — the explicit conversion
    node whose presence in the tree IS the decision to convert."""
    inner: Expression
    target: t.TypeSpec

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver, Any], Any]) -> Expression:
        return rw.rewrite(self, replace, resolver,
            inner=self.inner.search_and_replace(resolver, replace),
            target=self.target.search_and_replace(resolver, replace))

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec:
        return self.target

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement]]:
        inner, stmts = self.inner.compile(resolver, None)
        target, spec_stmts = self.target.compile(resolver)
        return dataclasses.replace(self, inner=inner, target=target), stmts + spec_stmts

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        return self.inner.check(resolver, None)

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        bundle = self.inner.generate(resolver)
        return bundle + emit_conversion(bundle.result_var,
                                        self.inner.get_type(resolver), self.target, resolver)


def converted(expr: Expression, expected: t.TypeSpec | None,
              resolver: g.Resolver) -> Expression:
    """Compile-side conversion insertion: wrap `expr` in a ConvertExpression
    when representing its value as `expected` requires a representation change
    (needs_conversion — the one shared decision). Identity while either side is
    not ground yet (the fixpoint asks again) and when the types already agree,
    so insertion is idempotent across compile passes."""
    if expected is None:
        return expr
    if needs_conversion(expr.get_type(resolver), expected, resolver):
        return ConvertExpression(expr.line_ref, expr, expected)
    return expr


def _passthrough(value) -> g.OperationBundle:
    return g.OperationBundle((), (), value)


def matching_tuple_variant(source: "t.TupleSpec", target: "t.CombinationSpec",
                           resolver: g.Resolver) -> "t.TypeSpec | None":
    """The unique tuple variant of union `target` that tuple `source` fits, or
    None. THE single home for this match — needs_conversion (the decision),
    coerce (the emission) and lowering/boxing.py (the insertion) all call it.
    More than one match means nominally distinct variants collapsed to one
    structural spec, which simple_classes' union-collision pruning must have
    prevented — assert it."""
    matching = [v for v in target.repr_members()
                if isinstance(v, t.TupleSpec)
                and v.trivially_assignable_from(resolver, source) is True]
    assert len(matching) <= 1, (
        f"ambiguous union boxing: tuple value fits {len(matching)} variants of "
        f"{target.as_unique_id_str()}")
    return matching[0] if matching else None


def needs_conversion(source: t.TypeSpec | None, target: t.TypeSpec | None,
                     resolver: g.Resolver) -> bool:
    """Would representing a `source`-typed value as `target` require a
    representation change? Mirrors `coerce`'s non-passthrough cases exactly —
    the single home for the decision. Undecidable (either side not ground
    enough) is False: the compile fixpoint asks again once types refine."""
    if source is None or target is None:
        return False
    if isinstance(source, t.EnumSpec) and not source.valid_leaf_names:
        # Uninhabited source (Never): dead code, but the SHAPE must change
        # unless the target is identical.
        return source.as_unique_id_str() != target.as_unique_id_str()
    su, tu = source.as_unique_id_str(), target.as_unique_id_str()
    if su is None or tu is None or su == tu:
        return False
    if isinstance(target, t.TupleSpec):
        return (isinstance(source, t.TupleSpec)
                and len(source.entries) == len(target.entries)
                and any(needs_conversion(s_e.type, t_e.type, resolver)
                        for s_e, t_e in zip(source.entries, target.entries)))
    if isinstance(target, t.CombinationSpec):
        if isinstance(source, t.TupleSpec):
            return matching_tuple_variant(source, target, resolver) is not None
        if isinstance(source, t.CombinationSpec):
            return True     # distinct union ids ⇒ widening/re-slotting
        return any(v.as_unique_id_str() == su for v in target.repr_members())
    return False


def emit_conversion(value, source: t.TypeSpec | None, target: t.TypeSpec | None,
           resolver: g.Resolver) -> g.OperationBundle:
    """Emit the representation change over an already-generated `value` of
    TypeSpec `source`, producing it as `target`. Called only from
    ConvertExpression.generate — generate itself never converts."""
    if value is None or source is None or target is None:
        return _passthrough(value)

    # The empty/bottom type (a leafless enum like `Never`) has no values, so this
    # coercion is only reachable in dead code — e.g. the `Error` arm of a match
    # over a stream whose error type is `Never`. Passing the `Never`-shaped value
    # through to a differently-shaped target produces a function-signature /
    # representation mismatch at codegen; materialise a zero of the TARGET repr
    # instead (correct shape; the value is never actually observed at runtime).
    if isinstance(source, t.EnumSpec) and not source.valid_leaf_names:
        return g.OperationBundle((), (), cg_p.ZeroOf(target.generate(resolver)))

    su = source.as_unique_id_str()
    if su is not None and su == target.as_unique_id_str():
        return _passthrough(value)  # same representation — nothing to do

    if isinstance(target, t.TupleSpec):
        if isinstance(source, t.TupleSpec):
            return _convert_tuple(value, source, target, resolver)
        return _passthrough(value)

    if isinstance(target, t.CombinationSpec):
        if isinstance(source, t.TupleSpec):
            return _tuple_into_union(value, source, target, resolver)
        if isinstance(source, t.CombinationSpec):
            # The target union's repr owns the widening (re-slot / null-check),
            # given the source repr.
            return union_repr.classify(target, resolver).widen_from(
                union_repr.classify(source, resolver), value, resolver)
        return _pack_variant(value, source, target, resolver)

    return _passthrough(value)


# ---------------------------------------------------------------------------
# Tuple → wider tuple / tuple → union containing a tuple variant
# ---------------------------------------------------------------------------

def _convert_tuple(value, source: t.TupleSpec, target: t.TupleSpec,
                  resolver: g.Resolver) -> g.OperationBundle:
    """Rebuild a tuple value with each field coerced to the target field type.

    Reached only when `source != target`, so at least one field widens; reading
    the unchanged fields back out and re-packing them is cheap and keeps the
    logic uniform with the non-literal case (a tuple-typed call result, etc.)."""
    if len(source.entries) != len(target.entries):
        return _passthrough(value)
    bundle = g.OperationBundle()
    field_values: list[tuple[str, cg_p.RParam]] = []
    for i, (s_entry, t_entry) in enumerate(zip(source.entries, target.entries)):
        fname = f"_{i}"
        cb = emit_conversion(cg_p.StructField(value, fname), s_entry.type, t_entry.type,
                    resolver).with_prefix(f"f{i}")
        bundle = bundle + cb
        field_values.append((fname, cb.result_var))
    return bundle + g.OperationBundle((), (), cg_p.NewStruct(tuple(field_values)))


def _tuple_into_union(value, source: t.TupleSpec, target: t.CombinationSpec,
                      resolver: g.Resolver) -> g.OperationBundle:
    """Box a tuple value into a union that contains a single matching tuple
    variant (matching_tuple_variant — the shared match). No match is a
    pass-through, as in the old `__box_tuple_into_union`."""
    variant = matching_tuple_variant(source, target, resolver)
    if variant is None:
        return _passthrough(value)
    tuple_bundle = emit_conversion(value, source, variant, resolver)
    box_bundle = _pack_variant(tuple_bundle.result_var, variant, target, resolver)
    return tuple_bundle + box_bundle


# ---------------------------------------------------------------------------
# Non-union variant → union (tag-packing)
# ---------------------------------------------------------------------------

def _pack_variant(value, source: t.TypeSpec, target: t.CombinationSpec,
                 resolver: g.Resolver) -> g.OperationBundle:
    """Box a non-union value into a union that holds it as a direct variant.

    Pass-through if `source` is not a variant of `target` — matches the old
    `__box_singleton_variant` guard (the function-body implicit return can reach
    here with a unit value against a non-nullable union; that must be inert)."""
    su = source.as_unique_id_str()
    variant_idx = next((i for i, v in enumerate(target.repr_members())
                        if v.as_unique_id_str() == su), None) if su is not None else None
    if variant_idx is None:
        return _passthrough(value)
    # The union's repr owns the representation-specific packing (collapsed
    # pointer word vs tagged struct).
    return union_repr.classify(target, resolver).box_value(value, source, resolver)
