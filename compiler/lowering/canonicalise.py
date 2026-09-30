"""Spell equal code equally, so representation dedup finds more of it.

Dedup (lowering/representation_dedup.py) compares code as written. Two
instances of the same generic can differ only in what the representation of
the program leaves behind, and that is enough to keep them apart — and, since
merges cascade, everything that refers to them apart with them. This stage
removes two such differences. It changes no behaviour and runs just before
dedup, after every other IR pass.

DEBRIS. The optimiser leaves copies it never propagated, unreachable ops,
jumps to the next label, repeated subexpressions, and locals declared for ops
since deleted. C emission cleans
each function up with a fixed chain (lower_phis, strip_unused_operations,
simplify_control_flow, fold_struct_fields, copy_propagate,
eliminate_common_subexpressions). The same chain runs here, before dedup, and
the locals it leaves unused are dropped from the declarations, which dedup
compares as a set. Emission then finds nothing more to do: the code is what it
would have emitted anyway.

OBJECT FIELD NAMES. A generated object's field names carry the hash of the
declaration that made them (`value@jdhwD4`), so two classes with the same
layout never compare equal. Each generated object's fields are renamed to
their position, consistently in the object and in every field access and
static initialiser. Only member names change in the C; the layout does not.
Foreign objects (declared in yafl.h) keep their names, as do the vtable word
`type` and the trailing `array`, which the IR requires by name.

Measured on the port against dedup alone: -O1 objects 1701 -> 1220 and
functions 9255 -> 8745; -O3 C 59.5 -> 56.1 MB, .text 6.83 -> 6.68 MB.
Measured and left out (about zero): canonical evaluation order, commutative
operand order, comparison direction, move sinking, clearing post-async sync
flags, positional names in by-value structs. Off under --profile, like dedup.
"""
from __future__ import annotations

import dataclasses

import codegen.ops as o
import codegen.param as p
import codegen.typedecl as t
from codegen.gen import Application
from codegen.ir import Function, Global, Object


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def canonicalise(app: Application) -> Application:
    """See module docstring."""
    if app.profile:
        return app
    fields = _FieldRenames(app)
    return dataclasses.replace(
        app,
        objects={n: fields.object(x) for n, x in app.objects.items()},
        functions={n: fields.function(_cleaned(x)) for n, x in app.functions.items()},
        globals={n: fields.global_(x) for n, x in app.globals.items()})


# ---------------------------------------------------------------------------
# Debris: the emitter's own cleanups, then unused declarations
# ---------------------------------------------------------------------------

def _cleaned(fn: Function) -> Function:
    if fn.foreign_symbol or not fn.ops:
        return fn
    fn = (fn.lower_phis().strip_unused_operations().simplify_control_flow()
            .fold_struct_fields().copy_propagate().simplify_control_flow()
            .eliminate_common_subexpressions())
    used = _mentioned_locals(fn)
    kept = tuple((n, ty) for n, ty in fn.stack_vars.fields if n in used)
    if len(kept) == len(fn.stack_vars.fields):
        return fn
    return dataclasses.replace(fn, stack_vars=t.Struct(kept))


def _mentioned_locals(fn: Function) -> set[str]:
    names = {n for n, _ in fn.params.fields}
    for op in fn.ops:
        names |= {v.name for v in op.saved_vars}
        for q in op.all_params():
            names |= {r.name for r in q.flatten() if isinstance(r, p.StackVar)}
        for written in (getattr(op, "target", None), getattr(op, "register", None),
                        getattr(op, "task_lhs", None), getattr(op, "call_id_lhs", None)):
            if isinstance(written, p.StackVar):
                names.add(written.name)
        if isinstance(op, o.ParallelCall):
            names |= {v.name for v in op.results}
    return names


# ---------------------------------------------------------------------------
# Object field names by position
# ---------------------------------------------------------------------------

_KEPT_FIELD_NAMES = frozenset({"type", "array"})


class _FieldRenames:
    def __init__(self, app: Application):
        self.renames: dict[str, dict[str, str]] = {
            name: {f: f if f in _KEPT_FIELD_NAMES else f"$f{i}"
                   for i, (f, _) in enumerate(obj.fields.fields)}
            for name, obj in app.objects.items() if not obj.is_foreign}

    def object(self, obj: Object) -> Object:
        r = self.renames.get(obj.name)
        if r is None:
            return obj
        return dataclasses.replace(
            obj, fields=t.ImmediateStruct(tuple((r[f], ty) for f, ty in obj.fields.fields)),
            length_field=obj.length_field and r[obj.length_field])

    def function(self, fn: Function) -> Function:
        ops = tuple(op.replace_params(self.access) for op in fn.ops)
        return fn if ops == fn.ops else dataclasses.replace(fn, ops=ops)

    def global_(self, gv: Global) -> Global:
        if gv.init is None:
            return gv
        init = gv.init.replace_params(self.access)
        r = self.renames.get(gv.object_name) if gv.object_name else None
        if r is not None and isinstance(init, p.NewStruct):
            init = p.NewStruct(tuple((r.get(n, n), v) for n, v in init.values))
        return gv if init == gv.init else dataclasses.replace(gv, init=init)

    def access(self, x: p.RParam) -> p.RParam:
        if isinstance(x, (p.ObjectField, p.ArrayElement)):
            r = self.renames.get(x.object_name)
            if r is not None:
                if isinstance(x, p.ArrayElement):
                    return dataclasses.replace(x, field=r.get(x.field, x.field),
                                               length_field=r.get(x.length_field, x.length_field))
                return dataclasses.replace(x, field=r.get(x.field, x.field))
        return x
