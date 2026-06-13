from __future__ import annotations

import pyast.statement as s
import pyast.typespec as t
import pyast.resolver as g


def collect_discriminator_ids(statements: list[s.Statement]) -> dict[str, int]:
    """Walk all compiled statements and assign globally unique integer discriminator IDs
    to every type that appears as a variant inside a CombinationSpec.

    Key   = type.as_unique_id_str()  (structural, order-independent for unions)
    Value = globally unique integer, assigned in encounter order

    The registry is used at match-expression codegen time to compare the runtime
    discriminator field against a known constant.  It is stable within a compilation
    unit; cross-unit stability is not required because yafl is whole-program compiled.

    COMPLEX-ENUM LEAVES get ids too, keyed `enumleaf(<leaf root name>)`: each
    variant of a heap-allocated enum carries its own vtable whose
    `.discriminator` holds this id, and enum match dispatch compares against
    it — the discriminant lives once per TYPE instead of a tag byte in every
    object. IDs start at 1: 0 is the vtable-field default, reserved for
    "never dispatched on".
    """
    ids: dict[str, int] = {}

    def assign(uid: str | None) -> None:
        if uid is not None and uid not in ids:
            ids[uid] = len(ids) + 1

    def visit(_, thing):
        if isinstance(thing, t.CombinationSpec):
            for variant in thing.types:
                assign(variant.as_unique_id_str())
        return thing

    resolver = g.ResolverRoot(statements)
    # Enum leaves first, taken from the root enum STATEMENTS in statement
    # order: each root's _enum_spec is authoritative (spec copies reachable
    # by the tree walk can carry stale `is_complex` flags).
    for stmt in statements:
        if isinstance(stmt, s.EnumStatement) and stmt._root_name == stmt.name \
                and stmt._enum_spec is not None and stmt._enum_spec.is_complex:
            for leaf in stmt._enum_spec.all_leaf_names:
                assign(f"enumleaf({t.enum_leaf_object_name(stmt.name, leaf)})")
    for stmt in statements:
        stmt.search_and_replace(resolver, visit)

    return ids
