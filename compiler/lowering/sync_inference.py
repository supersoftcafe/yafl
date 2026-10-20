"""
Sync inference pass.

After inlining and devirtualisation, before task lowering: prove which
functions — and which function VALUES — can never suspend, and record it on
the IR so the task lowering can make a call through a sync value a plain
call (no basic-block split, no resume case, no IfTask).

The fact lives on the function-value type: `FuncPointer.sync`. Every call is
a call through a function value, so one rule decides every call site:
`op.function.get_type().sync`. `GlobalFunction.sync` / `VirtualFunction.sync`
answer for a constant function value; a StackVar / ObjectField / GlobalVar
answers through its type.

The flow
--------
One optimistic dataflow over two kinds of node:

  * a FUNCTION — "may suspend" — and its MAYBE_ASYNC twin: "may suspend
    other than by calling its own function parameters";
  * a function-typed LOCATION — an SSA variable, a parameter (a variable
    fed by its callers), a function result, an object field, a global.

Every node starts sync and can only FALL; a node falls when any of its
sources falls:

  function F     every call's sources (tail calls too: F returns the
                 callee's task); ParallelCall, a `TagTask` return, being
                 foreign or hand-built (`bypass_async`) without `sync`, make
                 F fall outright
  maybe_async F  the same, except a call of one of F's own function
                 parameters — called, or handed on to a callee — does not
                 count. F is MAYBE_ASYNC when this holds but F falls: it keeps
                 its suspension points, yet a call of it whose function
                 arguments are all sync returns a value
  GlobalFunction the function it names
  VirtualFunction every implementation (none known = unknown)
  SSA variable   its definitions: Move source, Phi = AND of every incoming
                 value, a direct/virtual call's register = the callees'
                 results
  parameter      the matching argument at every direct call site; a virtual
                 site feeds every implementation
  result of F    every `Return` value
  object field   every store into it program-wide, static initialisers
                 included; base- and derived-class views of one field are
                 one node

A call's sources: for a direct or virtual call, every callee's maybe_async
node and the function arguments handed to it; for any other call, its
function value. A call is sync when all of its sources are — decided per
SITE, so one maybe_async function is sync at some call sites and not others.
"Its own parameter" includes a variable that only ever holds one: the loop
variable a [tail] lowering carries the parameter round in.

Anything the flow cannot see is UNKNOWN and makes its dependent fall
outright: the parameters of an address-taken function (called from sites
the IR cannot enumerate — `trim.address_taken_functions`), a call result
through a non-constant function value, closures read out of aggregates,
arrays and union slots (StructField / ArrayElement / MakeFun), and fields of
foreign (runtime-owned) objects.

Each node falls at most once, so the worklist is linear. Starting
optimistic makes it the GREATEST fixpoint: a recursive function that
reaches no source of suspension is proven sync. A suspension has to start
at a source, so this is sound.

A function the programmer marked `[sync]` (or a hand-built one authored
sync) is trusted and never falls; a may-suspend call inside it keeps its
IfTask, and reaching the cold path aborts.

Materialisation: `fn.sync`, `sync` on every GlobalFunction/VirtualFunction
reference, and `FuncPointer(sync=...)` on every function-typed StackVar,
ObjectField, GlobalVar, parameter / stack-variable declaration and object
field declaration.
"""

from __future__ import annotations

import dataclasses
import lowering.trim as trim
from codegen.gen import Application
from codegen.ir import Function, Object
from codegen.ops import Call, Move, Op, ParallelCall, Phi, Return
from codegen.param import (
    GlobalFunction, GlobalVar, NewStruct, NewStructTyped, NullPointer,
    ObjectField, RParam, StackVar, StructField, TagTask, VirtualFunction,
    ZeroOf,
)
from codegen.typedecl import FuncPointer, Struct, Type


def _returns_tagged_task(fn: Function) -> bool:
    """A function whose body returns `TagTask(...)` produces a tagged
    task pointer — its callers' `PTR_IS_TASK` check will fire and they
    must enter the async path.  Such a function cannot be sync,
    regardless of whether its ops contain `Call` nodes."""
    return any(isinstance(op, Return) and isinstance(op.value, TagTask)
               for op in fn.ops)


