"""How a union type is represented and operated on — one classification, one
place.

A "union" is either a `CombinationSpec` (ad-hoc `A|B|None`) or an `EnumSpec` (a
declared enum, itself a union of variants). It has one of three representations,
historically decided ad-hoc and operated on at ~20 sites. `classify` makes the
decision ONCE; the returned `UnionRepr` owns the representation-specific
operations so callers stop re-deriving `isinstance(ctype, DataPointer)` /
`is_complex` / `pointer_word_kind`.

    TaggedRepr      by-value {$s0.., $tag} struct (codegen.typedecl.compute_union_slots).
                    Non-collapsing CombinationSpec and flat (non-complex) EnumSpec.
    PointerRepr     one DataPointer word; None=NULL, every other member dispatches
                    by its pointer tag / vtable. Collapsing CombinationSpec.
    ComplexEnumRepr DataPointer + per-variant heap objects, dispatch by
                    vtable.discriminator. Complex EnumSpec.

Every representation-specific operation lives on the repr it belongs to:
`ctype()` (the C type), `generate_match` (match dispatch), `construct_enum_value`
/ `box_value` (construction & boxing), `read_field`, and `widen_from` (union
widening). The scattered call sites — `typespec.*.generate`, `match`, `coerce`,
`access`, `new` — are thin delegators to `classify(...)`, which is the single
place the R1/R2/R3 decision is made.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from functools import reduce
import dataclasses

import langtools
import pyast.typespec as t
import pyast.statement as s
import pyast.resolver as g
import codegen.typedecl as cg_t
import codegen.param as cg_p
import codegen.ops as cg_o


def literal_eq_test(lit_type_name: str, value: cg_p.RParam,
                     literal: cg_p.RParam) -> cg_p.RParam:
    """Boolean IR expression comparing a primitive `value` to a `literal`."""
    args = cg_p.NewStruct((("a", value), ("b", literal)))
    if lit_type_name == "str":
        return cg_p.IntEqConst(cg_p.Invoke("string_compare", args, cg_t.Int(32)), 0)
    if lit_type_name == "bigint":
        return cg_p.Invoke("integer_test_eq", args, cg_t.Int(8))
    return cg_p.Invoke(f"{lit_type_name}_test_eq", args, cg_t.Int(8))  # int8..int64


def _classspec_is_foreign(member: t.ClassSpec, resolver: g.Resolver) -> bool:
    """A `[foreign]` class's vtable symbol lives in an external library, so it
    can't be vtable-identity-tested from generated code (it acts as the at-most-
    one implicit fallback in a pointer-union dispatch)."""
    for resolved in resolver.find_type(member.name):
        stmt = resolved.statement
        if isinstance(stmt, s.ClassStatement) and "foreign" in stmt.attributes:
            return True
    return False


def _pointer_word_kind(member: t.TypeSpec, resolver: g.Resolver) -> tuple | None:
    """The runtime dispatch kind of a union member IF it is representable as a
    single pointer-word (a heap pointer or a tagged immediate), looking through
    single-field newtype tuples (a simple class lowers to `(field)`, which is
    layout-identical to its field). `None` if the member is genuinely multi-word
    (scalar, multi-field tuple/struct, flat enum).

    Kinds are hashable tokens; two members that share a kind are NOT runtime-
    distinguishable, so a union containing them must stay a tagged struct:
      ('UNIT',)        empty tuple / None        -> NULL sentinel
      ('INT',)         bigint                    -> PTR_TAG_INTEGER / INTEGER_VTABLE
      ('STR',)         str                       -> PTR_TAG_STRING / STRING_VTABLE
      ('CLASS', name)  heap class                -> its own vtable
      ('ENUM', root)   complex enum              -> the root marker vtable
      ('FOREIGN',)     foreign class             -> untestable; the fallback
    """
    if member.generate(resolver) == cg_t.Struct(()):     # unit / None
        return ('UNIT',)
    if (isinstance(member, t.TupleSpec) and len(member.entries) == 1
            and member.entries[0].type is not None):     # newtype wrapper
        return _pointer_word_kind(member.entries[0].type, resolver)
    if isinstance(member, t.BuiltinSpec):
        if member.type_name == "bigint":
            return ('INT',)
        if member.type_name == "str":
            return ('STR',)
        return None                                       # int32, float, bool, ...
    if isinstance(member, t.ClassSpec):
        # A ClassSpec surviving to generate() is a non-simple class (simple ones
        # are already TupleSpec). All heap classes are a single pointer-word.
        return ('FOREIGN',) if _classspec_is_foreign(member, resolver) else ('CLASS', member.name)
    if isinstance(member, t.EnumSpec):
        # Complex enums use per-variant vtables (a pointer-word); flat enums are
        # a tagged struct, so not pointer-representable here.
        return ('ENUM', member.root_name) if member.is_complex else None
    return None


def _union_collapses_to_pointer(members: list, resolver: g.Resolver) -> bool:
    """A union collapses to a single pointer-word iff every member is a pointer-
    word AND the members are mutually runtime-distinguishable: at most one unit
    (NULL), at most one foreign class (the fallback), and the remaining testable
    kinds all distinct. This also rejects two newtypes over the same inner type
    (e.g. `Id=(str)` and `Name=(str)`) and 2+ distinct unit variants, both of
    which would be indistinguishable as a bare pointer."""
    kinds = [_pointer_word_kind(m, resolver) for m in members]
    if any(k is None for k in kinds):
        return False
    if not any(k != ('UNIT',) for k in kinds):
        return False  # all-unit: a compact int tag (compute_union_slots) is smaller
    if kinds.count(('UNIT',)) > 1 or kinds.count(('FOREIGN',)) > 1:
        return False
    testable = [k for k in kinds if k not in (('UNIT',), ('FOREIGN',))]
    return len(testable) == len(set(testable))


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


def _variant_slots(value, inner_ctype, slot_assignments, slot_fields):
    """Map a variant value's primitives to their union slots; returns slot
    (name, value) pairs. Recurses into nested struct fields (a tuple variant
    flattens into several primitives mapped to several slots)."""
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


class UnionRepr(ABC):
    """Base for the three union representations. Obtain one via `classify`."""

    @abstractmethod
    def ctype(self) -> cg_t.Type:
        """The C-level type a value of this union occupies."""
        ...

    @abstractmethod
    def generate_match(self, em, subj_bundle, arms, else_arm,
                       resolver: g.Resolver) -> None:
        """Emit the match dispatch for a subject of this union, driving the
        shared match emitter `em`. `em` keeps all orchestration (arm bodies,
        join Phi, binding) — the repr supplies the representation-specific
        guards and bound values via `em.arm` / `em.fallback` /
        `em.bind_subject` / `em.bind_from_slots` / `em.multi_entry_arm`."""
        ...

    # The four operations below are representation-*partial* — they only make
    # sense for some union kinds, so they are not abstract. A repr that does not
    # support one inherits the default here, which fails loudly (naming the repr
    # and operation) instead of raising a bare AttributeError. The split:
    #   box_value / widen_from          — CombinationSpec reprs (boxing a variant
    #                                      in, widening a narrower union in).
    #   read_field / construct_enum_value — EnumSpec reprs.
    # TaggedRepr serves BOTH roles (flat enum *and* non-collapsing combination)
    # and so overrides all four; PointerRepr is combination-only; ComplexEnumRepr
    # is enum-only. Callers route here via `classify`, whose return type already
    # matches the operation (CombinationSpec target -> box/widen; EnumSpec ->
    # read/construct), so these defaults guard against future miswiring.

    def box_value(self, value, source_type: t.TypeSpec,
                  resolver: g.Resolver) -> g.OperationBundle:
        """Box an already-generated variant `value` into this union's repr."""
        raise NotImplementedError(
            f"{type(self).__name__} does not support box_value (not a boxable union target)")

    def widen_from(self, src_repr: "UnionRepr", value,
                   resolver: g.Resolver) -> g.OperationBundle:
        """Widen a value from the narrower `src_repr` into this union's repr."""
        raise NotImplementedError(
            f"{type(self).__name__} does not support widen_from (not a widening target)")

    def read_field(self, base_value, field_name: str, resolver: g.Resolver):
        """Read field `field_name` off `base_value`, a value of this enum union."""
        raise NotImplementedError(
            f"{type(self).__name__} does not support read_field (not an enum union)")

    def construct_enum_value(self, leaf_name: str, field_args,
                             resolver: g.Resolver) -> g.OperationBundle:
        """Construct enum variant `leaf_name` from `field_args` in this repr."""
        raise NotImplementedError(
            f"{type(self).__name__} does not support construct_enum_value (not an enum union)")


