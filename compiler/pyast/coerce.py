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

from functools import reduce

import codegen.ops as cg_o
import codegen.param as cg_p
import codegen.typedecl as cg_t

import pyast.resolver as g
import pyast.typespec as t


def _passthrough(value) -> g.OperationBundle:
    return g.OperationBundle((), (), value)


def _unwrap_to_pointer_word(value, ctype):
    """Peel single-field newtype wrappers down to the bare pointer word stored
    in a collapsed pointer-union. A single-field struct is layout-identical to
    its field, so reading the field yields the pointer (e.g. a simple class
    `A(x: T)` lowered to the tuple `(T)` -> `value._0`). A value that is already
    a bare DataPointer passes through unchanged."""
    while isinstance(ctype, cg_t.Struct) and len(ctype.fields) == 1:
        fname, ctype = ctype.fields[0]
        value = cg_p.StructField(value, fname)
    return value


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
            return _widen(value, source, target, resolver)
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

    target_ctype = target.generate(resolver)
    inner_ctype = source.generate(resolver)

    # Collapsed pointer union: every member is a distinguishable pointer-word.
    if isinstance(target_ctype, cg_t.DataPointer):
        if inner_ctype == cg_t.Struct(()):  # unit / None variant
            return g.OperationBundle((), (), cg_p.NullPointer())
        # Unwrap a single-field newtype value to its bare pointer; a value that
        # is already a DataPointer (class / immediate) passes straight through.
        return g.OperationBundle((), (), _unwrap_to_pointer_word(value, inner_ctype))

    assert isinstance(target_ctype, cg_t.Struct), \
        f"Expected Struct (tagged union), got {target_ctype}"

    # Identity boxing: value already carries the full union representation.
    if inner_ctype == target_ctype:
        return _passthrough(value)

    variant_types = [v.generate(resolver) for v in target.types]
    _, variant_map = cg_t.compute_union_slots(variant_types)
    discriminators = resolver.get_discriminators()
    tag_value = discriminators.get(su, 0)
    slot_values = _variant_slots(value, inner_ctype, variant_map[variant_idx], target_ctype.fields)
    slot_values.append(("$tag", cg_p.Integer(tag_value, 32)))
    return g.OperationBundle((), (), cg_p.union_struct(target_ctype, dict(slot_values)))


def _variant_slots(value, inner_ctype, slot_assignments, slot_fields):
    """Map the value's primitives to their union slots; returns slot (name, value) pairs.

    Handles arbitrarily nested struct fields: a TupleSpec (key: Str, value: FlatEnum)
    generates Struct([('_0', Str), ('_1', FlatEnum_struct)]). FlatEnum_struct has
    multiple primitives, so we recurse into it, reading each sub-field via nested
    StructField and mapping it to its assigned union slot."""
    if len(cg_t._flatten_primitives(inner_ctype)) == 0:
        return []  # unit variant: no slot values

    def collect(param, ctype, offset):
        if isinstance(ctype, cg_t.Struct):
            result = []
            for field_name, field_type in ctype.fields:
                part, offset = collect(cg_p.StructField(param, field_name), field_type, offset)
                result.extend(part)
            return result, offset
        si, _ = slot_assignments[offset]
        return [(slot_fields[si][0], param)], offset + 1

    result, _ = collect(value, inner_ctype, 0)
    return result


# ---------------------------------------------------------------------------
# Union → wider union (re-slot / null-check)
# ---------------------------------------------------------------------------

def _widen(value, source: t.CombinationSpec, target: t.CombinationSpec,
           resolver: g.Resolver) -> g.OperationBundle:
    """Widen a union value to a strictly wider union: DataPointer → Struct
    (null-check), Struct → Struct (tag-based re-slot), or DataPointer →
    DataPointer / Struct passthrough."""
    src_ctype = source.generate(resolver)
    tgt_ctype = target.generate(resolver)

    # DataPointer target: both unions use the same tag-bit-dispatch encoding and
    # every source variant is a target variant with identical pointer repr.
    if isinstance(tgt_ctype, cg_t.DataPointer):
        assert isinstance(src_ctype, cg_t.DataPointer), \
            f"widen: DataPointer target requires DataPointer source, got {src_ctype}"
        return _passthrough(value)

    assert isinstance(tgt_ctype, cg_t.Struct), \
        f"widen: target must be Struct (tagged union), got {tgt_ctype}"

    tgt_container, tgt_variant_map = cg_t.compute_union_slots(
        [v.generate(resolver) for v in target.types])
    discriminators = resolver.get_discriminators()
    result_var = cg_p.StackVar(tgt_ctype, "wide_result")
    end_label = "wide_end"

    # Each widening path computes a tagged-union struct value as an inline RParam
    # expression. The Phi at the join collects one such expression per
    # predecessor edge — codegen emits per-edge Moves into `result_var`.
    wide_results: list[tuple[str, cg_p.RParam]] = []

    if isinstance(src_ctype, cg_t.DataPointer):
        body = _widen_from_datapointer(
            value, source, target, tgt_ctype, tgt_variant_map, tgt_container.fields,
            discriminators, end_label, wide_results, resolver)
    else:
        assert isinstance(src_ctype, cg_t.Struct), \
            f"widen: source must be DataPointer or Struct (tagged union), got {src_ctype}"
        body = _widen_from_container(
            value, src_ctype, source, target, tgt_ctype, tgt_variant_map, tgt_container.fields,
            discriminators, end_label, wide_results, resolver)

    join = g.OperationBundle(
        stack_vars=(result_var,),
        operations=(
            cg_o.Label(end_label),
            cg_o.Phi(target=result_var, sources=tuple(wide_results)),
        ),
        result_var=result_var)
    return reduce(lambda a, b: a + b, body + [join])


