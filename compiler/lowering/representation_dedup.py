"""Merge objects, functions and globals whose representation is identical.

Monomorphisation gives every instantiation its own vtables and functions, even
when T only ever sits behind a pointer, so the emitted code for `List<A>` and
`List<B>` is the same code under two sets of names. This pass finds every
group of IR entities that are indistinguishable and keeps one of each.

EQUIVALENCE is the coarsest partition in which two members agree on their own
shape and refer to equivalent entities at the same positions. It is computed
by partition refinement (Moore): start from groups keyed by shape alone, then
split by the groups of what each member refers to, until nothing splits. That
reaches cycles — a vtable whose methods allocate that same vtable — which a
bottom-up pass cannot. A shape compares locals and labels up to renaming (an
inlined body names its locals by inline counter), types structurally, and
everything else literally.

RUNTIME IDENTITY is only merged where nothing can observe it:
  * An instance test (`ObjVtableEq`) observes identity only among the
    classes that can reach it. Over a union of classes that set is the
    union's class members, which the test carries (`among`): the tested
    class must stay apart from each of them, and is otherwise free to merge
    — `Leaf<A>` and `Leaf<B>` may become one object, as long as no single
    union holds both. A test whose set is open (`among` None: an interface
    subject, an interface or enum member) pins its class: any implementor
    could arrive, and the test would start answering true for it.
  * A complex-enum leaf's identity is its `Object.discriminator`, and match
    dispatch compares `VtableDiscriminator(v)` against leaf ids. Those
    comparisons are the only integers the pass reads as identities; every
    other integer (a `$tag` numbering is either positional or global, and the
    IR cannot say which) compares literally, which can only prevent a merge.
    Leaves of the same enum stay in distinct groups, so every dispatch still
    sees distinct ids after the rewrite. Should a discriminator read ever
    appear outside such a comparison, no leaf merges at all.
  * The entry point is pinned.

REFERENCES are exactly what trim counts as references, and trim has just run,
so nothing reachable only through a literal survives to be missed. Every
string field is classified as a reference, a local, a label or a literal; an
unclassified one is a compiler bug, reported rather than guessed at.

The first member of each group in `Application` order survives; references
to the rest are rewritten to it and the rest are deleted. Runs last, after
every optimisation has seen each function on its own, and not under
--profile, which must attribute time to the functions the source declares.
"""
from __future__ import annotations

import dataclasses
import hashlib
import re
from typing import Any, Callable

import codegen.ops as o
import codegen.param as p
import codegen.typedecl as t
from codegen.gen import Application
from codegen.ir import Function, Global, Object


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def merge_identical_representations(app: Application) -> Application:
    """See module docstring."""
    if app.profile:
        return app
    graph = _Graph(app)
    groups = _refine(graph)
    return _rewrite(app, graph, groups)


# ---------------------------------------------------------------------------
# Roles: what a string (or an integer) inside the IR refers to
# ---------------------------------------------------------------------------

OBJ, FUN, GLB = "obj", "fun", "glb"   # node kinds, and the roles naming them
VAR, LABEL = "var", "label"           # local names, compared up to renaming
LIT = "lit"                           # compared as written

# (class, field) → role. Tuple-valued fields apply the role to each element;
# a tuple role applies positionally to each element's items. A string field
# absent from here is unclassified — see the module docstring.
_ROLES: dict[tuple[type, str], Any] = {
    (o.Label, "name"): LABEL,
    (o.Jump, "name"): LABEL,
    (o.JumpIf, "label"): LABEL,
    (o.IfTask, "target"): LABEL,
    (o.SwitchJump, "cases"): (None, LABEL),
    (o.Phi, "sources"): (LABEL, None),
    (o.NewObject, "name"): OBJ,
    (p.ObjVtableEq, "class_name"): OBJ,
    (p.ObjectField, "object_name"): OBJ,
    (p.ArrayElement, "object_name"): OBJ,
    (p.GlobalFunction, "name"): FUN,
    (p.GlobalVar, "name"): GLB,
    (p.StaticObjectRef, "name"): GLB,
    (o.Abort, "reason"): LIT,
    (p.RuntimeInvoke, "function"): LIT,
    (p.StructField, "field"): LIT,
    (p.String, "value"): LIT,
    (p.NewStruct, "values"): (LIT, None),
    (p.NewStructTyped, "values"): (LIT, None),
    (p.GlobalFunction, "c_symbol"): LIT,
    (p.ObjVtableEq, "extern_symbol"): LIT,
    (p.VirtualFunction, "name"): LIT,
    (p.ObjectField, "field"): LIT,
    (p.ArrayElement, "field"): LIT,
    (p.ArrayElement, "length_field"): LIT,
    (p.FunField, "part"): LIT,
}