def _is_fun(t: Type) -> bool:
    return isinstance(t, FuncPointer)


Path = tuple[str, ...]


def _fun_paths(t: Type) -> tuple[Path, ...]:
    """The field paths to every function-typed leaf of `t`: `((),)` for a
    function itself, `(("_0",), ("p", "f"))` for a struct holding two. The
    flag follows the value wherever the type nests it — a closure riding in
    a tuple or a flattened class is still tracked."""
    if isinstance(t, FuncPointer):
        return ((),)
    if isinstance(t, Struct):
        return tuple((name,) + p for name, ft in t.fields for p in _fun_paths(ft))
    return ()


def _retype(t: Type, is_sync) -> Type:
    """`t` with each function-typed leaf flagged `is_sync(path)`."""
    if isinstance(t, FuncPointer):
        return FuncPointer(sync=is_sync(()))
    if isinstance(t, Struct) and _fun_paths(t):
        return dataclasses.replace(t, fields=tuple(
            (name, _retype(ft, lambda p, name=name: is_sync((name,) + p)))
            for name, ft in t.fields))
    return t


# A node of the flow — plain tuples. A function: ("fn", name). A function-
# typed leaf of a location, addressed by its field path within the
# location's type: ("var", fn, name, path), ("result", fn, path),
# ("field", object, field, path) — the object being the class
# representative — and ("global", name, path).
Node = tuple


