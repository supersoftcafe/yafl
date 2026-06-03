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
class BoxExpression(Expression):
    """Widen a value of a variant type into its enclosing union type."""
    inner: Expression
    union_spec: t.CombinationSpec

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver, Any], Any]) -> Expression:
        return cast(Expression, replace(resolver, dataclasses.replace(self,
            inner=self.inner.search_and_replace(resolver, replace),
            union_spec=cast(t.CombinationSpec, self.union_spec.search_and_replace(resolver, replace)))))

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec:
        return self.union_spec

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement]]:
        inner, stmts = self.inner.compile(resolver, None)
        union_spec, spec_stmts = self.union_spec.compile(resolver)
        return dataclasses.replace(self, inner=inner, union_spec=cast(t.CombinationSpec, union_spec)), stmts + spec_stmts

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        return self.inner.check(resolver, None)

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        inner_bundle = self.inner.generate(resolver)
        target_ctype = self.union_spec.generate(resolver)

        # DataPointer union: exactly one non-unit pointer variant + optional unit (None)
        if isinstance(target_ctype, cg_t.DataPointer):
            inner_ctype = self.inner.get_type(resolver).generate(resolver)
            if inner_ctype == cg_t.Struct(()):  # unit/None variant
                return g.OperationBundle(inner_bundle.stack_vars, inner_bundle.operations, cg_p.NullPointer())
            return inner_bundle  # Already a DataPointer — pass through

        # Struct-based tagged union
        assert isinstance(target_ctype, cg_t.Struct), f"Expected Struct (tagged union), got {target_ctype}"
        variant_types = [v.generate(resolver) for v in self.union_spec.types]
        _, variant_map = cg_t.compute_union_slots(variant_types)

        inner_ctype = self.inner.get_type(resolver).generate(resolver)

        # Identity boxing: inner already carries the full union representation.
        # This happens when a match expression whose arms all return the boxed
        # union is itself nested inside another box for the same union type.
        if inner_ctype == target_ctype:
            return inner_bundle

        variant_idx = next(i for i, vt in enumerate(variant_types) if vt == inner_ctype)

        discriminators = resolver.get_discriminators()
        tag_value = discriminators.get(self.union_spec.types[variant_idx].as_unique_id_str(), 0)
        slot_values = self.__build_variant_slots(inner_ctype, inner_bundle, variant_map[variant_idx], target_ctype.fields)
        slot_values.append(("$tag", cg_p.Integer(tag_value, 32)))
        return inner_bundle + g.OperationBundle((), (), cg_p.union_struct(target_ctype, dict(slot_values)))

    def __build_variant_slots(self, inner_ctype, inner_bundle, slot_assignments, slot_fields):
        """Map the inner value's primitives to their union slots; returns slot (name, value) pairs.

        Handles arbitrarily nested struct fields: a TupleSpec (key: Str, value: FlatEnum)
        generates Struct([('_0', Str), ('_1', FlatEnum_struct)]).  FlatEnum_struct has
        multiple primitives, so we recurse into it, reading each sub-field via nested
        StructField and mapping it to its assigned union slot.
        """
        inner_prims = cg_t._flatten_primitives(inner_ctype)
        if len(inner_prims) == 0:
            return []  # unit variant: no slot values

        def collect(param, ctype, offset):
            """Yield (slot_name, value) pairs, advancing offset past each primitive."""
            if isinstance(ctype, cg_t.Struct):
                result = []
                for field_name, field_type in ctype.fields:
                    part, offset = collect(cg_p.StructField(param, field_name), field_type, offset)
                    result.extend(part)
                return result, offset
            # Primitive (DataPointer, Int, Float, Str, etc.)
            si, _ = slot_assignments[offset]
            return [(slot_fields[si][0], param)], offset + 1

        result, _ = collect(inner_bundle.result_var, inner_ctype, 0)
        return result