@dataclasses.dataclass(frozen=True)
class TaggedRepr(UnionRepr):
    union_type: t.TypeSpec
    container: cg_t.Struct                      # {$s0.., $tag}
    variant_map: tuple                          # per-variant primitive -> slot (compute_union_slots)

    def ctype(self) -> cg_t.Type:
        return self.container

    def generate_match(self, em, subj_bundle, arms, else_arm, resolver):
        # Two tag-numbering flavours over the same {$s0..,$tag} layout: a flat
        # enum tags by positional leaf index and binds the whole struct; a
        # tagged combination tags by global discriminator and binds the value
        # narrowed/reslotted for the matched member.
        if isinstance(self.union_type, t.EnumSpec):
            self._generate_flat_enum_match(em, subj_bundle, arms, else_arm, resolver)
        else:
            self._generate_combination_match(em, subj_bundle, arms, else_arm, resolver)

    def _generate_flat_enum_match(self, em, subj_bundle, arms, else_arm, resolver):
        subj_type = self.union_type
        sv = subj_bundle.result_var
        tag = cg_p.StructField(sv, "$tag")
        # A leaf's tag is its position in the subject's leaf list. Match by BASE
        # identity (name before any `$generic$…` monomorphisation suffix): when a
        # generic enum is matched at a concrete instantiation, the subject's
        # all_leaf_names and an arm's valid_leaf_names can be specialised through
        # different passes and disagree only on that suffix — but a leaf's
        # identity within its enum is its base name, and the suffix is uniform
        # across all leaves of one instantiation, so base names stay unique.
        def _base(name: str) -> str:
            return name.split("$generic$", 1)[0]
        leaf_index = {_base(n): i for i, n in enumerate(subj_type.all_leaf_names)}
        def leaf_id(leaf: str) -> int:
            return leaf_index[_base(leaf)]
        for arm in (a for a in arms if a.type_spec is not None):
            arm_type = arm.type_spec
            assert isinstance(arm_type, t.EnumSpec)
            # valid_leaf_names is a frozenset; sort by discriminant for a fixed
            # (ascending) OR-guard order — set iteration is hash-seeded.
            guards = [cg_p.IntEqConst(tag, leaf_id(leaf))
                      for leaf in sorted(arm_type.valid_leaf_names, key=leaf_id)]
            # Bind at subj_type (always concrete): an EnumSpec arm_type may point
            # at a pruned generic spec with stale all_fields; only leaf identity
            # matters for the guards above.
            em.arm(arm, [guards], bind=em.bind_subject(arm, subj_type, sv))
        em.fallback(else_arm,
                    em.bind_subject(else_arm, subj_type, sv) if else_arm else None,
                    "enum match fell through all arms")

    def _generate_combination_match(self, em, subj_bundle, arms, else_arm, resolver):
        subj_type = self.union_type
        sv = subj_bundle.result_var
        tag = cg_p.StructField(sv, "$tag")
        discriminators = resolver.get_discriminators()
        # The slot layout is the repr's own data; `variant_types` is still needed
        # below to find a variant by its generated ctype (the `vt == arm_ctype`
        # lookup), but the slot map itself comes from `self`, not a recompute.
        variant_types = [v.generate(resolver) for v in subj_type.types]
        variant_map = self.variant_map
        slot_fields = self.container.fields

        def variant_index(uid: str | None) -> int | None:
            if uid is None:
                return None
            return next((i for i, v in enumerate(subj_type.types)
                         if v.as_unique_id_str() == uid), None)

        for arm in arms:
            if arm.type_spec is None and arm.literal is None:
                continue  # else arm: the fallback, handled at the end

            if arm.literal is not None:
                lit_ast_type = arm.literal.get_type(resolver)
                lit_type_name = lit_ast_type.type_name if isinstance(lit_ast_type, t.BuiltinSpec) else None
                vi = next((i for i, v in enumerate(subj_type.types)
                           if isinstance(v, t.BuiltinSpec) and v.type_name == lit_type_name), None)
                if vi is None:
                    continue  # check() prevents this; skip to be safe
                tag_value = discriminators.get(subj_type.types[vi].as_unique_id_str(), 0)
                si, _ = variant_map[vi][0]
                slot_val = cg_p.StructField(sv, slot_fields[si][0])
                lit_bundle = arm.literal.generate(resolver).with_prefix(f"lit{em.counter}")
                em.arm(arm,
                       [[cg_p.IntEqConst(tag, tag_value)],
                        [literal_eq_test(lit_type_name, slot_val, lit_bundle.result_var)]],
                       pre=(lit_bundle,))

            elif isinstance(arm.type_spec, t.CombinationSpec):
                # Union-typed arm, e.g. `(w: Word|None)` over Word|None|IOError.
                # Discriminator ids are GLOBAL per leaf type, so each member's
                # tag test is the same constant it has in the wide union; the
                # bound value is the NARROWED representation rebuilt from the
                # wide slots (tags carry over unchanged for the same reason).
                narrow_ctype = arm.type_spec.generate(resolver)
                narrow_map = None
                if isinstance(narrow_ctype, cg_t.Struct):
                    _, narrow_map = cg_t.compute_union_slots(
                        [m.generate(resolver) for m in arm.type_spec.types])

                entries: list[tuple[cg_p.RParam, cg_p.RParam]] = []
                for k, member in enumerate(arm.type_spec.types):
                    uid = member.as_unique_id_str()
                    vi = variant_index(uid)
                    if vi is None or uid not in discriminators:
                        continue  # check() validated coverage; skip defensively
                    member_tag = discriminators[uid]
                    if narrow_map is None:
                        # DataPointer narrow union: NULL for the unit member,
                        # else the member's single pointer slot.
                        if member.generate(resolver) == cg_t.Struct(()):
                            value: cg_p.RParam = cg_p.NullPointer()
                        else:
                            wsi, _ = variant_map[vi][0]
                            value = cg_p.StructField(sv, slot_fields[wsi][0])
                    else:
                        fields = {"$tag": cg_p.Integer(member_tag, 32)}
                        for (nsi, _nt), (wsi, _wt) in zip(narrow_map[k], variant_map[vi]):
                            fields[narrow_ctype.fields[nsi][0]] = cg_p.StructField(sv, slot_fields[wsi][0])
                        value = cg_p.union_struct(narrow_ctype, fields)
                    entries.append((cg_p.IntEqConst(tag, member_tag), value))
                em.multi_entry_arm(arm, entries, narrow_ctype)

            else:
                arm_ctype = arm.type_spec.generate(resolver)
                tag_value = discriminators.get(arm.type_spec.as_unique_id_str(), 0)
                vi = next((i for i, vt in enumerate(variant_types) if vt == arm_ctype), None)
                bind = (em.bind_from_slots(arm, arm_ctype, variant_map[vi], slot_fields, sv)
                        if vi is not None else None)
                em.arm(arm, [[cg_p.IntEqConst(tag, tag_value)]], bind=bind)

        em.fallback(else_arm,
                    em.bind_subject(else_arm, subj_type, sv) if else_arm else None,
                    "tagged-union match fell through all arms")

    def box_value(self, value, source_type, resolver):
        """Box an already-generated value of `source_type` (a variant of this
        combination) into the tagged struct: fill the variant's slots and set
        $tag to the variant's global discriminator. Identity if the value is
        already the full union representation."""
        target_ctype = self.container
        inner_ctype = source_type.generate(resolver)
        if inner_ctype == target_ctype:
            return g.OperationBundle((), (), value)
        su = source_type.as_unique_id_str()
        variant_idx = next(i for i, v in enumerate(self.union_type.types)
                           if v.as_unique_id_str() == su)
        discriminators = resolver.get_discriminators()
        tag_value = discriminators.get(su, 0)
        slot_values = _variant_slots(value, inner_ctype,
                                     self.variant_map[variant_idx], target_ctype.fields)
        slot_values.append(("$tag", cg_p.Integer(tag_value, 32)))
        return g.OperationBundle((), (), cg_p.union_struct(target_ctype, dict(slot_values)))

    def read_field(self, base_value, field_name, resolver):
        """Read a field off a flat-enum value: locate the field's variant and
        primitive offset, then rebuild it from the union slots it occupies. A
        field spanning several primitives (a tuple field) reads each slot and
        re-packs them into the field's struct shape."""
        root_stmt = langtools.cast(
            s.EnumStatement, resolver.find_type(self.union_type.root_name)[0].statement)
        leaf_field_sets = t._collect_leaf_field_sets(root_stmt, [])
        container = self.container
        variant_map = self.variant_map

        def read_slot(si: int) -> cg_p.RParam:
            slot_name, _ = container.fields[si]
            return cg_p.StructField(base_value, slot_name)

        def reconstruct_from_slots(ftype, slot_assigns, off):
            if isinstance(ftype, cg_t.Struct):
                fvs = []
                for fname, ft in ftype.fields:
                    val, off = reconstruct_from_slots(ft, slot_assigns, off)
                    fvs.append((fname, val))
                return cg_p.NewStruct(tuple(fvs)), off
            si, _ = slot_assigns[off]
            return read_slot(si), off + 1

        for leaf_idx, leaf_fields in enumerate(leaf_field_sets):
            offset = 0
            for let in leaf_fields:
                field_type = let.declared_type.generate(resolver)
                n_prims = len(cg_t._flatten_primitives(field_type))
                if let.name == field_name:
                    slots_for_field = [variant_map[leaf_idx][offset + p] for p in range(n_prims)]
                    result_var, _ = reconstruct_from_slots(field_type, slots_for_field, 0)
                    return result_var
                offset += n_prims
        raise AssertionError(
            f"Field '{field_name}' not found in enum {self.union_type.root_name}")

    def construct_enum_value(self, leaf_name, field_args, resolver):
        """Construct a flat enum variant: fill its slots from the field-arg
        expressions (generated here, in field-arg order) and set $tag to the
        positional leaf index. `field_args` maps field name -> Expression."""
        root_stmt = resolver.find_type(self.union_type.root_name)[0].statement
        leaf_idx = self.union_type.all_leaf_names.index(leaf_name)
        leaf_fields = t._collect_leaf_field_sets(root_stmt, [])[leaf_idx]
        container = self.container
        variant_map = self.variant_map
        _, tag_slot_type = container.fields[-1]   # $tag is always last
        tag_const = cg_p.Integer(leaf_idx, tag_slot_type.precision)

        prim_start: dict[str, int] = {}
        offset = 0
        for let in leaf_fields:
            prim_start[let.name] = offset
            offset += len(cg_t._flatten_primitives(let.declared_type.generate(resolver)))

        slot_values = [(sname, cg_p.ZeroOf(stype)) for sname, stype in container.fields]
        tag_slot_idx = next(i for i, (n, _) in enumerate(container.fields) if n == "$tag")
        slot_values[tag_slot_idx] = ("$tag", tag_const)

        bundles = []
        for field_name, arg_expr in field_args.items():
            pi = prim_start[field_name]
            let = next(l for l in leaf_fields if l.name == field_name)
            field_type = let.declared_type.generate(resolver)
            arg_bundle = arg_expr.generate(resolver).with_prefix(f"arg_{field_name.split('@')[0]}")
            bundles.append(arg_bundle)

            def emit_flat(param, ftype, off):
                if isinstance(ftype, cg_t.Struct):
                    for fname, ft in ftype.fields:
                        off = emit_flat(cg_p.StructField(param, fname), ft, off)
                    return off
                si, _ = variant_map[leaf_idx][off]
                sname, _ = container.fields[si]
                slot_values[si] = (sname, param)
                return off + 1

            emit_flat(arg_bundle.result_var, field_type, pi)

        final_bundle = g.OperationBundle((), (), cg_p.union_struct(container, dict(slot_values)))
        if bundles:
            return reduce(lambda a, b: a + b, bundles + [final_bundle])
        return final_bundle

    def widen_from(self, src_repr, value, resolver):
        """Widen a narrower union value to this (strictly wider) tagged union.
        Each source variant is re-slotted into the target's slots and re-tagged
        with the same global discriminator (tags are global per leaf, so they
        carry over). The source is either a collapsed pointer union (null-check)
        or another tagged union (per-variant re-slot). Each path computes one
        tagged-union expression per predecessor edge; the join Phi collects them
        and codegen emits per-edge Moves into `result_var`."""
        target = self.union_type
        tgt_ctype = self.container
        tgt_variant_map = self.variant_map
        tgt_slot_fields = self.container.fields
        discriminators = resolver.get_discriminators()
        result_var = cg_p.StackVar(tgt_ctype, "wide_result")
        end_label = "wide_end"
        wide_results: list = []

        if isinstance(src_repr, PointerRepr):
            body = self._widen_from_pointer(
                value, src_repr.union_type, target, tgt_ctype, tgt_variant_map,
                tgt_slot_fields, discriminators, end_label, wide_results, resolver)
        else:
            assert isinstance(src_repr, TaggedRepr), \
                f"widen: source must be a pointer or tagged union, got {type(src_repr).__name__}"
            body = self._widen_from_tagged(
                value, src_repr, target, tgt_ctype, tgt_variant_map,
                tgt_slot_fields, discriminators, end_label, wide_results, resolver)

        join = g.OperationBundle(
            stack_vars=(result_var,),
            operations=(
                cg_o.Label(end_label),
                cg_o.Phi(target=result_var, sources=tuple(wide_results)),
            ),
            result_var=result_var)
        return reduce(lambda a, b: a + b, body + [join])

    def _widen_from_pointer(self, sv, source, target, tgt_ctype, tgt_variant_map,
                            tgt_slot_fields, discriminators, end_label, wide_results, resolver):
        """Widen a DataPointer union (null = unit/None, non-null = pointer variant)
        to this tagged-union Struct. The non-null pointer path and the null path
        each contribute a single tagged-union expression to the Phi."""
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

    def _widen_from_tagged(self, sv, src_repr, target, tgt_ctype, tgt_variant_map,
                           tgt_slot_fields, discriminators, end_label, wide_results, resolver):
        """Widen a tagged-union Struct to this wider tagged-union Struct by
        re-slotting each variant. One arm per source variant, each contributing
        its tagged-union expression to `wide_results`."""
        source = src_repr.union_type
        src_ctype = src_repr.container
        src_variant_map = src_repr.variant_map
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