def _role(x: Any, f: str) -> Any:
    # An external function's name is a C symbol, not a reference (as in trim).
    if f == "name" and isinstance(x, p.GlobalFunction) and x.external:
        return LIT
    return _ROLES.get((type(x), f))

# A StackVar's name is free up to renaming, except for the names whose
# spelling carries meaning to a later stage (ssa_validate's scratch slots,
# the receiver, async lowering's state) — those must agree to merge.
_FIXED_VARS = frozenset({"this", "$state", "$completed_task", "$continuation"})
_SCRATCH_PREFIX = re.compile(r"^\$[a-z]+[_$]")


def _var_kind(name: str) -> str:
    if name in _FIXED_VARS:
        return name
    m = _SCRATCH_PREFIX.match(name)
    return m.group(0) if m else ""


# ---------------------------------------------------------------------------
# The graph: one canonical shape and one reference list per node
# ---------------------------------------------------------------------------

Node = tuple[str, str]   # (kind, name)
class _Ref:
    """Placeholder token where a reference sits in a shape. Its repr cannot
    be mistaken for a literal: a string token's repr is quoted."""
    def __repr__(self) -> str:
        return "<ref>"


_REF = _Ref()


class _Graph:
    def __init__(self, app: Application):
        self.nodes: list[Node] = ([(OBJ, n) for n in app.objects]
                                  + [(FUN, n) for n in app.functions]
                                  + [(GLB, n) for n in app.globals])
        self.names = {OBJ: app.objects, FUN: app.functions, GLB: app.globals}
        # A leaf's discriminator id names the leaf, so a dispatch comparison
        # against it is a reference to that object.
        self.leaf_by_id: dict[int, str] = {
            obj.discriminator: n for n, obj in app.objects.items() if obj.discriminator}
        self.shape: dict[Node, bytes] = {}
        self.type_ids: dict[t.Type, int] = {}
        self.refs: dict[Node, tuple[Node, ...]] = {}
        self.pinned: set[Node] = {(FUN, "__entrypoint__")}
        self.stray_discriminator = False
        # Sets of objects an instance test must tell apart (see `among`).
        self.separations: list[frozenset[str]] = []

        for n, obj in app.objects.items():
            self.__add((OBJ, n), self.__object(obj))
        for n, fn in app.functions.items():
            self.__add((FUN, n), self.__function(fn))
        for n, gv in app.globals.items():
            self.__add((GLB, n), self.__global(n, gv))

        if self.stray_discriminator:
            self.pinned.update((OBJ, n) for n in self.leaf_by_id.values())
        self.conflicts = self.__conflicts()

    def __conflicts(self) -> dict[Node, set[Node]]:
        """Which nodes each node must never share a group with: the other
        leaves of its enum (a dispatch compares their ids), and the other
        classes of any union an instance test separates it within."""
        out: dict[Node, set[Node]] = {}
        def apart(nodes: list[Node]) -> None:
            for a in nodes:
                out.setdefault(a, set()).update(b for b in nodes if b != a)
        by_parent: dict[tuple[str, ...], list[Node]] = {}
        for n in self.nodes:
            if self.is_leaf(n):
                by_parent.setdefault(self.parent(n), []).append(n)
        for leaves in by_parent.values():
            apart(leaves)
        for names in self.separations:
            apart([(OBJ, x) for x in sorted(names) if x in self.names[OBJ]])
        return out

    def is_leaf(self, node: Node) -> bool:
        return node[0] == OBJ and self.names[OBJ][node[1]].discriminator != 0

    def parent(self, node: Node) -> tuple[str, ...]:
        return self.names[OBJ][node[1]].extends

    def __add(self, node: Node, canon: _Canon) -> None:
        # A shape is held as a 128-bit digest of its tokens' repr: the whole
        # program's token tuples at once would cost more than the IR itself.
        # Types enter as ids interned by their own equality (see _Canon.ty),
        # so the repr of everything else is at least as discriminating as
        # tuple equality, and a digest can only split what equality joins.
        self.shape[node] = hashlib.blake2b(
            repr((node[0], canon.tokens)).encode(), digest_size=16).digest()
        self.refs[node] = tuple(canon.refs)

    def __object(self, obj: Object) -> _Canon:
        c = _Canon(self)
        if obj.is_foreign:
            self.pinned.add((OBJ, obj.name))
        c.emit(obj.fields)
        c.emit(obj.length_field, LIT)
        c.emit((obj.is_foreign, obj.is_mutable, obj.is_pinnable, obj.discriminator != 0))
        c.emit(obj.extends, OBJ)
        c.emit(obj.functions, (LIT, FUN))
        return c

    def __function(self, fn: Function) -> _Canon:
        # Parameters are positional; locals are named by first use, and their
        # declarations compare as a set — declaration order means nothing.
        c = _Canon(self)
        c.tokens.append(tuple((c.var(n), c.ty(ty)) for n, ty in fn.params.fields))
        c.emit(fn.foreign_symbol, LIT)
        c.emit((fn.result, fn.sync, fn.tail, fn.bypass_async, fn.always_inline))
        c.emit(fn.ops)
        for n, _ in fn.stack_vars.fields:
            c.var(n)
        c.close_sets()
        c.tokens.append(tuple(sorted((c.var(n), c.ty(ty)) for n, ty in fn.stack_vars.fields)))
        return c

    def __global(self, name: str, gv: Global) -> _Canon:
        c = _Canon(self)
        # Interned string literals are left out of the GC root set by name.
        c.emit((gv.type, name.startswith("$strings::")))
        c.emit(gv.init)
        c.emit(gv.object_name, OBJ)
        c.emit(gv.lazy_init_function, FUN)
        c.emit(gv.lazy_init_flag, GLB)
        return c