@dataclass
class WideExpression(Expression):
    """Widen a value of one union type to a strictly wider union type.

    Handles DataPointer → Struct (null-check) and
    Struct → Struct (tag-based re-slot) widening.
    """
    inner: Expression
    source_spec: t.CombinationSpec
    target_spec: t.CombinationSpec

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver, Any], Any]) -> Expression:
        return cast(Expression, replace(resolver, dataclasses.replace(self,
            inner=self.inner.search_and_replace(resolver, replace),
            source_spec=cast(t.CombinationSpec, self.source_spec.search_and_replace(resolver, replace)),
            target_spec=cast(t.CombinationSpec, self.target_spec.search_and_replace(resolver, replace)))))

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec:
        return self.target_spec

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement]]:
        inner, stmts = self.inner.compile(resolver, None)
        src, src_stmts = self.source_spec.compile(resolver)
        tgt, tgt_stmts = self.target_spec.compile(resolver)
        return dataclasses.replace(self,
            inner=inner,
            source_spec=cast(t.CombinationSpec, src),
            target_spec=cast(t.CombinationSpec, tgt)), stmts + src_stmts + tgt_stmts

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        return self.inner.check(resolver, None)

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        inner_bundle = self.inner.generate(resolver)
        src_ctype = self.source_spec.generate(resolver)
        tgt_ctype = self.target_spec.generate(resolver)

        # DataPointer → DataPointer widening is a pass-through. Both unions use
        # the same tag-bit-dispatch encoding, and every variant in the source
        # spec is also a variant in the target spec with identical pointer
        # representation.
        if isinstance(tgt_ctype, cg_t.DataPointer):
            assert isinstance(src_ctype, cg_t.DataPointer), \
                f"WideExpression: DataPointer target requires DataPointer source, got {src_ctype}"
            return inner_bundle

        assert isinstance(tgt_ctype, cg_t.Struct), \
            f"WideExpression: target must be Struct (tagged union), got {tgt_ctype}"

        tgt_container, tgt_variant_map = cg_t.compute_union_slots([v.generate(resolver) for v in self.target_spec.types])
        discriminators = resolver.get_discriminators()
        result_var = cg_p.StackVar(tgt_ctype, "wide_result")
        end_label = "wide_end"
        sv = inner_bundle.result_var

        # Each widening path computes a tagged-union struct value as an
        # inline RParam expression. The Phi at the join collects one such
        # expression per predecessor edge — codegen emits per-edge Moves
        # into `result_var`, evaluating the expression at the right point.
        # `wide_results` keeps the `(exit_label, expr)` pairs in the order
        # the branches are emitted.
        wide_results: list[tuple[str, cg_p.RParam]] = []

        if isinstance(src_ctype, cg_t.DataPointer):
            body = self.__widen_from_datapointer(
                sv, src_ctype, tgt_ctype, tgt_variant_map, tgt_container.fields,
                discriminators, end_label, wide_results, resolver)
        else:
            assert isinstance(src_ctype, cg_t.Struct), \
                f"WideExpression: source must be DataPointer or Struct (tagged union), got {src_ctype}"
            body = self.__widen_from_container(
                sv, src_ctype, tgt_ctype, tgt_variant_map, tgt_container.fields,
                discriminators, end_label, wide_results, resolver)

        join = g.OperationBundle(
            stack_vars=(result_var,),
            operations=(
                cg_o.Label(end_label),
                cg_o.Phi(target=result_var, sources=tuple(wide_results)),
            ),
            result_var=result_var)
        bundles = [inner_bundle] + body + [join]
        return reduce(lambda a, b: a + b, bundles)

    def __widen_from_datapointer(self, sv, src_ctype, tgt_ctype, tgt_variant_map, tgt_slot_fields,
                                  discriminators, end_label, wide_results, resolver):
        """Widen a DataPointer union (null = unit/None, non-null = pointer variant) to a tagged-union Struct.

        Two paths feed the join: the non-null pointer path and the null
        path. Each contributes a single tagged-union expression to the Phi
        via `wide_results`; codegen emits per-edge Moves into the result.
        """
        unit_type = cg_t.Struct(())
        src_variant_types = [v.generate(resolver) for v in self.source_spec.types]
        ptr_variant = next((v for v, vt in zip(self.source_spec.types, src_variant_types) if vt != unit_type), None)
        unit_variant = next((v for v, vt in zip(self.source_spec.types, src_variant_types) if vt == unit_type), None)
        assert ptr_variant is not None, "DataPointer union must have a non-unit pointer variant"

        null_label = "wide_null"
        ptr_uid = ptr_variant.as_unique_id_str()
        ptr_tag = discriminators.get(ptr_uid, 0)
        tgt_ptr_idx = next((i for i, v in enumerate(self.target_spec.types) if v.as_unique_id_str() == ptr_uid), None)
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

    def __widen_from_container(self, sv, src_ctype, tgt_ctype, tgt_variant_map, tgt_slot_fields,
                                discriminators, end_label, wide_results, resolver):
        """Widen a tagged-union Struct to a wider tagged-union Struct by re-slotting each variant.

        One arm per source variant. Each contributes its tagged-union
        expression to `wide_results`; the Phi at the join collects them.
        """
        src_variant_types = [v.generate(resolver) for v in self.source_spec.types]
        _, src_variant_map = cg_t.compute_union_slots(src_variant_types)
        src_tag_field = cg_p.StructField(sv, "$tag")

        bundles = []
        for i, src_var in enumerate(self.source_spec.types):
            var_uid = src_var.as_unique_id_str()
            var_tag = discriminators.get(var_uid, 0)
            arm_label, next_label = f"wide_arm_{i}", f"wide_next_{i}"
            exit_label = f"wide_exit_{i}"

            tgt_var_idx = next(
                (ti for ti, tv in enumerate(self.target_spec.types) if tv.as_unique_id_str() == var_uid), None)
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
        # All source variants are enumerated; any tag outside that set is
        # unreachable at runtime.  Make that explicit so the end-label join
        # has no uninitialised-result path.
        bundles.append(g.OperationBundle(operations=(
            cg_o.Abort(reason="container-widening fell through all source variants"),)))
        return bundles



