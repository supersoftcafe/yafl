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
        # The inner compiles with NO expected type: it is the raw source value —
        # this node is the adapter to the receiver, and feeding the receiver's
        # type back down would make the inner wrap itself again. Safe because a
        # wrap is only ever inserted over ground types (needs_conversion), so
        # the inner's names are already committed.
        inner, stmts = self.inner.compile(resolver, None)
        target, spec_stmts = self.target.compile(resolver)
        # The receiver's view wins: a ground expected that differs from our
        # target means the receiver WIDENED since this wrap was inserted
        # (inference only ever widens) — retarget to it.
        if (expected_type is not None and expected_type.is_concrete()
                and expected_type.as_unique_id_str() is not None
                and expected_type.as_unique_id_str() != target.as_unique_id_str()):
            target = expected_type
        # Dissolve when no conversion remains (the inner reached the target
        # itself, or a retarget made the wrap moot). Idempotent at fixpoint:
        # the parent's own `converted` re-wraps only if needs_conversion says
        # so, which is exactly the kept case.
        if not needs_conversion(inner.get_type(resolver), target, resolver):
            return inner, stmts + spec_stmts
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
    def class_structural_tuple(v: "t.TypeSpec") -> "t.TypeSpec | None":
        # A [final] class member is REPRESENTED structurally in unions; a
        # tuple-typed value (e.g. the class's own inlined construction, whose
        # type has become the field tuple) must box AS that class member.
        if not isinstance(v, t.ClassSpec):
            return None
        found = resolver.find_type(v.name)
        if len(found) != 1 or not isinstance(found[0].statement, s.ClassStatement):
            return None
        stmt = found[0].statement
        if "final" not in stmt.attributes:
            return None
        return stmt.parameters.get_type()

    matching = []
    for v in target.repr_members():
        if isinstance(v, t.TupleSpec) and v.trivially_assignable_from(resolver, source) is True:
            matching.append(v)
            continue
        struct = class_structural_tuple(v)
        if (isinstance(struct, t.TupleSpec)
                and struct.trivially_assignable_from(resolver, source) is True):
            matching.append(v)
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
    if su is None or tu is None:
        return False
    # Tuple-into-tuple is decided by the field BINDING, before the id shortcut
    # below: a pure name-directed reorder has identical ids on both sides
    # (`as_unique_id_str` is positional types only) yet must rebuild the value.
    if isinstance(target, t.TupleSpec) and isinstance(source, t.TupleSpec):
        # 1-tuple WRAP first: when the target is a one-entry tuple whose entry
        # the SOURCE-AS-A-WHOLE fits (it IS the entry type, or it is a member
        # tuple of the entry's union — e.g. a simple-class's structural tuple
        # into `(t: E3|W)` after simple_classes rewrote W to its field tuple),
        # the conversion is wrap(+box), not an entry-wise rebind.
        if len(target.entries) == 1 and target.entries[0].type is not None:
            ety = target.entries[0].type
            eu = ety.as_unique_id_str()
            if eu is not None:
                if eu == su:
                    return True
                if (isinstance(ety, t.CombinationSpec)
                        and matching_tuple_variant(source, ety, resolver) is not None):
                    return True
        binding = t.bind_tuple_entries(target.entries, [en.name for en in source.entries])
        if binding is None:
            return False    # not assignable — the receiver reports that, not us
        if binding != list(range(len(target.entries))):
            return True     # reorder and/or default fill
        return su != tu and any(needs_conversion(s_e.type, t_e.type, resolver)
                                for s_e, t_e in zip(source.entries, target.entries))
    if su == tu:
        return False
    if isinstance(target, t.TupleSpec):
        # A 1-tuple and its element are one TYPE with two REPRESENTATIONS
        # (the tuple is a one-field struct): a non-tuple source must WRAP.
        # Wider tuples with a non-tuple source are not assignable at all —
        # the receiver reports that, not us.
        return len(target.entries) == 1
    if isinstance(target, t.CombinationSpec):
        if isinstance(source, t.TupleSpec):
            if matching_tuple_variant(source, target, resolver) is not None:
                return True
            # A 1-tuple that is a genuine WRAPPER of a union value (its
            # entry id equals the target's) unwraps to its element first.
            if len(source.entries) == 1 and source.entries[0].type is not None:
                return source.entries[0].type.as_unique_id_str() == tu
            return False
        if isinstance(source, t.CombinationSpec):
            # Distinct union ids ⇒ widening/re-slotting — but only a genuine
            # WIDENING (every source member assignable into the target) is a
            # conversion. Anything else must NOT wrap: a ConvertExpression's
            # get_type reports the TARGET, which would hide the mismatch from
            # the receiver's own check forever — a declared
            # `(ls: List<String>, n: Int)|None` silently accepted a returned
            # `List<String>|None` this way. Not assignable — the receiver
            # reports that, not us (test_union_return_shape).
            return t.trivially_assignable_equals(resolver, target, source) is True
        return any(v.as_unique_id_str() == su for v in target.repr_members())
    if (isinstance(source, t.TupleSpec) and len(source.entries) == 1
            and source.entries[0].type is not None
            and source.entries[0].type.as_unique_id_str() == tu):
        return True         # a genuine 1-tuple WRAPPER of the target: UNWRAP
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

    # Tuple-into-tuple before the same-id shortcut: a pure reorder has equal
    # ids (positional types only) but still rebuilds the value.
    if isinstance(target, t.TupleSpec):
        if isinstance(source, t.TupleSpec):
            if len(target.entries) == 1 and target.entries[0].type is not None:
                ety = target.entries[0].type
                eu = ety.as_unique_id_str()
                whole_fits = eu is not None and (
                    eu == source.as_unique_id_str()
                    or (isinstance(ety, t.CombinationSpec)
                        and matching_tuple_variant(source, ety, resolver) is not None))
                if whole_fits:
                    inner = emit_conversion(value, source, ety, resolver)
                    return inner + g.OperationBundle((), (),
                        cg_p.NewStruct((("_0", inner.result_var),)))
            return _convert_tuple(value, source, target, resolver)
        if len(target.entries) == 1:
            # Wrap a bare element into its 1-tuple: convert to the entry's
            # type first (the element may itself need union boxing).
            inner = emit_conversion(value, source, target.entries[0].type, resolver)
            return inner + g.OperationBundle((), (),
                cg_p.NewStruct((("_0", inner.result_var),)))
        return _passthrough(value)

    su = source.as_unique_id_str()
    if su is not None and su == target.as_unique_id_str():
        return _passthrough(value)  # same representation — nothing to do

    if isinstance(target, t.CombinationSpec):
        if isinstance(source, t.TupleSpec):
            if matching_tuple_variant(source, target, resolver) is not None:
                return _tuple_into_union(value, source, target, resolver)
            if (len(source.entries) == 1 and source.entries[0].type is not None
                    and source.entries[0].type.as_unique_id_str() == target.as_unique_id_str()):
                inner = cg_p.StructField(value, "_0")
                return emit_conversion(inner, source.entries[0].type, target, resolver)
            return _tuple_into_union(value, source, target, resolver)
        if isinstance(source, t.CombinationSpec):
            # The target union's repr owns the widening (re-slot / null-check),
            # given the source repr.
            return union_repr.classify(target, resolver).widen_from(
                union_repr.classify(source, resolver), value, resolver)
        return _pack_variant(value, source, target, resolver)

    if isinstance(source, t.TupleSpec) and len(source.entries) == 1:
        # 1-tuple into a bare element slot: read the single field and convert
        # the element the rest of the way.
        inner = cg_p.StructField(value, "_0")
        return emit_conversion(inner, source.entries[0].type, target, resolver)

    return _passthrough(value)


