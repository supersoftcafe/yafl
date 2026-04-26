"""
Sync inference pass.

After inlining and before CPS conversion, propagate the `sync` guarantee to
functions that can be proven to never suspend:

  Seed
  ----
  * Functions already marked [sync] by the programmer.
  * Non-foreign functions with zero non-tail Call ops (leaf functions that
    therefore return directly without ever entering the task scheduler).
    Foreign functions are excluded from this path because they have empty
    bodies; their sync-ness is determined solely by the programmer-supplied
    [sync] attribute.

  Propagation
  -----------
  A function F is sync if every non-tail Call in its body is sync.
  A Call is sync if:
    * Its target is a GlobalFunction whose name is in the sync set, OR
    * Its target is a VirtualFunction and every object that provides an
      implementation for that virtual name (via Object.functions) is also in
      the sync set.  An empty implementation set is treated conservatively
      (not sync), to avoid incorrectly promoting truly-abstract virtual calls.

  The fixed-point loop iterates until no new functions are added.

  Materialisation
  ---------------
  After convergence, every Function whose name is in the sync set gets
  fn.sync = True. The CPS pass uses fn.sync to decide what the cold
  $asynccommon block does: a sync function emits Abort there (it cannot
  legally suspend), an async function does the state save + task creation
  + tagged-task return. Per-Call optimisation does not exist — every
  non-tail Call uniformly receives an IfTask check, so a misclassified
  callee that suspends aborts cleanly rather than corrupting state.
"""

from __future__ import annotations

import dataclasses

from codegen.gen import Application
from codegen.things import Function
from codegen.ops import Call
from codegen.param import GlobalFunction, VirtualFunction


def infer_sync(a: Application) -> Application:
    # ------------------------------------------------------------------
    # 1. Build virtual implementation map from ALL objects (incl. foreign)
    # ------------------------------------------------------------------
    # virtual_impls[virtual_name] = {global_function_name, ...}
    virtual_impls: dict[str, set[str]] = {}
    for obj in a.objects.values():
        for virtual_name, global_name in obj.functions:
            virtual_impls.setdefault(virtual_name, set()).add(global_name)

    # ------------------------------------------------------------------
    # 2. Seed the sync set
    # ------------------------------------------------------------------
    def _has_no_nontail_calls(fn: Function) -> bool:
        return not any(
            isinstance(op, Call) and not op.musttail
            for op in fn.ops
        )

    sync_set: set[str] = {
        name
        for name, fn in a.functions.items()
        if fn.sync or (fn.foreign_symbol is None and _has_no_nontail_calls(fn))
    }

    # ------------------------------------------------------------------
    # 3. Helper: is a single Call op provably sync given current sync_set?
    # ------------------------------------------------------------------
    def _call_is_sync(op: Call) -> bool:
        fn_ref = op.function
        if isinstance(fn_ref, GlobalFunction):
            return fn_ref.name in sync_set
        if isinstance(fn_ref, VirtualFunction):
            impls = virtual_impls.get(fn_ref.name)
            return bool(impls) and all(impl in sync_set for impl in impls)
        return False

    # ------------------------------------------------------------------
    # 4. Fixed-point propagation
    # ------------------------------------------------------------------
    # Only non-foreign functions participate in propagation.  Foreign functions
    # have empty bodies, so all([]) would incorrectly qualify them as sync.
    # Their sync-ness is determined solely by the programmer-supplied [sync]
    # attribute (handled in the seed above).
    changed = True
    while changed:
        changed = False
        for name, fn in a.functions.items():
            if name in sync_set:
                continue
            if fn.foreign_symbol is not None:
                continue
            non_tail_calls = [op for op in fn.ops if isinstance(op, Call) and not op.musttail]
            if all(_call_is_sync(op) for op in non_tail_calls):
                sync_set.add(name)
                changed = True

    # ------------------------------------------------------------------
    # 5. Materialise: update fn.sync only. Call ops are uniformly emitted
    # by CPS — there is no per-Call optimisation. fn.sync only changes
    # what the cold $asynccommon block does (state save vs. abort).
    # ------------------------------------------------------------------
    new_functions: dict[str, Function] = {
        name: dataclasses.replace(fn, sync=(name in sync_set))
        for name, fn in a.functions.items()
    }

    return dataclasses.replace(a, functions=new_functions)
