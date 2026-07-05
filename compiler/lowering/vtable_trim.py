"""Drop vtable entries whose slot no surviving virtual call dispatches.

After devirtualisation, a single-implementation slot is only ever called
directly; its vtable entry is dead weight — in a whole-program build
nothing can dispatch it later — yet it still counts as a function
reference, blocking the single-caller fold. Dropping the entry lets the
fold + trim cascade collapse witness objects whose every method went
direct: entry gone → refcount 1 → fold → the witness `this` goes dead →
deadstores + trim remove the instance, its object and its whole vtable.
Instance/`implements` checks are untouched (they use implements_array,
not the function table)."""
from __future__ import annotations

import dataclasses

from codegen.gen import Application
from codegen.ir import Object
from codegen.param import VirtualFunction


def trim_unused_vtable_slots(app: Application) -> Application:
    """See module docstring."""
    used: set[str] = set()
    for fn in app.functions.values():
        for op in fn.ops:
            for p in op.all_params():
                for q in p.flatten():
                    if isinstance(q, VirtualFunction):
                        used.add(q.name)
    for gv in app.globals.values():
        if gv.init is not None:
            for q in gv.init.flatten():
                if isinstance(q, VirtualFunction):
                    used.add(q.name)

    changed = False
    new_objects: dict[str, Object] = {}
    for name, obj in app.objects.items():
        kept = tuple((slot, target) for slot, target in obj.functions if slot in used)
        if len(kept) != len(obj.functions):
            changed = True
            new_objects[name] = dataclasses.replace(obj, functions=kept)
        else:
            new_objects[name] = obj
    return dataclasses.replace(app, objects=new_objects) if changed else app