def _widen_from_datapointer(sv, source, target, tgt_ctype, tgt_variant_map, tgt_slot_fields,
                            discriminators, end_label, wide_results, resolver):
    """Widen a DataPointer union (null = unit/None, non-null = pointer variant) to
    a tagged-union Struct. The non-null pointer path and the null path each
    contribute a single tagged-union expression to the Phi via `wide_results`."""
    unit_type = cg_t.Struct(())
    src_variant_types = [v.generate(resolver) for v in source.types]
    ptr_variant = next((v for v, vt in zip(source.types, src_variant_types) if vt != unit_type), None)
    unit_variant = next((v for v, vt in zip(source.types, src_variant_types) if vt == unit_type), None)
    assert ptr_variant is not None, "DataPointer union must have a non-unit pointer variant"

    null_label = "wide_null"
    ptr_uid = ptr_variant.as_unique_id_str()
    ptr_tag = discriminators.get(ptr_uid, 0)
    tgt_ptr_idx = next((i for i, v in enumerate(target.types) if v.as_unique_id_str() == ptr_uid), None)
    slot_values = [(tgt_slot_fields[tgt_si][0], sv) for tgt_si, _ in tgt_variant_map[tgt_ptr_idx]] \
        if tgt_ptr_idx is not None else []
    slot_values.append(("$tag", cg_p.Integer(ptr_tag, 32)))

    unit_tag = discriminators.get(unit_variant.as_unique_id_str(), 0) if unit_variant else 0

    wide_results.append(("ptr_exit",  cg_p.union_struct(tgt_ctype, dict(slot_values))))
    wide_results.append(("null_exit", cg_p.union_struct(tgt_ctype, {"$tag": cg_p.Integer(unit_tag, 32)})))

    return [
        g.OperationBundle(operations=(cg_o.JumpIf(null_label, cg_p.IntEqConst(sv, 0)),)),
        g.OperationBundle(operations=(cg_o.Label("ptr_exit"), cg_o.Jump(end_label), cg_o.Label(null_label))),
        g.OperationBundle(operations=(cg_o.Label("null_exit"),)),
    ]


def _widen_from_container(sv, src_ctype, source, target, tgt_ctype, tgt_variant_map, tgt_slot_fields,
                          discriminators, end_label, wide_results, resolver):
    """Widen a tagged-union Struct to a wider tagged-union Struct by re-slotting
    each variant. One arm per source variant, each contributing its tagged-union
    expression to `wide_results`."""
    src_variant_types = [v.generate(resolver) for v in source.types]
    _, src_variant_map = cg_t.compute_union_slots(src_variant_types)
    src_tag_field = cg_p.StructField(sv, "$tag")

    bundles = []
    for i, src_var in enumerate(source.types):
        var_uid = src_var.as_unique_id_str()
        var_tag = discriminators.get(var_uid, 0)
        arm_label, next_label = f"wide_arm_{i}", f"wide_next_{i}"
        exit_label = f"wide_exit_{i}"

        tgt_var_idx = next(
            (ti for ti, tv in enumerate(target.types) if tv.as_unique_id_str() == var_uid), None)
        slot_values = []
        if tgt_var_idx is not None:
            for pi in range(len(cg_t._flatten_primitives(src_var.generate(resolver)))):
                tgt_si, _ = tgt_variant_map[tgt_var_idx][pi]
                src_si, _ = src_variant_map[i][pi]
                slot_values.append((tgt_slot_fields[tgt_si][0], cg_p.StructField(sv, src_ctype.fields[src_si][0])))
        slot_values.append(("$tag", cg_p.Integer(var_tag, 32)))

        wide_results.append((exit_label, cg_p.union_struct(tgt_ctype, dict(slot_values))))

        bundles.append(g.OperationBundle(operations=(
            cg_o.JumpIf(arm_label, cg_p.IntEqConst(src_tag_field, var_tag)),
            cg_o.Jump(next_label), cg_o.Label(arm_label),
        )))
        bundles.append(g.OperationBundle(operations=(
            cg_o.Label(exit_label),
            cg_o.Jump(end_label),
        )))
        bundles.append(g.OperationBundle(operations=(cg_o.Label(next_label),)))
    # All source variants are enumerated; any tag outside that set is unreachable.
    bundles.append(g.OperationBundle(operations=(
        cg_o.Abort(reason="container-widening fell through all source variants"),)))
    return bundles
