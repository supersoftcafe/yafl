"""Erase tuple field names: every name becomes the position it meant.

A tuple is positional. A field name is sugar for the program as written — it
picks a field in a read (`st.acc`) and directs a binding (`(acc = 1, cur = 2)`
into `(cur: Int, acc: Int)`) — and means nothing to generics or to generated
code. Once the program has converged and been checked, every such use has an
answer, so this pass writes the answers into the tree and removes the names:

  1. a tuple field read takes its POSITION (`DotExpression.index`);
  2. a conversion that binds a tuple's fields by name — a reorder, a default
     filled in — is rebuilt as the tuple it produces, field by field, so what
     is left of the conversion is positional;
  3. every tuple type and tuple value in the program loses its field names.

It runs once, immediately before monomorphisation. From there on a tuple has
no field names for anything to consult: the instances of a generic are shared
by call sites that named their tuples differently, and it no longer matters.
What stays named is a PARAMETER LIST — a function's or constructor's — whose
names are the declaration's own.
"""
from __future__ import annotations

import dataclasses

import pyast.expression as e
import pyast.resolver as g
import pyast.rewrite as rw
import pyast.statement as s
import pyast.typespec as t
from pyast.expression.conversion import matching_tuple_variant


def erase_field_names(statements: list[s.Statement]) -> list[s.Statement]:
    resolver = g.ResolverRoot(statements)
    positioned = [rw.resolved(stmt.search_and_replace(resolver, __by_position), stmt)
                  for stmt in statements]
    return [rw.resolved(stmt.search_and_replace(resolver, __unnamed), stmt)
            for stmt in positioned]


# ── 1 and 2: names become positions, while the names can still be read ───────

def __by_position(resolver: g.Resolver, thing):
    if isinstance(thing, e.DotExpression) and thing.index is None:
        btype = thing.base.get_type(resolver)
        if isinstance(btype, t.TupleSpec):
            found = thing.tuple_entry(btype.entries)
            if found is None:
                raise ValueError(f"compiler bug: tuple field read `.{thing.name}` at "
                                 f"{thing.line_ref} names no field of its tuple")
            return dataclasses.replace(thing, index=found[0])
    if isinstance(thing, e.ConvertExpression):
        rebuilt = __bound_by_position(thing.inner, thing.inner.get_type(resolver), thing.target,
                                      resolver, "")
        if rebuilt is not None:
            return dataclasses.replace(thing, inner=rebuilt)
    return rw.UNCHANGED


def __bound_tuple(source: t.TypeSpec | None, target: t.TypeSpec | None,
                  resolver: g.Resolver) -> t.TupleSpec | None:
    """The tuple inside `target` that a `source` tuple's fields bind to, the
    way the conversion engine finds it: the target itself, the tuple variant
    of a union target, or either of those inside a one-field wrapper."""
    if not isinstance(source, t.TupleSpec):
        return None
    if isinstance(target, t.CombinationSpec):
        variant = matching_tuple_variant(source, target, resolver)
        return variant if isinstance(variant, t.TupleSpec) else None
    if not isinstance(target, t.TupleSpec):
        return None
    if len(target.entries) == 1 and target.entries[0].type is not None:
        wrapped = target.entries[0].type
        su, wu = source.as_unique_id_str(), wrapped.as_unique_id_str()
        if su is not None and su == wu:
            return None             # the whole source IS the one field
        if isinstance(wrapped, t.CombinationSpec):
            inside = __bound_tuple(source, wrapped, resolver)
            if inside is not None:
                return inside
    return target


def __bound_by_position(expr: e.Expression, source: t.TypeSpec | None, target: t.TypeSpec | None,
                        resolver: g.Resolver, path: str) -> e.Expression | None:
    """`expr` rebuilt as the tuple its fields bind to in `target`, each field
    in the position it binds — or None when the fields already sit there, all
    the way down. `path` names the temporaries of a rebuild inside a rebuild."""
    bound = __bound_tuple(source, target, resolver)
    if bound is None:
        return None
    binding = t.bind_tuple_entries(bound.entries, [en.name for en in source.entries])
    if binding is None:
        return None
    lr = expr.line_ref
    in_place = binding == list(range(len(source.entries)))

    # A tuple literal's entries already converged toward the fields they bind:
    # they only move.
    if isinstance(expr, e.TupleExpression) and not any(x.spread for x in expr.expressions):
        if in_place:
            return None
        return e.TupleExpression(lr, [
            e.TupleEntryExpression(None, expr.expressions[b].value if b is not None else field.default)
            for field, b in zip(bound.entries, binding)])

    # Any other value is held once and read field by field.
    held = f"$fn{path}"
    changed = not in_place
    fields: list[e.TupleEntryExpression] = []
    for i, (field, b) in enumerate(zip(bound.entries, binding)):
        if b is None:
            fields.append(e.TupleEntryExpression(None, field.default))
            continue
        read = e.DotExpression(lr, e.NamedExpression(lr, held), source.entries[b].name or "", b)
        inner = __bound_by_position(read, source.entries[b].type, field.type, resolver, f"{path}_{i}")
        changed = changed or inner is not None
        fields.append(e.TupleEntryExpression(None, inner if inner is not None else read))
    if not changed:
        return None
    hold = s.LetStatement(lr, f"{held}@{lr.hash6()}", None, {}, (), expr, None)
    return e.BlockExpression(lr, [hold], e.TupleExpression(lr, fields), tag=None)


# ── 3: the names go ──────────────────────────────────────────────────────────

def __unnamed(_resolver: g.Resolver, thing):
    if isinstance(thing, t.TupleSpec) and any(en.name is not None for en in thing.entries):
        return dataclasses.replace(thing, entries=type(thing.entries)(
            dataclasses.replace(en, name=None) for en in thing.entries))
    if isinstance(thing, e.TupleExpression) and any(x.name is not None for x in thing.expressions):
        return dataclasses.replace(thing, expressions=[
            dataclasses.replace(x, name=None) for x in thing.expressions])
    return rw.UNCHANGED