class _Canon:
    """Flattens one node into tokens. Each class emits a fixed field sequence
    and each container its length first, so the flat form is unambiguous."""

    def __init__(self, graph: _Graph):
        self.graph = graph
        self.tokens: list = []
        self.refs: list[Node] = []
        self.vars: dict[str, tuple] = {}
        self.labels: dict[str, int] = {}
        self.sets: list = []

    def var(self, name: str) -> tuple:
        v = self.vars.get(name)
        if v is None:
            v = self.vars[name] = (len(self.vars), _var_kind(name))
        return v

    def close_sets(self) -> None:
        """Encode the deferred saved_vars sets, once every local has its
        number from an ordered position. One that appears nowhere else is
        numbered by name — deterministic, if more conservative."""
        for x in self.sets:
            for name in sorted(v.name for v in x):
                self.var(name)
        self.tokens.append(tuple(tuple(sorted((self.var(v.name), self.ty(v.type)) for v in x))
                                 for x in self.sets))

    def ty(self, x: t.Type) -> tuple:
        """A type by its own equality: a repr would also print the fields
        equality ignores (FuncPointer.sync, a refinement)."""
        ids = self.graph.type_ids
        return ("Y", ids.setdefault(x, len(ids)))

    def emit(self, x: Any, role: Any = None) -> None:
        if isinstance(x, str):
            self.__string(x, role)
        elif isinstance(x, tuple):
            self.tokens.append(("T", len(x)))
            for item in x:
                if isinstance(role, tuple):
                    for part, r in zip(item, role):
                        self.emit(part, r)
                else:
                    self.emit(item, role)
        elif isinstance(x, (set, frozenset)):
            # saved_vars: an unordered set, so it may not number a local —
            # its iteration order is hash-seeded. Encoded by close_sets.
            self.tokens.append(("S", len(self.sets)))
            self.sets.append(x)
        elif isinstance(x, t.Type):
            self.tokens.append(self.ty(x))
        elif x is None or isinstance(x, (bool, int, float)):
            self.tokens.append(x)
        elif isinstance(x, p.StackVar):
            self.tokens.append(("V", self.var(x.name), self.ty(x.type)))
        elif isinstance(x, p.IntEqConst) and isinstance(x.value, p.VtableDiscriminator):
            self.tokens.append(p.IntEqConst)
            self.tokens.append(p.VtableDiscriminator)
            self.__dataclass(x.value)
            leaf = self.graph.leaf_by_id.get(x.const_val)
            if leaf is None:
                self.tokens.append(x.const_val)
            else:
                self.__ref(OBJ, leaf)
        elif dataclasses.is_dataclass(x):
            if isinstance(x, p.VtableDiscriminator):
                self.graph.stray_discriminator = True
            self.tokens.append(type(x))
            self.__dataclass(x)
        else:
            raise TypeError(f"representation_dedup: unexpected IR value {x!r}")

    def __dataclass(self, x: Any) -> None:
        cls = type(x)
        if cls is p.ObjVtableEq and x.class_name is not None:
            if x.among is None:
                self.graph.pinned.add((OBJ, x.class_name))
            else:
                self.graph.separations.append(frozenset((x.class_name, *x.among)))
        for f in _fields(cls, compared=True):
            self.emit(getattr(x, f), _role(x, f))

    def __string(self, s: str, role: Any) -> None:
        if role == VAR:
            self.tokens.append(self.var(s))
        elif role == LABEL:
            self.tokens.append(("L", self.labels.setdefault(s, len(self.labels))))
        elif role in (OBJ, FUN, GLB) and s in self.graph.names[role]:
            self.__ref(role, s)
        elif role in (OBJ, FUN, GLB, LIT):
            self.tokens.append(s)
        else:
            raise TypeError(f"representation_dedup: unclassified string field holding {s!r}")

    def __ref(self, kind: str, name: str) -> None:
        self.tokens.append(_REF)
        self.refs.append((kind, name))


