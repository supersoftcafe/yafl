"""Detect complex enums and mark them.

A YAFL enum is "complex" when its `all_fields` graph contains a cycle
through this enum's `root_name` — directly (`enum List: Cons(tail: List)`)
or via mutual recursion through other enums (`enum A: A1(b: B); enum B:
B1(a: A)`). Recursive enums must lower to heap-allocated objects so the
compiled struct has finite size.

This pass runs once after monomorphization. Each `EnumSpec` whose
`root_name` qualifies gets `is_complex=True` rewritten via
`search_and_replace`. Simple enums are unchanged.

To break a cycle exactly one enum per cycle is marked complex; the rest
stay flat. The breaker is chosen by: System:: enums first (they appear in
many user-facing cycles), then the enum with the fewest all_fields entries
(small nodes are cheap indirections; richer types stay flat), then root_name.

Class boundaries break recursion cycles: a class field is already a
heap pointer, so an enum that references a class which references the
enum back is NOT recursive (the class boundary is the indirection).
The reachability walk therefore stops at `ClassSpec`.
"""
from __future__ import annotations

import dataclasses
from typing import Any

import pyast.statement as s
import pyast.typespec as t
import pyast.resolver as g



def _collect_reachable_roots(spec: t.TypeSpec | None, out: set[str], name_to_root: dict[str, str]) -> None:
    """Collect every EnumSpec.root_name directly referenced in `spec`,
    without crossing EnumSpec or class boundaries.

    We intentionally stop at EnumSpec boundaries (do not recurse into
    spec.all_fields). The outer loop in mark_complex_enums visits each
    root's own all_fields; transitive closure across enum boundaries is
    computed by the SCC algorithm, not here. Recursing transitively would
    create false self-loops (e.g. JsonValue → List → _ListNode → JsonValue)
    that cause the wrong enum to be chosen as the cycle breaker.

    NamedSpecs are resolved via the bare-name → canonical-root_name map —
    recursive-enum field types may still appear as NamedSpec in
    EnumSpec.all_fields because the iterative compile loop captures the
    self-reference at iteration 1 before its target's _enum_spec is
    populated."""
    if spec is None:
        return
    if isinstance(spec, t.EnumSpec):
        out.add(spec.root_name)
        # Stop here — do not recurse into spec.all_fields.
    elif isinstance(spec, t.TupleSpec):
        for ent in spec.entries:
            _collect_reachable_roots(ent.type, out, name_to_root)
    elif isinstance(spec, t.CombinationSpec):
        for tt in spec.types:
            _collect_reachable_roots(tt, out, name_to_root)
    elif isinstance(spec, t.CallableSpec):
        _collect_reachable_roots(spec.parameters, out, name_to_root)
        _collect_reachable_roots(spec.result, out, name_to_root)
    elif isinstance(spec, t.NamedSpec):
        # Map bare/qualified names to canonical root_name. Only enum
        # targets contribute; class/builtin targets aren't in the map.
        if spec.name in name_to_root:
            out.add(name_to_root[spec.name])
        else:
            # Try matching by suffix form ("Foo::Bar" → match
            # "AnyNs::Foo::Bar@hash" via simple-name comparison).
            for known_name, canonical in name_to_root.items():
                if known_name.endswith("::" + spec.name) or spec.name.endswith("::" + known_name):
                    out.add(canonical)
                    break
    # ClassSpec, BuiltinSpec, GenericPlaceholderSpec: no descent.


def _build_name_to_root(roots: dict[str, t.EnumSpec]) -> dict[str, str]:
    """Build a map from every name form (bare, namespaced) of an enum
    root to its canonical root_name. The unique-id form `Name@hash` is
    NOT a key because NamedSpec.name typically lacks the hash."""
    out: dict[str, str] = {}
    for canonical in roots:
        # canonical: "Ns1::Ns2::Name@hash" or "Name@hash"
        no_hash = canonical.rpartition("@")[0] or canonical
        out.setdefault(no_hash, canonical)  # full namespaced form
        bare = no_hash.rpartition("::")[-1]
        out.setdefault(bare, canonical)     # bare name (last namespace component)
    return out