@dataclasses.dataclass
class _SyncFlow:
    """The analysis state: dependency edges, the fallen set, and the lookup
    tables the edge builder needs."""
    app: Application
    virtual_impls: dict[str, tuple[str, ...]]
    field_class: dict[tuple[str, str], tuple[str, str]]
    pinned: frozenset[Node]
    dependents: dict[Node, list[Node]] = dataclasses.field(default_factory=dict)
    fallen: set[Node] = dataclasses.field(default_factory=set)
    aliases: dict[str, set[str]] = dataclasses.field(default_factory=dict)

    # ── Node naming ──────────────────────────────────────────────────────
    def field_node(self, object_name: str, field: str, path: Path) -> Node:
        return ("field",) + self.field_class.get((object_name, field), (object_name, field)) + (path,)

    def callees(self, fn_ref: RParam) -> tuple[str, ...] | None:
        """The functions a call through `fn_ref` can reach, or None when
        the IR cannot enumerate them."""
        match fn_ref:
            case GlobalFunction(name=name) if name in self.app.functions:
                return (name,)
            case VirtualFunction(name=name):
                impls = self.virtual_impls.get(name, ())
                return impls if impls and all(i in self.app.functions for i in impls) else None
        return None

    def sources(self, fn_name: str, value: RParam, path: Path) -> list[Node] | None:
        """The nodes the function-typed leaf `path` of `value` reads, or
        None when it is unknown. A null function holds no function: it
        constrains nothing."""
        match value:
            case GlobalFunction() | VirtualFunction() if path == ():
                targets = self.callees(value)
                return None if targets is None else [("fn", t) for t in targets]
            case StackVar(name=name):
                return [("var", fn_name, name, path)]
            case ObjectField(object_name=obj, field=field):
                return [self.field_node(obj, field, path)]
            case GlobalVar(name=name):
                return [("global", name, path)]
            case StructField(struct=inner, field=field):
                return self.sources(fn_name, inner, (field,) + path)
            case NewStruct(values=values) | NewStructTyped(values=values) if path:
                matching = [v for n, v in values if n == path[0]]
                return self.sources(fn_name, matching[0], path[1:]) if matching else []
            case NullPointer() | ZeroOf():
                return []
        return None

    def location(self, fn_name: str, lp: RParam, path: Path) -> Node | None:
        """The node the function-typed leaf `path` of a WRITE lands in, or
        None for a location whose reads are unknown anyway (an array
        element)."""
        match lp:
            case StackVar(name=name):
                return ("var", fn_name, name, path)
            case ObjectField(object_name=obj, field=field):
                return self.field_node(obj, field, path)
            case GlobalVar(name=name):
                return ("global", name, path)
        return None

    def own_param(self, fn_name: str, value: RParam) -> bool:
        """`value` is one of `fn_name`'s own function parameters."""
        if fn_name not in self.aliases:
            self.aliases[fn_name] = _param_aliases(self.app.functions[fn_name])
        return isinstance(value, StackVar) and value.name in self.aliases[fn_name]

    def call_sources(self, fn_name: str, op: Call) -> list[tuple[list[Node] | None, bool]]:
        """What `op` suspends through: groups of sources (None = unknown),
        each paired with whether it counts against the caller's
        maybe_async node — a group that is just the caller's own parameter
        does not."""
        targets = self.callees(op.function)
        if targets is None:
            return [(self.sources(fn_name, op.function, ()),
                     not self.own_param(fn_name, op.function))]
        groups: list[tuple[list[Node] | None, bool]] = [([("mfn", t)], True) for t in targets]
        for t in targets:
            target = self.app.functions[t]
            if target.sync:
                continue          # trusted: no argument can make it suspend
            params = target.params.fields[1:]
            fun_params = [(p, path) for p, pt in params for path in _fun_paths(pt)]
            if fun_params and not isinstance(op.parameters, NewStruct):
                groups.append((None, True))
                continue
            args = {p: arg for (_, arg), (p, _) in zip(op.parameters.values, params)} if fun_params else {}
            for p, path in fun_params:
                arg = args.get(p)
                groups.append((None if arg is None else self.sources(fn_name, arg, path),
                               not (path == () and arg is not None and self.own_param(fn_name, arg))))
        return groups

    def call_is_sync(self, fn_name: str, op: Call) -> bool:
        return all(srcs is not None and all(self.is_sync(s) for s in srcs)
                   for srcs, _ in self.call_sources(fn_name, op))

    # ── Edges ────────────────────────────────────────────────────────────
    def fall(self, node: Node) -> None:
        if node not in self.pinned:
            self.fallen.add(node)

    def flow(self, srcs: list[Node] | None, dst: Node | None) -> None:
        """`dst` falls if any of `srcs` falls; unknown sources fall it now."""
        if dst is None:
            return
        if srcs is None:
            self.fall(dst)
            return
        for src in srcs:
            self.dependents.setdefault(src, []).append(dst)

    def assign(self, fn_name: str, target: RParam, value: RParam) -> None:
        """Every function-typed leaf of `target` reads the same leaf of
        `value`."""
        for path in _fun_paths(target.get_type()):
            self.flow(self.sources(fn_name, value, path), self.location(fn_name, target, path))

    def solve(self) -> None:
        work = list(self.fallen)
        while work:
            for dst in self.dependents.get(work.pop(), ()):
                if dst not in self.fallen and dst not in self.pinned:
                    self.fallen.add(dst)
                    work.append(dst)

    def is_sync(self, node: Node) -> bool:
        return node not in self.fallen


def _param_aliases(fn: Function) -> set[str]:
    """The function-typed parameters of `fn`, and every variable whose every
    definition is a Move or Phi from one of them — the greatest such set, so
    a loop variable fed by the parameter and by itself qualifies."""
    defs: dict[str, list[RParam | None]] = {}
    for op in fn.ops:
        match op:
            case Move(target=StackVar(name=name), source=source):
                defs.setdefault(name, []).append(source)
            case Phi(target=StackVar(name=name), sources=srcs):
                defs.setdefault(name, []).extend(v for _, v in srcs)
            case _:
                for w in op.get_live_vars()[1]:
                    defs.setdefault(w.name, []).append(None)
    alias = {p for p, pt in fn.params.fields if isinstance(pt, FuncPointer) and p not in defs} | set(defs)
    changed = True
    while changed:
        changed = False
        for name, srcs in defs.items():
            if name in alias and not all(isinstance(s, StackVar) and s.name in alias for s in srcs):
                alias.discard(name)
                changed = True
    return alias


