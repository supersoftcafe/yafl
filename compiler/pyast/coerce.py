"""IR-level union boxing/widening, applied at generation sinks.

`coerce(value, source, target, resolver)` returns an `OperationBundle` whose
`result_var` holds `value` — an already-generated RParam whose TypeSpec is
`source` — represented as TypeSpec `target` (tag-packed into a union, widened to
a larger union, or rebuilt as a wider tuple). When no representation change is
needed it returns a bundle that simply carries `value` through unchanged.

This replaces the old AST-level boxing pass (`lowering/boxing.py`), which walked
the AST inserting marker nodes whose `generate` emitted the tag-packing. Instead,
each generation *sink* — return, let, call argument, `[tail]` recur, and the
per-branch merge of ternary/match — calls `coerce` directly via
`Expression.generate_to`, with the TypeSpec still in hand so variant tags (keyed
on `as_unique_id_str`) resolve. The decision of *whether* to coerce mirrors the
old `__box_expr`: anything boxing would have left untouched is a pass-through
here.
"""
from __future__ import annotations

import codegen.param as cg_p

import pyast.resolver as g
import pyast.typespec as t
from pyast import union_repr


def _passthrough(value) -> g.OperationBundle:
    return g.OperationBundle((), (), value)


def coerce(value, source: t.TypeSpec | None, target: t.TypeSpec | None,
           resolver: g.Resolver) -> g.OperationBundle:
    """Coerce already-generated `value` from TypeSpec `source` to `target`."""
    if value is None or source is None or target is None:
        return _passthrough(value)

    su = source.as_unique_id_str()
    if su is not None and su == target.as_unique_id_str():
        return _passthrough(value)  # same representation — nothing to do

    if isinstance(target, t.TupleSpec):
        if isinstance(source, t.TupleSpec):
            return _coerce_tuple(value, source, target, resolver)
        return _passthrough(value)

    if isinstance(target, t.CombinationSpec):
        if isinstance(source, t.TupleSpec):
            return _tuple_into_union(value, source, target, resolver)
        if isinstance(source, t.CombinationSpec):
            # The target union's repr owns the widening (re-slot / null-check),
            # given the source repr.
            return union_repr.classify(target, resolver).widen_from(
                union_repr.classify(source, resolver), value, resolver)
        return _box_variant(value, source, target, resolver)

    return _passthrough(value)


# ---------------------------------------------------------------------------
# Tuple → wider tuple / tuple → union containing a tuple variant
# ---------------------------------------------------------------------------

def _coerce_tuple(value, source: t.TupleSpec, target: t.TupleSpec,
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
        cb = coerce(cg_p.StructField(value, fname), s_entry.type, t_entry.type,
                    resolver).with_prefix(f"f{i}")
        bundle = bundle + cb
        field_values.append((fname, cb.result_var))
    return bundle + g.OperationBundle((), (), cg_p.NewStruct(tuple(field_values)))


def _tuple_into_union(value, source: t.TupleSpec, target: t.CombinationSpec,
                      resolver: g.Resolver) -> g.OperationBundle:
    """Box a tuple value into a union that contains a single matching tuple
    variant. Ambiguity (no match, or more than one) is a pass-through, as in the
    old `__box_tuple_into_union`."""
    matching = [v for v in target.types
                if isinstance(v, t.TupleSpec)
                and v.trivially_assignable_from(resolver, source) is True]
    assert len(matching) <= 1, (
        f"ambiguous union boxing: tuple value fits {len(matching)} variants of "
        f"{target.as_unique_id_str()} — nominally distinct variants have collapsed "
        f"to one structural spec (simple_classes union-collision pruning should "
        f"have prevented this)")
    if not matching:
        return _passthrough(value)
    variant = matching[0]
    tuple_bundle = coerce(value, source, variant, resolver)
    box_bundle = _box_variant(tuple_bundle.result_var, variant, target, resolver)
    return tuple_bundle + box_bundle


# ---------------------------------------------------------------------------
# Non-union variant → union (tag-packing)
# ---------------------------------------------------------------------------

def _box_variant(value, source: t.TypeSpec, target: t.CombinationSpec,
                 resolver: g.Resolver) -> g.OperationBundle:
    """Box a non-union value into a union that holds it as a direct variant.

    Pass-through if `source` is not a variant of `target` — matches the old
    `__box_singleton_variant` guard (the function-body implicit return can reach
    here with a unit value against a non-nullable union; that must be inert)."""
    su = source.as_unique_id_str()
    variant_idx = next((i for i, v in enumerate(target.types)
                        if v.as_unique_id_str() == su), None) if su is not None else None
    if variant_idx is None:
        return _passthrough(value)
    # The union's repr owns the representation-specific packing (collapsed
    # pointer word vs tagged struct).
    return union_repr.classify(target, resolver).box_value(value, source, resolver)