def _find_sccs(edges: dict[str, set[str]]) -> list[set[str]]:
    """Tarjan's SCC algorithm. Returns one set per strongly-connected component."""
    index: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    sccs: list[set[str]] = []
    counter = [0]

    def visit(v: str) -> None:
        index[v] = lowlink[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on_stack.add(v)
        for w in sorted(edges.get(v, ())):
            if w not in index:
                visit(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif w in on_stack:
                lowlink[v] = min(lowlink[v], index[w])
        if lowlink[v] == index[v]:
            scc: set[str] = set()
            while True:
                w = stack.pop()
                on_stack.discard(w)
                scc.add(w)
                if w == v:
                    break
            sccs.append(scc)

    for v in sorted(edges):
        if v not in index:
            visit(v)
    return sccs


def _pick_cycle_breakers(edges: dict[str, set[str]], roots: dict[str, t.EnumSpec]) -> set[str]:
    """Return the minimal set of nodes to mark complex to break all cycles.

    Priority: System:: nodes first, then fewest all_fields entries, then root_name.
    Prefer small nodes as the indirection point; richer types stay flat.
    Iterates until no cycles remain (handles SCCs with multiple independent sub-cycles).
    """
    def _is_system(name: str) -> bool:
        bare = name.rpartition("@")[0] or name
        return bare.startswith("System::")

    def _sort_key(name: str) -> tuple:
        spec = roots.get(name)
        is_self_loop = name in work.get(name, ())
        return (not _is_system(name), not is_self_loop, len(spec.all_fields) if spec else 0, name)

    result: set[str] = set()
    work: dict[str, set[str]] = {k: set(v) for k, v in edges.items()}

    while True:
        cyclic = [s for s in _find_sccs(work)
                  if len(s) > 1 or any(n in work.get(n, ()) for n in s)]
        if not cyclic:
            break
        for scc in cyclic:
            chosen = min(scc, key=_sort_key)
            result.add(chosen)
            del work[chosen]
            for nbrs in work.values():
                nbrs.discard(chosen)

    return result


def mark_complex_enums(statements: list[s.Statement]) -> list[s.Statement]:
    # 1. Index every top-level EnumStatement by its root_name.
    #    Variants nested inside the root share the same root_name and the
    #    same all_fields (assigned by EnumStatement._assign_specs) — we
    #    only need to walk the root.
    roots: dict[str, t.EnumSpec] = {}
    for stmt in statements:
        if isinstance(stmt, s.EnumStatement) and stmt._enum_spec is not None:
            spec = stmt._enum_spec
            # If two top-level statements share a root_name they must agree
            # on all_fields (compiler invariant); take the first.
            roots.setdefault(spec.root_name, spec)

    if not roots:
        return statements

    name_to_root = _build_name_to_root(roots)

    # 2. Build the directed reachability graph between root_names. A
    #    self-loop (this enum's fields contain a reference back to its
    #    own root_name) is the common case for self-recursive enums;
    #    larger cycles arise from mutual recursion.
    edges: dict[str, set[str]] = {}
    for name, spec in roots.items():
        children: set[str] = set()
        for _, ftype in spec.all_fields:
            _collect_reachable_roots(ftype, children, name_to_root)
        edges[name] = children

    # 3. Pick exactly one breaker per cycle.
    complex_set = _pick_cycle_breakers(edges, roots)

    if not complex_set:
        return statements

    # 4. Rewrite every EnumSpec instance throughout the AST.
    #    - Set is_complex on EnumSpec instances whose root_name is
    #      complex.
    #    - Resolve NamedSpec children of all_fields to their target
    #      EnumSpec (with is_complex applied). The iterative compile
    #      loop leaves NamedSpec references inside an enum's own
    #      all_fields when the spec was first built before the target
    #      was fully populated; codegen needs concrete types here.
    #    - Pruned generic EnumSpecs (not in roots) that survive as stale
    #      references inside specialized enum all_fields are marked complex
    #      so generate() never tries to expand their GenericPlaceholderSpec
    #      all_fields.
    #    - Recursion into all_fields uses EnumSpec.walk_all_fields with a
    #      visited set, propagating is_complex to stale copies at any depth
    #      while avoiding loops on self-recursive types.
    def _resolve_named(ft: t.TypeSpec, visited: frozenset[str] = frozenset()) -> t.TypeSpec:
        if isinstance(ft, t.NamedSpec):
            canonical = name_to_root.get(ft.name)
            if canonical is None:
                for known, c in name_to_root.items():
                    if known.endswith("::" + ft.name) or ft.name.endswith("::" + known):
                        canonical = c
                        break
            if canonical is not None and canonical in roots:
                spec = roots[canonical]
                is_complex = canonical in complex_set
                return dataclasses.replace(spec, is_complex=is_complex) if is_complex != spec.is_complex else spec
        if isinstance(ft, t.EnumSpec):
            is_complex = ft.root_name in complex_set
            if not is_complex and ft.root_name not in roots:
                return dataclasses.replace(ft, is_complex=True) if not ft.is_complex else ft
            if ft.root_name not in visited:
                new_visited = visited | {ft.root_name}
                new_fields = tuple((n, _resolve_named(f, new_visited)) for n, f in ft.all_fields)
                fields_changed = any(nf is not of_
                                     for (_, nf), (_, of_) in zip(new_fields, ft.all_fields))
                if is_complex != ft.is_complex or fields_changed:
                    return dataclasses.replace(ft, is_complex=is_complex, all_fields=new_fields)
            else:
                if is_complex != ft.is_complex:
                    return dataclasses.replace(ft, is_complex=is_complex)
        return ft

    def mark(_resolver: g.Resolver, thing: Any) -> Any:
        if isinstance(thing, t.EnumSpec):
            is_complex = thing.root_name in complex_set
            new_fields = tuple(
                (n, _resolve_named(ft)) for n, ft in thing.all_fields)
            fields_changed = any(nf is not of_
                                 for (_, nf), (_, of_) in zip(new_fields, thing.all_fields))
            if is_complex != thing.is_complex or fields_changed:
                return dataclasses.replace(thing, is_complex=is_complex, all_fields=new_fields)
        return thing

    resolver = g.ResolverRoot(statements)
    return [stmt.search_and_replace(resolver, mark) for stmt in statements]
