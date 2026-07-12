"""Eliminate provably-in-range array bounds checks.

clang's loop vectoriser refuses any loop containing the `array_bounds_check`
abort branch ("control flow cannot be substituted for a select"), so a checked
read in a hot loop forfeits SIMD no matter what flags are used. This pass
proves the canonical counted-loop shape in range and flips the ArrayElement's
`checked` flag; everything unproven keeps its check.

The proof, per loop region (a Label with a later back-edge Jump to it):

  * the region's Phis classify as INVARIANT (the back edge feeds the value
    back unchanged) or INDUCTION (the back edge feeds `int32_add(self, 1)`);
  * a guard shows the induction variable is below a bound inside the body —
    either `JumpIf(exit, int32_test_eq(i, n))` (the [tail]-loop shape: exit
    exactly at n, so i < n inside given i starts at 0 and steps by +1) or
    `JumpIf(body, int32_test_lt(i, n))` (the array-fill shape);
  * the bound resolves to an ObjectField load of the SAME array's length
    field that the read indexes (lengths are non-negative by construction,
    which the eq-exit shape needs).

Runs after ALL IR inlining (the kernel's caller supplies the `0` start and
the `a.length` bound, so the proof usually only completes once the loop is
inlined into it) and before async lowering (the state-machine copy inherits
the flipped flags).
"""
from __future__ import annotations

import dataclasses

from codegen.gen import Application
from codegen.ir import Function
from codegen.ops import Op, Call, Return, Move, Label, Jump, JumpIf, Phi, NewObject
from codegen.param import (RParam, StackVar, ObjectField, ArrayElement,
                           Integer, RuntimeInvoke, NewStruct, StructField)


_OPAQUE = ("opaque",)


def _single_defs(ops: tuple[Op, ...]) -> dict[str, RParam | Phi]:
    """StackVar name → its unique definition (a Move source, or the Phi op).
    Multi-defined names are dropped: resolution must not guess."""
    counts: dict[str, int] = {}
    defs: dict[str, RParam | Phi] = {}

    def seen(name: str, value) -> None:
        counts[name] = counts.get(name, 0) + 1
        defs[name] = value

    for op in ops:
        if isinstance(op, Move) and isinstance(op.target, StackVar):
            seen(op.target.name, op.source)
        elif isinstance(op, Phi) and isinstance(op.target, StackVar):
            seen(op.target.name, op)
        elif isinstance(op, Call) and isinstance(op.register, StackVar):
            seen(op.register.name, _OPAQUE)
        elif isinstance(op, NewObject) and isinstance(op.register, StackVar):
            seen(op.register.name, _OPAQUE)
    return {n: v for n, v in defs.items() if counts[n] == 1}


def _field_stores(ops: tuple[Op, ...], res: "_Resolver") -> dict[tuple, tuple]:
    """(base_id, field) → stored value id, for object fields stored exactly
    once (an array's length field is: written at creation, immutable after).
    Lets a length LOAD resolve to the value it was created with, so a guard
    bound of `n` also covers a second array whose length was stored from the
    same `n`."""
    counts: dict[tuple, int] = {}
    stores: dict[tuple, tuple] = {}
    for op in ops:
        if (isinstance(op, Move) and isinstance(op.target, ObjectField)
                and op.target.index is None):
            key = (res.resolve(op.target.pointer), op.target.field)
            counts[key] = counts.get(key, 0) + 1
            stores[key] = res.resolve(op.source)
    return {k: v for k, v in stores.items() if counts[k] == 1 and k[0] != _OPAQUE}