@dataclasses.dataclass(frozen=True)
class PointerRepr(UnionRepr):
    union_type: t.TypeSpec

    def ctype(self) -> cg_t.Type:
        return cg_t.DataPointer()

    def generate_match(self, em, subj_bundle, arms, else_arm, resolver):
        """DataPointer union dispatch: sv==NULL → the None arm; typed arms test
        vtable identity / pointer tag bits via ObjVtableEq (member_guard);
        literal arms test kind then value; at most one foreign class acts as the
        implicit fallback (untestable from generated code)."""
        subj_type = self.union_type
        unit_type = cg_t.Struct(())
        sv = subj_bundle.result_var
        subj_has_none = any(v.generate(resolver) == unit_type for v in subj_type.types)

        def member_guard(member: t.TypeSpec) -> cg_p.RParam | None:
            kind = _pointer_word_kind(member, resolver)
            if kind == ('INT',):
                return cg_p.ObjVtableEq(sv, extern_symbol="INTEGER_VTABLE")
            if kind == ('STR',):
                return cg_p.ObjVtableEq(sv, extern_symbol="STRING_VTABLE")
            if kind is not None and kind[0] in ('CLASS', 'ENUM'):
                return cg_p.ObjVtableEq(sv, class_name=kind[1])
            return None  # FOREIGN (fallback) / UNIT / non-pointer-word

        # Classify the arms, preserving source order for the guarded ones.
        null_arm = None
        foreign_fallback = None
        guarded = []
        union_arm_covers_none = False
        for arm in arms:
            if arm.literal is not None:
                guarded.append(arm)
            elif arm.type_spec is None:
                pass  # else arm: the fallback, handled at the end
            elif arm.type_spec.generate(resolver) == unit_type:
                null_arm = arm
            elif isinstance(arm.type_spec, t.ClassSpec) and _classspec_is_foreign(arm.type_spec, resolver):
                foreign_fallback = arm
            else:
                if isinstance(arm.type_spec, t.CombinationSpec) and any(
                        m.generate(resolver) == unit_type for m in arm.type_spec.types):
                    union_arm_covers_none = True
                guarded.append(arm)

        # NULL routes to: an explicit None arm; else a union arm covering None
        # (its own null guard, in source order); else the else arm when the
        # subject can be None at all.
        null_target = (null_arm if null_arm is not None
                       else (else_arm if subj_has_none and not union_arm_covers_none else None))
        if null_target is not None:
            em.arm(null_target, [[cg_p.IntEqConst(sv, 0)]],
                   bind=em.bind_subject(null_target,
                                        null_target.type_spec or subj_type, sv))

        for arm in guarded:
            if arm.literal is not None:
                self._pointer_literal_arm(em, arm, sv, resolver)
            elif isinstance(arm.type_spec, t.CombinationSpec):
                guards = []
                for member in arm.type_spec.types:
                    if member.generate(resolver) == unit_type:
                        guards.append(cg_p.IntEqConst(sv, 0))
                    else:
                        guard = member_guard(member)
                        if guard is not None:
                            guards.append(guard)
                em.arm(arm, [guards], bind=em.bind_subject(arm, arm.type_spec, sv))
            else:
                guard = member_guard(arm.type_spec)
                if guard is None:
                    continue  # untestable arm kind; check() rejects these
                em.arm(arm, [[guard]], bind=em.bind_subject(arm, arm.type_spec, sv))

        final_fallback = foreign_fallback if foreign_fallback is not None else else_arm
        em.fallback(final_fallback,
                    em.bind_subject(final_fallback,
                                    final_fallback.type_spec or subj_type, sv)
                    if final_fallback else None,
                    "pointer-union match fell through all arms")

    def _pointer_literal_arm(self, em, arm, sv, resolver):
        lit_ast_type = arm.literal.get_type(resolver)
        if not isinstance(lit_ast_type, t.BuiltinSpec):
            return  # unreachable — check() already validated
        if lit_ast_type.type_name == "str":
            kind_guard = cg_p.ObjVtableEq(sv, extern_symbol="STRING_VTABLE")
        elif lit_ast_type.type_name == "bigint":
            kind_guard = cg_p.ObjVtableEq(sv, extern_symbol="INTEGER_VTABLE")
        else:
            return  # unreachable — check() already validated
        lit_bundle = arm.literal.generate(resolver).with_prefix(f"lit{em.counter}")
        value_test = literal_eq_test(lit_ast_type.type_name, sv, lit_bundle.result_var)
        em.arm(arm, [[kind_guard], [value_test]], pre=(lit_bundle,))

    def box_value(self, value, source_type, resolver):
        """Box an already-generated value of `source_type` (a variant of this
        union) into the collapsed pointer word: None/unit -> NULL, a single-field
        newtype -> its bare pointer, an already-DataPointer value -> itself."""
        inner_ctype = source_type.generate(resolver)
        if inner_ctype == cg_t.Struct(()):  # unit / None variant
            return g.OperationBundle((), (), cg_p.NullPointer())
        return g.OperationBundle((), (), _unwrap_to_pointer_word(value, inner_ctype))

    def widen_from(self, src_repr, value, resolver):
        """Widen to a collapsed pointer union: both unions share the same
        tag-bit pointer encoding and every source variant is a target variant
        with identical pointer repr, so the value passes through unchanged."""
        assert isinstance(src_repr, PointerRepr), \
            f"widen: DataPointer target requires a DataPointer source, got {type(src_repr).__name__}"
        return g.OperationBundle((), (), value)


