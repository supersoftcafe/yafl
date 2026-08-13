"""Resolve relocation before touching a [pinnable] object's fields.

An ordinary immutable object needs no read barrier: every copy of one holds
the same bytes for ever, which is precisely why a field access is a plain
`->` with nothing around it. A [pinnable] object is immutable EXCEPT inside a
late pin, and that write lands on the live copy alone — so a pointer taken
before a relocation reads the pre-write bytes.

Cross-thread that would be tolerable: a reader that has not yet seen another
thread's publication is indistinguishable from one that ran a moment earlier,
and no ordering was promised. Within ONE thread it is not. A walk that reads
a field, and later reads the same field of the same logical object through a
pointer it was already holding, must not get two different answers — no
caller can defend against that, and it is exactly the inconsistency the
memoize contract exists to rule out.

So every access to a [pinnable] class's fields resolves first: the access's
pointer is wrapped in `object_resolve`, which emits as an ordinary call
around whatever expression the pointer already was.

ONE PLACE ON PURPOSE. There are forty-odd sites that build an ObjectField,
most of them for compiler-internal classes (lazy stubs, task frames, union
representations) that are never [pinnable]. Wrapping at those sites would
mean auditing every one and re-auditing whenever a new one appears, and a
missed site is a silent stale read rather than a compile error. Rewriting
here — over every ObjectField in the finished program, keyed on the object
registry — cannot miss one.

Wrapping the POINTER rather than flagging the access is deliberate: it needs
no new field on ObjectField, so neither compiler has to touch its forty-odd
positional construction sites, and emission stays untouched.

Runs late, after every pass that can introduce an ObjectField, and after
stack promotion (which deletes accesses to non-escaping objects: those need
no resolve, having never been shared, and a [pinnable] object cannot be
promoted anyway — pinning one means passing it to the publish primitive, and
any call argument escapes).
"""
from __future__ import annotations

import dataclasses

import codegen.typedecl as t
from codegen.gen import Application
from codegen.param import NewStruct, ObjectField, RParam, RuntimeInvoke


def resolve_pinnable_reads(app: Application) -> Application:
    pinnable = {name for name, obj in app.objects.items() if obj.is_pinnable}
    if not pinnable:
        return app

    def rewrite(p: RParam) -> RParam:
        # A FRESH store needs no resolve: the object was allocated moments ago
        # on a thread-private page, straight-line before this store, so it
        # cannot have been relocated yet.
        if (isinstance(p, ObjectField) and p.object_name in pinnable
                and not p.fresh
                and not isinstance(p.pointer, RuntimeInvoke)):
            resolved = RuntimeInvoke("object_resolve",
                                     NewStruct((("o", p.pointer),)),
                                     t.DataPointer())
            return dataclasses.replace(p, pointer=resolved)
        return p

    new_functions = {name: dataclasses.replace(fn, ops=tuple(
                         op.replace_params(rewrite) for op in fn.ops))
                     for name, fn in app.functions.items()}
    return dataclasses.replace(app, functions=new_functions)
