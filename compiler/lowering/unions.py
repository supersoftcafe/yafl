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
    """
    ids: dict[str, int] = {}

    def visit(_, thing):
        if isinstance(thing, t.CombinationSpec):
            for variant in thing.types:
                uid = variant.as_unique_id_str()
                if uid is not None and uid not in ids:
                    ids[uid] = len(ids)
        return thing

    resolver = g.ResolverRoot(statements)
    for stmt in statements:
        stmt.search_and_replace(resolver, visit)

    return ids