_FIELDS: dict[tuple[type, bool], tuple[str, ...]] = {}


def _fields(cls: type, compared: bool = False) -> tuple[str, ...]:
    """A node class's fields; `compared` keeps only those that take part in
    its equality (a compare=False field such as ObjectField.fresh is a
    refinement of the same value, as for types)."""
    fs = _FIELDS.get((cls, compared))
    if fs is None:
        fs = _FIELDS[cls, compared] = tuple(
            f.name for f in dataclasses.fields(cls) if f.compare or not compared)
    return fs


# ---------------------------------------------------------------------------
# Partition refinement
# ---------------------------------------------------------------------------

def _refine(graph: _Graph) -> dict[Node, int]:
    """Group id per node: the coarsest partition that agrees on shape, on the
    groups of references, and keeps pinned nodes and sibling leaves apart."""
    groups = _number(graph.nodes, lambda n: ("pinned", n) if n in graph.pinned else graph.shape[n])
    while True:
        while True:
            refined = _number(graph.nodes, lambda n: (
                groups[n], tuple(groups[r] for r in graph.refs[n])))
            if len(set(refined.values())) == len(set(groups.values())):
                break
            groups = refined
        separated = _separate_siblings(graph, groups)
        if separated is None:
            return groups
        groups = separated


def _number(nodes: list[Node], key: Callable[[Node], Any]) -> dict[Node, int]:
    ids: dict[Any, int] = {}
    return {n: ids.setdefault(key(n), len(ids)) for n in nodes}