# ---------------------------------------------------------------------------
# Tuple → wider tuple / tuple → union containing a tuple variant
# ---------------------------------------------------------------------------

def _convert_tuple(value, source: t.TupleSpec, target: t.TupleSpec,
                  resolver: g.Resolver) -> g.OperationBundle:
    """Rebuild a tuple value as the target tuple: each source field lands in
    the target field it BINDS (positional, or by name), coerced to that field's
    type; an unbound target field materialises its declared default. The
    binding is the same one needs_conversion consulted, so a pass-through here
    means the shapes already agree exactly."""
    binding = t.bind_tuple_entries(target.entries, [en.name for en in source.entries])
    if binding is None:
        return _passthrough(value)
    identity = (binding == list(range(len(target.entries))))
    if identity and source.as_unique_id_str() == target.as_unique_id_str():
        return _passthrough(value)
    bundle = g.OperationBundle()
    field_values: list[tuple[str, cg_p.RParam]] = []
    for i, (t_entry, b) in enumerate(zip(target.entries, binding)):
        if b is not None:
            cb = emit_conversion(cg_p.StructField(value, f"_{b}"), source.entries[b].type,
                        t_entry.type, resolver).with_prefix(f"f{i}")
        else:
            # Default fill: a literal or [const] reference (enforced at the
            # declaration), so generating it here is pure and order-free.
            db = t_entry.default.generate(resolver)
            cb = (db + emit_conversion(db.result_var, t_entry.default.get_type(resolver),
                        t_entry.type, resolver)).with_prefix(f"f{i}")
        bundle = bundle + cb
        field_values.append((f"_{i}", cb.result_var))
    return bundle + g.OperationBundle((), (), cg_p.NewStruct(tuple(field_values)))


def _tuple_into_union(value, source: t.TupleSpec, target: t.CombinationSpec,
                      resolver: g.Resolver) -> g.OperationBundle:
    """Box a tuple value into a union that contains a single matching tuple
    variant (matching_tuple_variant — the shared match). No match is a
    pass-through, as in the old `__box_tuple_into_union`."""
    variant = matching_tuple_variant(source, target, resolver)
    if variant is None:
        return _passthrough(value)
    if isinstance(variant, t.ClassSpec):
        # A [final] class member matched structurally: the tuple value IS the
        # class's in-union representation already — pack it under the class's
        # identity (its discriminator), no inner rebuild.
        return _pack_variant(value, variant, target, resolver)
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