@dataclasses.dataclass(frozen=True)
class ComplexEnumRepr(UnionRepr):
    union_type: t.TypeSpec

    def ctype(self) -> cg_t.Type:
        return cg_t.DataPointer()

    def generate_match(self, em, subj_bundle, arms, else_arm, resolver):
        # Each variant carries its own vtable; the guard compares
        # vtable.discriminator against the leaf's global registry id.
        subj_type = self.union_type
        sv = subj_bundle.result_var
        tag = cg_p.VtableDiscriminator(sv)
        discriminators = resolver.get_discriminators()
        def leaf_id(leaf: str) -> int:
            key = f"enumleaf({t.enum_leaf_object_name(subj_type.root_name, leaf)})"
            assert key in discriminators, f"no discriminator for {key!r}"
            return discriminators[key]
        for arm in (a for a in arms if a.type_spec is not None):
            arm_type = arm.type_spec
            assert isinstance(arm_type, t.EnumSpec)
            guards = [cg_p.IntEqConst(tag, leaf_id(leaf))
                      for leaf in sorted(arm_type.valid_leaf_names, key=leaf_id)]
            em.arm(arm, [guards], bind=em.bind_subject(arm, subj_type, sv))
        em.fallback(else_arm,
                    em.bind_subject(else_arm, subj_type, sv) if else_arm else None,
                    "enum match fell through all arms")

    def read_field(self, base_value, field_name, resolver):
        """Read a field off a complex-enum value. Field names are @hash-unique
        to one variant, so the field lives under its own name on the heap object
        of the variant whose declaration carries it."""
        root_stmt = langtools.cast(
            s.EnumStatement, resolver.find_type(self.union_type.root_name)[0].statement)
        leaf_field_sets = t._collect_leaf_field_sets(root_stmt, [])
        for leaf_name, leaf_fields in zip(self.union_type.all_leaf_names, leaf_field_sets):
            for let in leaf_fields:
                if let.name == field_name:
                    ftype = let.declared_type.generate(resolver)
                    obj_name = t.enum_leaf_object_name(self.union_type.root_name, leaf_name)
                    return cg_p.ObjectField(ftype, base_value, obj_name, let.name, None)
        raise AssertionError(
            f"Field '{field_name}' not found in enum {self.union_type.root_name}")

    def construct_enum_value(self, leaf_name, field_args, resolver):
        """Construct a complex enum variant: allocate the variant's own heap
        object (its vtable carries the discriminator) and store each field.
        Unwritten fields get ZeroOf so staticinit can promote all-constant
        constructions to static singletons. `field_args` maps name -> Expression."""
        root_stmt = resolver.find_type(self.union_type.root_name)[0].statement
        leaf_idx = self.union_type.all_leaf_names.index(leaf_name)
        leaf_fields = t._collect_leaf_field_sets(root_stmt, [])[leaf_idx]
        obj_name = t.enum_leaf_object_name(self.union_type.root_name, leaf_name)
        result_var = cg_p.StackVar(cg_t.DataPointer(), "result")
        ops = [cg_o.NewObject(obj_name, result_var)]
        bundles = []
        for let in leaf_fields:
            field_name = let.name
            field_type = let.declared_type.generate(resolver)
            if field_name in field_args:
                arg_bundle = field_args[field_name].generate(resolver).with_prefix(
                    f"arg_{field_name.split('@')[0]}")
                bundles.append(arg_bundle)
                source = arg_bundle.result_var
            else:
                source = cg_p.ZeroOf(field_type)
            ops.append(cg_o.Move(
                cg_p.ObjectField(field_type, result_var, obj_name, field_name, None), source))
        ctor_bundle = g.OperationBundle(stack_vars=(result_var,),
                                        operations=tuple(ops), result_var=result_var)
        if bundles:
            return reduce(lambda a, b: a + b, bundles + [ctor_bundle])
        return ctor_bundle