def _field_classes(objects: dict[str, Object]) -> dict[tuple[str, str], tuple[str, str]]:
    """Union the base- and derived-class views of every field holding a
    function — an `ObjectField` may name either class for the same slot —
    mapping each (object, field) to one representative."""
    parent: dict[tuple[str, str], tuple[str, str]] = {}

    def find(k: tuple[str, str]) -> tuple[str, str]:
        while parent.setdefault(k, k) != k:
            k = parent[k]
        return k

    def fun_fields(o: Object) -> set[str]:
        return {name for name, t in o.fields.fields if _fun_paths(t)}

    for o in objects.values():
        for field in fun_fields(o):
            for ancestor in o.extends:
                if ancestor in objects and field in fun_fields(objects[ancestor]):
                    a, b = find((o.name, field)), find((ancestor, field))
                    if a != b:
                        parent[max(a, b)] = min(a, b)
    return {k: find(k) for k in parent}


def _build_flow(a: Application) -> _SyncFlow:
    virtual_impls: dict[str, set[str]] = {}
    for obj in a.objects.values():
        for virtual_name, global_name in obj.functions:
            virtual_impls.setdefault(virtual_name, set()).add(global_name)

    pinned = frozenset(node for name, fn in a.functions.items() if fn.sync
                       for node in (("fn", name), ("mfn", name)))
    flow = _SyncFlow(a, {v: tuple(sorted(i)) for v, i in virtual_impls.items()},
                     _field_classes(a.objects), pinned)
    address_taken = trim.address_taken_functions(a)

    def fall_all(t: Type, node_of) -> None:
        for path in _fun_paths(t):
            flow.fall(node_of(path))

    def feed_params(callee: str, args: RParam, caller: str) -> None:
        target = a.functions[callee]
        if not isinstance(args, NewStruct):
            for p, pt in target.params.fields[1:]:
                fall_all(pt, lambda path, p=p: ("var", callee, p, path))
            return
        for (_, arg), (p, pt) in zip(args.values, target.params.fields[1:]):
            for path in _fun_paths(pt):
                flow.flow(flow.sources(caller, arg, path), ("var", callee, p, path))

    def call_edges(fn_name: str, op: Call) -> None:
        # The function can suspend iff one of its calls can.
        for srcs, counts_against_maybe in flow.call_sources(fn_name, op):
            flow.flow(srcs, ("fn", fn_name))
            if counts_against_maybe:
                flow.flow(srcs, ("mfn", fn_name))
        targets = flow.callees(op.function)
        if targets is not None:
            for t in targets:
                feed_params(t, op.parameters, fn_name)
        if op.register is not None:
            for path in _fun_paths(op.register.get_type()):
                flow.flow(None if targets is None else [("result", t, path) for t in targets],
                          flow.location(fn_name, op.register, path))

    def op_edges(fn_name: str, op: Op) -> None:
        match op:
            case Call():
                call_edges(fn_name, op)
            case Move(target=target, source=source):
                flow.assign(fn_name, target, source)
            case Phi(target=target, sources=srcs):
                for _, v in srcs:
                    flow.assign(fn_name, target, v)
            case Return(value=value):
                for path in _fun_paths(value.get_type()):
                    flow.flow(flow.sources(fn_name, value, path), ("result", fn_name, path))
            case _:
                # Any other op that defines a variable holding a function
                # (a ParallelCall slot result, …) is not modelled: unknown.
                for w in op.get_live_vars()[1]:
                    fall_all(w.get_type(), lambda path, w=w: ("var", fn_name, w.name, path))

    for name, fn in a.functions.items():
        if (fn.foreign_symbol is not None or fn.bypass_async
                or name == "__entrypoint__" or _returns_tagged_task(fn)
                or any(isinstance(op, ParallelCall) for op in fn.ops)):
            flow.fall(("fn", name))
            flow.fall(("mfn", name))
        if fn.foreign_symbol is not None:
            fall_all(fn.result, lambda path, name=name: ("result", name, path))
        if name in address_taken or fn.foreign_symbol is not None or name == "__entrypoint__":
            for p, pt in fn.params.fields:
                fall_all(pt, lambda path, name=name, p=p: ("var", name, p, path))
        for op in fn.ops:
            op_edges(name, op)

    for obj in a.objects.values():
        if obj.is_foreign:
            for field, t in obj.fields.fields:
                fall_all(t, lambda path, obj=obj, field=field: flow.field_node(obj.name, field, path))

    for gl in a.globals.values():
        if gl.init is None:
            continue
        if gl.object_name and isinstance(gl.init, NewStruct):
            # A static object instance: its initialiser stores each field.
            for field, value in gl.init.values:
                for path in _fun_paths(value.get_type()):
                    flow.flow(flow.sources("", value, path),
                              flow.field_node(gl.object_name, field, path))
        else:
            flow.assign("", GlobalVar(gl.type, gl.name), gl.init)

    flow.solve()
    return flow


