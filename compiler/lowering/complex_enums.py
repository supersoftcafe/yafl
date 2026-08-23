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

from parsing.parselib import Error
import pyast.statement as s
import pyast.typespec as t
import pyast.resolver as g



def _collect_reachable_roots(spec: t.TypeSpec | None, out: set[str], name_to_root: dict[str, str],
                             errors: list[Error]) -> None:
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
            _collect_reachable_roots(ent.type, out, name_to_root, errors)
    elif isinstance(spec, t.CombinationSpec):
        for tt in spec.types:
            _collect_reachable_roots(tt, out, name_to_root, errors)
    elif isinstance(spec, t.CallableSpec):
        _collect_reachable_roots(spec.parameters, out, name_to_root, errors)
        _collect_reachable_roots(spec.result, out, name_to_root, errors)
    elif isinstance(spec, t.NamedSpec):
        # Map bare/qualified names to canonical root_name. Only enum
        # targets contribute; class/builtin targets aren't in the map.
        if spec.name in name_to_root:
            out.add(name_to_root[spec.name])
        else:
            # Try matching by suffix form ("Foo::Bar" → match
            # "AnyNs::Foo::Bar@hash" via simple-name comparison).
            #
            # EVERY candidate is considered, not just the first. Stopping at
            # the first made the answer depend on map INSERTION ORDER: two
            # roots that both suffix-match resolved to whichever was inserted
            # earlier, and that choice decides which enum breaks a cycle — i.e.
            # which enum gets BOXED, which reaches the emitted C. The two
            # compilers agreed only because they insert in the same order;
            # neither was deciding anything. An ambiguous reference is now an
            # ERROR naming the candidates (USER RULING). Candidates are SORTED
            # so the message does not depend on map order either.
            matches = sorted({canonical
                              for known_name, canonical in name_to_root.items()
                              if known_name.endswith("::" + spec.name)
                              or spec.name.endswith("::" + known_name)})
            if len(matches) == 1:
                out.add(matches[0])
            elif len(matches) > 1:
                errors.append(Error(
                    spec.line_ref,
                    f"ambiguous enum reference '{spec.name}' — matches "
                    + ", ".join(f"'{m}'" for m in matches) + "; qualify it"))
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


def _pick_cycle_breakers(edges: dict[str, set[str]], roots: dict[str, t.EnumSpec],
                         fields_of=None) -> set[str]:
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
        n_fields = (len(fields_of(name)) if fields_of is not None
                    else (len(spec.all_fields) if spec else 0))
        return (not _is_system(name), not is_self_loop, n_fields, name)

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


def compute_breakers(statements: list[s.Statement]) -> set[str]:
    """The breaker set — WHICH enum roots must lower complex — as a pure
    function of the statements: collect roots, build the reachability graph
    over DERIVED fields, pick one breaker per cycle. Exposed so is_complex
    can become derive-only (identity vs state): late readers query this
    analysis (memoized per compile) instead of reading stamps."""
    roots: dict[str, t.EnumSpec] = {}
    for stmt in statements:
        if isinstance(stmt, s.EnumStatement) and stmt._enum_spec is not None:
            spec = stmt._enum_spec
            roots.setdefault(spec.root_name, spec)
    if not roots:
        return set()
    from lowering.enum_fields import fields_provider
    fields_of = fields_provider(statements)
    name_to_root = _build_name_to_root(roots)
    edges: dict[str, set[str]] = {}
    for name, spec in roots.items():
        children: set[str] = set()
        for _, ftype in fields_of(name):
            _collect_reachable_roots(ftype, children, name_to_root, [])
        edges[name] = children
    return _pick_cycle_breakers(edges, roots, fields_of)


# ── per-leaf value-struct threshold (the enum-encoding principle) ───────────
#
# A variant whose payload exceeds this many words is a heap object EVERYWHERE
# it appears: it contributes one pointer slot to its enum's pool and its
# payload lives in the same per-leaf Object a complex enum would use. The
# decision is a property of the variant TYPE, not of any one union, so
# widening between unions holding it is always a straight slot copy. Sizes
# are estimated at spec level (the analysis runs resolver-free, like the
# breaker analysis): sub-word scalars count their true bytes, pointers a
# word, closures two words, nested flat enums their own pool estimate under
# decisions already made — children are decided before parents (the value-
# containment graph is acyclic once breakers are removed), so a child whose
# wide leaf boxes shrinks honestly before its parents are sized.

_MAX_VALUE_STRUCT_WORDS = 8
_MAX_VALUE_STRUCT_BYTES = _MAX_VALUE_STRUCT_WORDS * 8

_BUILTIN_BYTES = {"bool": 1, "int8": 1, "int16": 2, "int32": 4, "float32": 4}


