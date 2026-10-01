"""Spell equal code equally, so representation dedup finds more of it.

Dedup (lowering/representation_dedup.py) compares code as written. A
generated object's field names carry the hash of the declaration that made
them (`value@jdhwD4`), so two classes with the same layout never compare equal
— and, since merges cascade, neither does anything that refers to them. This
stage renames each generated object's fields to their position, consistently
in the object, every field access and every static initialiser. Only member
names change in the C; the layout does not. Foreign objects (declared in
yafl.h) keep their names, as do the vtable word `type` and the trailing
`array`, which the IR requires by name.

Runs just before lowering/cleanup.py and dedup. Measured on the port against
dedup alone (with cleanup): -O1 objects 1701 -> 1220; -O3 C 59.5 -> 56.1 MB.
Measured and left out (about zero): canonical evaluation order, commutative
operand order, comparison direction, move sinking, clearing post-async sync
flags, positional names in by-value structs. Off under --profile, like dedup.
"""
from __future__ import annotations

import dataclasses

import codegen.param as p
import codegen.typedecl as t
from codegen.gen import Application
from codegen.ir import Function, Global, Object


def canonicalise(app: Application) -> Application:
    """See module docstring."""
    if app.profile:
        return app
    fields = _FieldRenames(app)
    return dataclasses.replace(
        app,
        objects={n: fields.object(x) for n, x in app.objects.items()},
        functions={n: fields.function(x) for n, x in app.functions.items()},
        globals={n: fields.global_(x) for n, x in app.globals.items()})


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
