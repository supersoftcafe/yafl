"""Resolve dispatch on statically-known tags (case-of-known-constructor).

After fusion, a union packed with a constant `$tag` is dispatched on a few ops
later; in SSA the tag is statically decidable (lowering/ssa_defs.py), so the
`JumpIf` hardens to an unconditional `Jump` (taken) or evaporates (never
taken). The dead pack then falls to deadstores, and the straightened flow lets
branch threading collapse further. Runs in the pre-async fixpoint at -O1+.

Phi-safe: no labels renamed or removed; a hardened/dropped JumpIf can strand
its other edge as unreachable code — harmless (never executes; trim/emission
strip it), and ssa_validate polices the result on both sides of async
lowering.
"""
from __future__ import annotations

import dataclasses

from codegen.gen import Application
from codegen.ops import Op, JumpIf, Jump
from lowering.ssa_defs import single_defs, static_int


def resolve_known_tags(app: Application) -> Application:
    new_functions = {}
    for name, fn in app.functions.items():
        defs = single_defs(fn)
        new_ops: list[Op] = []
        folded = False
        for op in fn.ops:
            if isinstance(op, JumpIf):
                cond = static_int(op.condition, defs)
                if cond is not None:
                    folded = True
                    taken = bool(cond) != bool(op.invert)
                    if taken:
                        new_ops.append(Jump(op.label))
                    continue    # never taken: the guard evaporates
            new_ops.append(op)
        result = dataclasses.replace(fn, ops=tuple(new_ops))
        # Hardening a conditional to an unconditional jump can make a whole
        # arm unreachable; drop it so its references (e.g. the dropped arm of
        # a folded ternary of lambdas) stop pinning otherwise-dead functions
        # against the reachability prune.
        if folded:
            result = result.strip_unused_operations()
        new_functions[name] = result
    return dataclasses.replace(app, functions=new_functions)
