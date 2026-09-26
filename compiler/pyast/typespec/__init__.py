"""The type system, split representation vs algorithm:

    specs.py    the TypeSpec dataclasses — what a type IS
    algebra.py  merge / refine / substitute / solve — what you DO with types

`import pyast.typespec as t` exposes the same flat surface as the former single
module. The underscore name re-exported here (`_collect_leaf_field_sets`) has
an external caller (enum codegen in statement.py).
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
    substitute_placeholders, placeholder_names_in, has_free_placeholders, has_missing_arguments,
    resolves_in_scope, with_opaque_placeholders, scoped_unique_id, is_narrowed_view, contains_narrowed_view,
    merge, receives, pattern_binding, join, converge, branch_type, refine, refine_widening,
    without_callable_params,
    bind_from_constraint_match, TraitInstance, solve_trait_constraint,
)