class _Resolver:
    """Canonical value ids over the single-def graph. An INVARIANT Phi is
    transparent (resolves to its entry value); an INDUCTION Phi is its own
    id. Cycles resolve to opaque."""

    def __init__(self, defs: dict[str, RParam | Phi]):
        self.defs = defs
        self.inductions: set[str] = set()
        self._memo: dict[str, tuple] = {}

    def resolve(self, rp: RParam, _visiting: frozenset[str] = frozenset()) -> tuple:
        if isinstance(rp, Integer):
            return ("int", rp.value, rp.precision)
        if isinstance(rp, ObjectField):
            return ("field", self.resolve(rp.pointer, _visiting), rp.field)
        if isinstance(rp, RuntimeInvoke):
            args = rp.parameters
            arg_ids = (tuple(self.resolve(v, _visiting) for _, v in args.values)
                       if isinstance(args, NewStruct) else _OPAQUE)
            return ("invoke", rp.function, arg_ids)
        if isinstance(rp, StructField):
            inner = rp.struct
            if isinstance(inner, StackVar):
                d = self.defs.get(inner.name)
                if isinstance(d, NewStruct):
                    val = next((v for n, v in d.values if n == rp.field), None)
                    if val is not None:
                        return self.resolve(val, _visiting)
            return _OPAQUE
        if not isinstance(rp, StackVar):
            return _OPAQUE
        name = rp.name
        if name in self._memo:
            return self._memo[name]
        if name in _visiting:
            # A reference back to a value currently being resolved — the Phi
            # classification below matches on this marker.
            return ("cycle", name)
        d = self.defs.get(name)
        if d is None:
            out = ("var", name)     # parameter or multi-def: stable identity
        elif d is _OPAQUE:
            out = ("var", name)     # call result: unknown but a fixed value
        elif isinstance(d, Phi):
            out = self._resolve_phi(name, d, _visiting | {name})
        else:
            out = self.resolve(d, _visiting | {name})
        if not _visiting:
            # Results computed mid-cycle can contain ("cycle", …) markers that
            # are only meaningful to the enclosing Phi — never memoise them.
            self._memo[name] = out
        return out

    def _resolve_phi(self, name: str, phi: Phi, visiting: frozenset[str]) -> tuple:
        if len(phi.sources) != 2:
            return _OPAQUE
        ids = [self.resolve(v, visiting) for _, v in phi.sources]
        cycle = ("cycle", name)
        for k in (0, 1):
            back, entry = ids[k], ids[1 - k]
            if back == cycle:
                # Invariant: the back edge feeds the value straight through.
                return entry
            if (back[0] == "invoke" and back[1] == "int32_add"
                    and len(back[2]) == 2
                    and cycle in back[2]
                    and ("int", 1, 32) in back[2]):
                self.inductions.add(name)
                # Entry value recorded for the guard check.
                self._entry = getattr(self, "_entry", {})
                self._entry[name] = entry
                return ("induction", name)
        return _OPAQUE

    def entry_of(self, induction_name: str) -> tuple | None:
        return getattr(self, "_entry", {}).get(induction_name)


def _loop_regions(ops: tuple[Op, ...]) -> list[tuple[int, int]]:
    label_at = {op.name: i for i, op in enumerate(ops) if isinstance(op, Label)}
    return [(label_at[op.name], i) for i, op in enumerate(ops)
            if isinstance(op, Jump) and op.name in label_at and label_at[op.name] < i]