def classify(union_type: t.TypeSpec, resolver: g.Resolver) -> UnionRepr:
    """Decide a union's representation. The single source of truth that the
    `*.generate` decision and the per-site representation branches route through."""
    if isinstance(union_type, t.EnumSpec):
        if union_type.is_complex:
            return ComplexEnumRepr(union_type)
        # Flat enum -> tagged struct over its variants, with the rare fallback
        # (the root name doesn't resolve to a single EnumStatement) preserved
        # exactly from the old EnumSpec.generate.
        types = resolver.find_type(union_type.root_name)
        if len(types) == 1 and isinstance(types[0].statement, s.EnumStatement):
            stmt = langtools.cast(s.EnumStatement, types[0].statement)
            container, vmap = cg_t.compute_union_slots(t.enum_variant_types(stmt, resolver))
            return TaggedRepr(union_type, container, vmap)
        container = cg_t.Struct(tuple((name, ftype.generate(resolver))
                                      for name, ftype in union_type.all_fields))
        return TaggedRepr(union_type, container, ())

    if isinstance(union_type, t.CombinationSpec):
        if _union_collapses_to_pointer(list(union_type.types), resolver):
            return PointerRepr(union_type)
        variant_types = [v.generate(resolver) for v in union_type.types]
        container, vmap = cg_t.compute_union_slots(variant_types)
        return TaggedRepr(union_type, container, vmap)

    raise TypeError(f"classify: not a union type: {type(union_type).__name__}")