def compute_sync_call_targets(a: Application) -> set[str]:
    """The functions called DIRECTLY at a call site that provably cannot
    suspend, without materialising anything — for the single-caller inline
    gate. Inlining a callee whose call can suspend merges its live set with
    the caller's, so every suspension in the merged body saves the combined
    frame; a sync SITE has no suspension to save across. For a function with
    one reference, membership says its one call site is sync — including a
    function sync only through the maybe_async calls it makes."""
    flow = _build_flow(a)
    return {op.function.name
            for name, fn in a.functions.items() for op in fn.ops
            if isinstance(op, Call) and isinstance(op.function, GlobalFunction)
            and op.function.name in a.functions and flow.call_is_sync(name, op)}


def infer_sync(a: Application) -> Application:
    flow = _build_flow(a)

    def retype_struct(struct: Struct, node_of) -> Struct:
        """Each field's function leaves flagged from `node_of(field, path)`."""
        return dataclasses.replace(struct, fields=tuple(
            (name, _retype(t, lambda path, name=name: flow.is_sync(node_of(name, path))))
            for name, t in struct.fields))

    def materialise(fn: Function) -> Function:
        def replacer(p: RParam) -> RParam:
            match p:
                case GlobalFunction() | VirtualFunction():
                    targets = flow.callees(p)
                    return dataclasses.replace(p, sync=targets is not None and all(
                        flow.is_sync(("fn", t)) for t in targets))
                case StackVar(name=name) if _fun_paths(p.type):
                    return dataclasses.replace(p, type=_retype(
                        p.type, lambda path: flow.is_sync(("var", fn.name, name, path))))
                case ObjectField(object_name=obj, field=field) if _fun_paths(p.type):
                    return dataclasses.replace(p, type=_retype(
                        p.type, lambda path: flow.is_sync(flow.field_node(obj, field, path))))
                case GlobalVar(name=name) if _fun_paths(p.type):
                    return dataclasses.replace(p, type=_retype(
                        p.type, lambda path: flow.is_sync(("global", name, path))))
            return p

        def var_node(name: str, path: Path) -> Node:
            return ("var", fn.name, name, path)

        def materialise_op(op: Op) -> Op:
            new = op.replace_params(replacer)
            # A direct or virtual callee answers for THIS call site: a
            # maybe_async callee handed only sync functions returns a value.
            if isinstance(op, Call) and isinstance(new.function, (GlobalFunction, VirtualFunction)):
                new = dataclasses.replace(new, function=dataclasses.replace(
                    new.function, sync=flow.call_is_sync(fn.name, op)))
            return new

        return dataclasses.replace(
            fn,
            sync=flow.is_sync(("fn", fn.name)),
            params=retype_struct(fn.params, var_node),
            stack_vars=retype_struct(fn.stack_vars, var_node),
            ops=tuple(materialise_op(op) for op in fn.ops))

    def materialise_object(obj: Object) -> Object:
        return dataclasses.replace(obj, fields=retype_struct(
            obj.fields, lambda field, path: flow.field_node(obj.name, field, path)))

    return dataclasses.replace(
        a,
        functions={name: materialise(fn) for name, fn in a.functions.items()},
        objects={name: materialise_object(obj) for name, obj in a.objects.items()})