def _has_interior_fields(stmt: s.EnumStatement) -> bool:
    """True when any non-leaf node of the variant tree declares fields.
    Inherited fields are read positionally across sibling variants, which
    requires every carrier to share one representation — so roots with
    interior-node fields keep all leaves inline (no per-leaf boxing)."""
    def walk(node: s.EnumStatement) -> bool:
        if not node.variants:
            return False
        own = any(let.declared_type is not None
                  for let in node.parameters.flatten())
        return own or any(walk(v) for v in node.variants)
    return walk(stmt)


def compute_boxed_leaves(statements: list[s.Statement],
                         breakers: set[str] | None = None) -> frozenset:
    """The boxed-leaf set — WHICH (root_name, leaf_name) variants of FLAT
    enums box their payload — as a pure function of the statements, like
    compute_breakers. Complex roots are excluded (every leaf of a complex
    root is already a heap object via its own machinery)."""
    if breakers is None:
        breakers = compute_breakers(statements)
    roots: dict[str, t.EnumSpec] = {}
    root_stmts: dict[str, s.EnumStatement] = {}
    for stmt in statements:
        if isinstance(stmt, s.EnumStatement) and stmt._enum_spec is not None:
            spec = stmt._enum_spec
            roots.setdefault(spec.root_name, spec)
            if stmt._root_name is None or stmt._root_name == stmt.name:
                root_stmts.setdefault(spec.root_name, stmt)
    if not root_stmts:
        return frozenset()
    name_to_root = _build_name_to_root(roots)
    boxed: set[tuple[str, str]] = set()
    pool_memo: dict[str, int] = {}

    def spec_bytes(spec: t.TypeSpec | None, stack: list[str]) -> int:
        if isinstance(spec, t.BuiltinSpec):
            return _BUILTIN_BYTES.get(spec.type_name, 8)
        if isinstance(spec, t.CallableSpec):
            return 16                       # fun_t: code word + env pointer
        if isinstance(spec, t.TupleSpec):
            return sum(spec_bytes(e.type, stack) for e in spec.entries)
        if isinstance(spec, t.CombinationSpec):
            # Conservative: widest member plus a tag word. Collapsed pointer
            # unions are really one word; the over-estimate only nudges
            # near-threshold leaves toward boxing.
            widths = [spec_bytes(m, stack) for m in spec.types]
            return (max(widths) if widths else 0) + 8
        if isinstance(spec, t.EnumSpec):
            return enum_value_bytes(spec.root_name, stack)
        if isinstance(spec, t.NamedSpec):
            if spec.name in name_to_root:
                return enum_value_bytes(name_to_root[spec.name], stack)
            return 8                        # class or unresolved: a pointer
        return 8                            # ClassSpec, placeholders, None

    def enum_value_bytes(root: str, stack: list[str]) -> int:
        if root in breakers or root not in root_stmts or root in stack:
            return 8                        # heap pointer (cycles all break)
        if root in pool_memo:
            return pool_memo[root]
        stmt = root_stmts[root]
        leaf_sets = t._collect_leaf_field_sets(stmt, [])
        leaf_names = roots[root].all_leaf_names
        boxable = not _has_interior_fields(stmt)
        inner = stack + [root]
        widths = []
        for leaf, lets in zip(leaf_names, leaf_sets):
            w = sum(spec_bytes(let.declared_type, inner) for let in lets)
            if w > _MAX_VALUE_STRUCT_BYTES and boxable:
                boxed.add((root, leaf))
                w = 8
            widths.append(w)
        pool = (max(widths) if widths else 0) + 8   # widest variant + tag
        pool_memo[root] = pool
        return pool

    for root in sorted(root_stmts):
        enum_value_bytes(root, [])
    return frozenset(boxed)


def mark_complex_enums(statements: list[s.Statement]) -> tuple[list[s.Statement], list[Error]]:
    """IDENTITY. is_complex is DERIVED (identity vs state): every reader
    queries the breaker analysis through its resolver (is_complex_root) or
    computes it from its statements (compute_breakers) — there are no stamps
    to apply and no stale copies to repair.

    The slot now earns its place: it VALIDATES the enum-name resolution that
    the breaker analysis depends on. compute_breakers is a lazy, cached
    resolver query with nowhere to report a diagnostic, so the same walk runs
    here purely to surface ambiguities (USER RULING: an ambiguous suffix match
    is an error, not first-insertion-wins)."""
    roots: dict[str, t.EnumSpec] = {}
    for st in statements:
        if isinstance(st, s.EnumStatement) and st._enum_spec is not None:
            spec = st._enum_spec
            if "@" in spec.root_name:
                roots.setdefault(spec.root_name, spec)
    if not roots:
        return statements, []
    from lowering.enum_fields import fields_provider
    fields_of = fields_provider(statements)
    name_to_root = _build_name_to_root(roots)
    errors: list[Error] = []
    for name in roots:
        for _, ftype in fields_of(name):
            _collect_reachable_roots(ftype, set(), name_to_root, errors)
    return statements, sorted(set(errors))
