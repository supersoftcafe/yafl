"""The type system, split representation vs algorithm:

    specs.py    the TypeSpec dataclasses — what a type IS
    algebra.py  meet / refine / unify / substitute / solve — what you DO with types

`import pyast.typespec as t` exposes the same flat surface as the former single
module. The underscore names re-exported here (`_CONFLICT`,
`_collect_leaf_field_sets`) have external callers (`meet`'s conflict marker,
which the spec tests and the bootstrap spec harness compare against; enum
codegen in statement.py).
"""
from __future__ import annotations

from pyast.typespec.specs import (
    TypeSpec, BuiltinSpec, Bool, CallableSpec, ClassSpec, CombinationSpec,
    EnumSpec, GenericPlaceholderSpec, LazyStubSpec, ArrayFieldSpec, NamedSpec,
    TupleEntrySpec, TupleSpec,
    collect_enum_leaves, enum_variant_types, enum_leaf_object_name,
    trivially_assignable_equals, bind_tuple_entries, default_value_errors,
    _collect_leaf_field_sets, _flatten_union_members,
)
from pyast.typespec.algebra import (
    substitute_placeholders, placeholder_names_in, has_free_placeholders,
    resolves_in_scope, with_opaque_placeholders, scoped_unique_id, is_narrowed_view, contains_narrowed_view,
    meet, join, converge, branch_type, refine, refine_widening, unify_generic,
    bind_from_constraint_match, TraitInstance, solve_trait_constraint,
    _CONFLICT,
)
