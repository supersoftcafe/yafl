"""all_fields as DERIVED state — the per-pass provider.

Identity vs state (user ruling 2026-08-08): an enum spec's identity is its
name (plus type parameters when complete); all_fields is state, derived from
the enum's STATEMENT as it currently stands, never stored. A reader that
derives from the current statement cannot see a stale copy — the probe that
gated this design caught stored copies disagreeing among THEMSELVES at
nested resolution depths on recursive enums.

Each pass builds its provider at entry (the registry is the pass's own
statements) and the memoize cache dies with the pass — the same scoping as
every other per-pass cache, mirrored in the port by a ctx-carried
System::memoize closure.

A root with no statement (a stale reference to a PRUNED generic) derives
EMPTY fields: such a spec is only ever used as a pointer (complex_enums
marks it complex unconditionally); its layout is never asked for.
"""
from __future__ import annotations

from typing import Callable

import pyast.statement as s
import pyast.typespec as t
from memoize import memoize

FieldsOf = Callable[[str], "tuple[tuple[str, t.TypeSpec], ...]"]


def enum_registry(statements: list) -> dict[str, "s.EnumStatement"]:
    """Root name -> root EnumStatement, for every enum in this pass's world."""
    reg: dict[str, s.EnumStatement] = {}
    for stmt in statements:
        if isinstance(stmt, s.EnumStatement) and stmt._root_name == stmt.name:
            reg.setdefault(stmt.name, stmt)
    return reg


def fields_provider(statements: list) -> FieldsOf:
    reg = enum_registry(statements)
    return memoize(lambda root: reg[root].derive_all_fields()
                                if root in reg else ())
