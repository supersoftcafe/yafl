"""Change-propagating tree rewrite — the machinery behind `search_and_replace`.

A rewrite reports whether it changed anything by returning either the new
value or the `UNCHANGED` sentinel. Threaded bottom-up, a node is unchanged
exactly when its callback made no change AND every child returned UNCHANGED;
in that case it returns UNCHANGED and constructs nothing. Only the subtrees
that actually change are rebuilt (one `dataclasses.replace` at the real change
site), so a pass that touches a handful of nodes stops rebuilding the whole
program.

The "did it change?" answer is *produced* by the transform (an explicit
signal), never *inferred* by comparing objects — so there is no reliance on
object identity or on O(subtree) value equality. `UNCHANGED` is a distinct
singleton, never confused with a `None` field value. This is the Python
spelling of the value-semantics algorithm (`Rewrite<T> = Changed<T> |
Unchanged`) the compiler will use once it is self-hosted.
"""
from __future__ import annotations

import dataclasses
from typing import Any, Callable, Iterable


class _Unchanged:
    __slots__ = ()
    def __repr__(self) -> str: return "UNCHANGED"


UNCHANGED = _Unchanged()


def rewrite(node: Any, replace: Callable, cb_resolver: Any, **fields: Any) -> Any:
    """Rebuild `node` only from the fields that changed (a field value of
    `UNCHANGED` means "keep the original"), run the callback on the result, and
    return the node — or `UNCHANGED` when nothing changed at all, propagating
    that up so no ancestor rebuilds either."""
    changed = {k: v for k, v in fields.items() if v is not UNCHANGED}
    rebuilt = dataclasses.replace(node, **changed) if changed else node
    out = replace(cb_resolver, rebuilt)
    if out is not UNCHANGED:
        return out
    return rebuilt if changed else UNCHANGED


def rebuild(node: Any, **fields: Any) -> Any:
    """Like `rewrite` but for a structural node the callback never visits
    (a match arm, a tuple entry): rebuild only if some field changed, else
    return `UNCHANGED`."""
    changed = {k: v for k, v in fields.items() if v is not UNCHANGED}
    return dataclasses.replace(node, **changed) if changed else UNCHANGED


def opt(child: Any, resolver: Any, replace: Callable) -> Any:
    """Rewrite an optional single child; a `None` field is left as `None`."""
    return UNCHANGED if child is None else child.search_and_replace(resolver, replace)


def seq(items: Iterable, resolver: Any, replace: Callable) -> Any:
    """Rewrite a list/tuple of children, preserving the sequence type; returns
    `UNCHANGED` when no element changed."""
    out = []
    changed = False
    for it in items:
        r = it.search_and_replace(resolver, replace)
        if r is UNCHANGED:
            out.append(it)
        else:
            out.append(r)
            changed = True
    return type(items)(out) if changed else UNCHANGED


def resolved(result: Any, original: Any) -> Any:
    """For a caller that needs a concrete value (not the UNCHANGED signal) —
    e.g. the top of a `search_and_replace` invocation from a pass."""
    return original if result is UNCHANGED else result