def _guarded_bounds(ops, lo: int, hi: int, res: _Resolver) -> list[tuple[tuple, tuple]]:
    """(induction_id, bound_id) pairs proven `induction < bound` inside the
    region's body. The key question per guard is which truth value of its
    condition ENTERS the body (branch-threading freely rewrites shape and
    inverts conditions, so the raw dialect can't be pattern-matched):

      * body sees `int32_test_lt(i, n)` TRUE  → i < n directly;
      * body sees `int32_test_eq(i, n)` FALSE → i < n, provided i counts up
        from exactly 0 by +1 (it must hit n before passing it) and n is a
        length (non-negative — the caller checks n is a length-field load).
    """
    label_at = {op.name: i for i, op in enumerate(ops) if isinstance(op, Label)}
    out: list[tuple[tuple, tuple]] = []
    for i in range(lo, hi):
        op = ops[i]
        if not isinstance(op, JumpIf):
            continue
        cond = res.resolve(op.condition)
        if cond[0] != "invoke" or len(cond[2]) != 2:
            continue
        target = label_at.get(op.label)
        inside = target is not None and lo <= target <= hi
        if inside:
            # Body entered by TAKING the branch — but only a guard if the
            # fall-through immediately leaves the region.
            nxt = ops[i + 1] if i + 1 <= hi else None
            nxt_target = label_at.get(nxt.name) if isinstance(nxt, Jump) else None
            if nxt_target is not None and lo <= nxt_target <= hi:
                continue
            if not isinstance(nxt, Jump):
                continue
            body_truth = not op.invert
        else:
            # Body entered by FALLING THROUGH the exit branch.
            body_truth = op.invert
        a, b = cond[2]
        for x, y in ((a, b), (b, a)):
            if x[0] != "induction":
                continue
            if cond[1] == "int32_test_eq" and body_truth is False:
                if res.entry_of(x[1]) == ("int", 0, 32):
                    out.append((x, y))
            elif (cond[1] == "int32_test_lt" and body_truth is True
                  and (x, y) == (a, b)):
                out.append((x, y))  # lt is not symmetric: only i < n, as written
    return out


def _eliminate_in_function(fn: Function) -> Function:
    defs = _single_defs(fn.ops)
    res = _Resolver(defs)
    stores = _field_stores(fn.ops, res)
    replaced = [False]

    for lo, hi in _loop_regions(fn.ops):
        proven = _guarded_bounds(fn.ops, lo, hi, res)
        if not proven:
            continue

        def flip(rp: RParam) -> RParam:
            if not (isinstance(rp, ArrayElement) and rp.checked):
                return rp
            idx = res.resolve(rp.index)
            ptr = res.resolve(rp.pointer)
            if idx == _OPAQUE or ptr == _OPAQUE:
                return rp
            # This array's length, as a value id: the load form, or — when
            # the array was created here — the value its length was stored
            # from (arrays are immutable; one store, at creation).
            length_ids = {("field", ptr, rp.length_field)}
            stored = stores.get((ptr, rp.length_field))
            if stored is not None:
                length_ids.add(stored)
            for ind, bound in proven:
                bound_ids = {bound}
                if bound[0] == "field" and (bound[1], bound[2]) in stores:
                    # The guard's bound is itself a length load — its stored
                    # value is the same number.
                    bound_ids.add(stores[(bound[1], bound[2])])
                if idx == ind and not _OPAQUE in bound_ids and (length_ids & bound_ids):
                    replaced[0] = True
                    return dataclasses.replace(rp, checked=False)
            return rp

        new_ops = []
        for i, op in enumerate(fn.ops):
            if lo <= i <= hi and isinstance(op, (Move, Call, Return, JumpIf, Phi)):
                if isinstance(op, Move):
                    op = dataclasses.replace(op, source=op.source.replace_params(flip))
                elif isinstance(op, Call):
                    op = dataclasses.replace(op, parameters=op.parameters.replace_params(flip),
                                             function=op.function.replace_params(flip))
                elif isinstance(op, Return):
                    op = dataclasses.replace(op, value=op.value.replace_params(flip))
                elif isinstance(op, JumpIf):
                    op = dataclasses.replace(op, condition=op.condition.replace_params(flip))
                elif isinstance(op, Phi):
                    op = dataclasses.replace(op, sources=tuple(
                        (l, v.replace_params(flip)) for l, v in op.sources))
            new_ops.append(op)
        fn = dataclasses.replace(fn, ops=tuple(new_ops))

    return fn


def eliminate_provable_bounds_checks(app: Application) -> Application:
    return dataclasses.replace(app, functions={
        name: _eliminate_in_function(fn) for name, fn in app.functions.items()})
