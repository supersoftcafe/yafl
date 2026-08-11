"""TypeId — a type's identity reified as a dedicated value type.

The identity-vs-state ruling: a type's identity is its NAME plus ALL its
type arguments, recursively — never its descriptive state (fields, leaves,
resolution snapshots). A TypeId is that identity as a plain immutable
value: structurally hashable, totally ordered by its serialisation, and
safe as a dict key precisely because there is no state on it to go stale.

Two builders:

    spelling_of(spec)   TOTAL — every spec gets a spelling, including the
                        incomplete arms (unbound placeholders, raw named
                        spellings). Key sites that sit behind the mono
                        concreteness gate key by this (where it coincides
                        with identity_of), as do defensive orderings (the
                        instantiation sort's tie-break).
    identity_of(spec)   PARTIAL — the ruling's identityOf: None for any
                        spec that cannot name an instantiation (a
                        placeholder or unresolved name anywhere inside).
                        The contract for any future UNGATED key site:
                        None means structurally unusable as a key.

serialise(tid) is the canonical spelling. The bootstrap port mirrors this
module exactly (bootstrap/ast/identity.yafl); the spelling formats are
load-bearing for whole-compiler byte-identity — the instantiation sort
orders by them.
"""
from __future__ import annotations

from dataclasses import dataclass

import pyast.typespec as t


@dataclass(frozen=True)
class TypeId:
    """Abstract base. Every arm is complete, immutable and hashable."""


@dataclass(frozen=True)
class NoneId(TypeId):
    """An absent spec position: no result type, an untyped tuple entry."""


@dataclass(frozen=True)
class BuiltinId(TypeId):
    name: str


@dataclass(frozen=True)
class NamedId(TypeId):
    """A raw source spelling that never resolved — never part of an identity."""
    name: str
    args: tuple[TypeId, ...]


@dataclass(frozen=True)
class ClassId(TypeId):
    name: str
    args: tuple[TypeId, ...]


@dataclass(frozen=True)
class EnumId(TypeId):
    root: str
    args: tuple[TypeId, ...]


@dataclass(frozen=True)
class TupleId(TypeId):
    entries: tuple[tuple[str, TypeId], ...]  # entry name, "" when unnamed


@dataclass(frozen=True)
class CallableId(TypeId):
    params: TypeId
    result: TypeId


@dataclass(frozen=True)
class UnionId(TypeId):
    members: tuple[TypeId, ...]  # sorted by serialisation at build time


@dataclass(frozen=True)
class PlaceholderId(TypeId):
    """An unbound generic parameter — never part of an identity."""
    name: str


@dataclass(frozen=True)
class LazyId(TypeId):
    target: TypeId


@dataclass(frozen=True)
class ArrayId(TypeId):
    element: TypeId
    length_field: str


def spelling_of(spec) -> TypeId:
    """The TOTAL spelling of a spec (or None) as a TypeId."""
    if spec is None:
        return NoneId()
    if isinstance(spec, t.BuiltinSpec):
        return BuiltinId(spec.type_name)
    if isinstance(spec, t.NamedSpec):
        return NamedId(spec.name, tuple(spelling_of(p) for p in spec.type_params))
    if isinstance(spec, t.ClassSpec):
        return ClassId(spec.name, tuple(spelling_of(p) for p in spec.type_params))
    if isinstance(spec, t.EnumSpec):
        return EnumId(spec.root_name, tuple(spelling_of(p) for p in spec.type_params))
    if isinstance(spec, t.TupleSpec):
        return TupleId(tuple((en.name or "", spelling_of(en.type)) for en in spec.entries))
    if isinstance(spec, t.CallableSpec):
        return CallableId(spelling_of(spec.parameters), spelling_of(spec.result))
    if isinstance(spec, t.CombinationSpec):
        return UnionId(tuple(sorted((spelling_of(m) for m in spec.types), key=serialise)))
    if isinstance(spec, t.GenericPlaceholderSpec):
        return PlaceholderId(spec.name)
    if isinstance(spec, t.LazyStubSpec):
        return LazyId(spelling_of(spec.target_type))
    if isinstance(spec, t.ArrayFieldSpec):
        return ArrayId(spelling_of(spec.element), spec.length_field)
    raise TypeError(f"no TypeId spelling for {type(spec).__name__}")


def serialise(tid: TypeId) -> str:
    """The canonical string form of a TypeId. Injective; total order by <."""
    if isinstance(tid, NoneId):
        return "_"
    if isinstance(tid, BuiltinId):
        return f"B({tid.name})"
    if isinstance(tid, NamedId):
        return f"N({tid.name};{','.join(serialise(a) for a in tid.args)})"
    if isinstance(tid, ClassId):
        return f"C({tid.name};{','.join(serialise(a) for a in tid.args)})"
    if isinstance(tid, EnumId):
        return f"E({tid.root};{','.join(serialise(a) for a in tid.args)})"
    if isinstance(tid, TupleId):
        return "T(" + ",".join(f"{n}:{serialise(a)}" for n, a in tid.entries) + ")"
    if isinstance(tid, CallableId):
        return f"F({serialise(tid.params)};{serialise(tid.result)})"
    if isinstance(tid, UnionId):
        return "U(" + "|".join(serialise(m) for m in tid.members) + ")"
    if isinstance(tid, PlaceholderId):
        return f"G({tid.name})"
    if isinstance(tid, LazyId):
        return f"L({serialise(tid.target)})"
    if isinstance(tid, ArrayId):
        return f"A({serialise(tid.element)};{tid.length_field})"
    raise TypeError(f"unknown TypeId arm {type(tid).__name__}")


def __is_complete(tid: TypeId) -> bool:
    if isinstance(tid, (PlaceholderId, NamedId)):
        return False
    if isinstance(tid, (ClassId, EnumId)):
        return all(__is_complete(a) for a in tid.args)
    if isinstance(tid, TupleId):
        return all(__is_complete(a) for _, a in tid.entries)
    if isinstance(tid, CallableId):
        return __is_complete(tid.params) and __is_complete(tid.result)
    if isinstance(tid, UnionId):
        return all(__is_complete(m) for m in tid.members)
    if isinstance(tid, LazyId):
        return __is_complete(tid.target)
    if isinstance(tid, ArrayId):
        return __is_complete(tid.element)
    return True  # NoneId, BuiltinId


def identity_of(spec) -> TypeId | None:
    """The ruling's identityOf: a spec's identity, or None when the spec is
    incomplete and therefore structurally unusable as a key."""
    tid = spelling_of(spec)
    return tid if __is_complete(tid) else None