def _separate_siblings(graph: _Graph, groups: dict[Node, int]) -> dict[Node, int] | None:
    """Split any group holding two nodes that must stay apart — two leaves of
    one enum (a dispatch must still see a distinct id per leaf), or two
    classes an instance test tells apart. Each such node goes to the first
    sub-group holding none of its conflicts, in graph order. None when
    nothing splits."""
    members: dict[int, list[Node]] = {}
    for n in graph.nodes:
        if n in graph.conflicts:
            members.setdefault(groups[n], []).append(n)
    split: dict[Node, int] = {}
    for nodes in members.values():
        for n in nodes:
            used = {split[m] for m in graph.conflicts[n] if m in split and groups[m] == groups[n]}
            split[n] = next(i for i in range(len(used) + 1) if i not in used)
    if not any(split.values()):
        return None
    return _number(graph.nodes, lambda n: (groups[n], split.get(n, 0)))


# ---------------------------------------------------------------------------
# Rewrite: keep the first member of each group, redirect the rest to it
# ---------------------------------------------------------------------------

def _rewrite(app: Application, graph: _Graph, groups: dict[Node, int]) -> Application:
    survivor: dict[int, Node] = {}
    for n in graph.nodes:
        survivor.setdefault(groups[n], n)
    renames: dict[str, dict[str, str]] = {OBJ: {}, FUN: {}, GLB: {}}
    for n in graph.nodes:
        s = survivor[groups[n]]
        if s != n:
            renames[n[0]][n[1]] = s[1]
    if not any(renames.values()):
        return app
    ids = {obj.discriminator: app.objects[renames[OBJ][n]].discriminator
           for n, obj in app.objects.items() if obj.discriminator and n in renames[OBJ]}
    r = _Renamer(renames, ids)

    return dataclasses.replace(
        app,
        objects={n: r.object(x) for n, x in app.objects.items() if n not in renames[OBJ]},
        functions={n: r.function(x) for n, x in app.functions.items() if n not in renames[FUN]},
        globals={n: r.global_(x) for n, x in app.globals.items() if n not in renames[GLB]})


class _Renamer:
    def __init__(self, renames: dict[str, dict[str, str]], ids: dict[int, int]):
        self.renames = renames
        self.ids = ids

    def object(self, obj: Object) -> Object:
        return dataclasses.replace(
            obj,
            extends=tuple(self.name(e, OBJ) for e in obj.extends),
            functions=tuple((slot, self.name(f, FUN)) for slot, f in obj.functions))

    def function(self, fn: Function) -> Function:
        return dataclasses.replace(fn, ops=tuple(self.value(op) for op in fn.ops))

    def global_(self, gv: Global) -> Global:
        return dataclasses.replace(
            gv,
            init=self.value(gv.init),
            object_name=self.name(gv.object_name, OBJ),
            lazy_init_function=self.name(gv.lazy_init_function, FUN),
            lazy_init_flag=self.name(gv.lazy_init_flag, GLB))

    def name(self, s: str | None, kind: str) -> str | None:
        return None if s is None else self.renames[kind].get(s, s)

    def value(self, x: Any) -> Any:
        """Rebuild `x` with every reference redirected; unchanged parts are
        returned as they are."""
        if isinstance(x, tuple):
            items = tuple(self.value(i) for i in x)
            return x if all(a is b for a, b in zip(items, x)) else items
        if not dataclasses.is_dataclass(x) or isinstance(x, (t.Type, p.StackVar)):
            return x
        cls = type(x)
        changes = {}
        for f in _fields(cls):
            old = getattr(x, f)
            role = _role(x, f)
            new = self.name(old, role) if role in (OBJ, FUN, GLB) else self.value(old)
            if new is not old:
                changes[f] = new
        if isinstance(x, p.IntEqConst) and isinstance(x.value, p.VtableDiscriminator):
            leaf_id = self.ids.get(x.const_val, x.const_val)
            if leaf_id != x.const_val:
                changes["const_val"] = leaf_id
        return dataclasses.replace(x, **changes) if changes else x
