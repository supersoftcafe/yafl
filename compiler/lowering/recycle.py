"""Recycle objects that die unpublished — OPT-IN PROTOTYPE (YAFL_RECYCLE=1).

A transient heap object costs the collector in proportion to the PAGES it
consumes, not the time it lives: collection is paced by page allocation
(yafllib/object.c, "PACING"). This stage finds objects this function
allocated, never let go of, and has finished with, and hands each one back to
the runtime at the point it dies (`yafl_recycle`, yafllib/yafl.h). The next
allocation of the same size takes the slot instead of moving the bump
pointer, so a loop that replaces one object with the next runs in two slots
instead of marching across the heap.

The runtime side decides only whether the COLLECTOR can tolerate the reuse
(the slot must be on one of this thread's pages since its last root scan,
which no cycle has seen). This side owns the hard part — that nothing else
can still reach the object. A wrong answer here is a use-after-free;
YAFL_RECYCLE_POISON makes the runtime poison instead of reuse, so the suite
can hunt for one.

THE PROOF (per function, on SSA, before phi_removal):

  * Objects, not names. A copy `Move(t, s)` between locals keeps the same
    object, so locals are grouped into COPY WEBS (union-find); each web has
    one ORIGIN — the one non-copy definition. Only two origins can be owned:
      - `NewObject` of an immutable, non-arrayed, non-pinnable, non-foreign
        class: this function created it;
      - a `Phi`: owned on the edges whose incoming web is owned. That is a
        runtime fact (a tail loop seeded by a caller's value is unowned on
        entry, owned from the first back edge), so it travels in a parallel
        Bool Phi — the OWNERSHIP FLAG — and the free is `yafl_recycle_if`.
  * Never published. Reading a FIELD of the object is fine. Anything that
    lets the bare pointer go anywhere else — a store, a struct pack, a call
    argument, a return, a runtime call, a capture — disqualifies the web for
    good (`_bare`: lowering/escapes.py's `bare_pointer_in`, except that a
    discriminator read or is-instance test is a read). A Phi source
    is not a publication but a TRANSFER to the Phi's web, valid only if the
    source web is dead past the edge (else two names hold it: disqualified).
  * Not across a suspension. A web live across a call that may suspend is
    saved into the async frame, a heap object outliving the free; it is
    disqualified rather than reasoned about.
  * Freed exactly where it dies. Web liveness (backward, op-granular, Phi
    sources as uses on their edge) gives every point where the web stops
    being live on some path that did not transfer it. After a non-
    terminator: free right there. A branch whose condition reads the dying
    web (or a Return reading its field): the operand is computed into a
    temp first, then freed, then the branch. On a branch EDGE (live on one
    successor, not the other): freed at the head of the dead successor if
    that is its only predecessor — otherwise left to the collector (counted
    as missed; edge splitting would recover it).

Interprocedural ownership (consumed parameters, owned returns) is the next
step and is NOT here: a web whose origin is a parameter or a call result is
never owned in this prototype.
"""
from __future__ import annotations

import dataclasses
import os
import sys

from codegen.gen import Application
from codegen.ir import Function
from codegen.ops import (
    Op, Label, Move, Jump, JumpIf, SwitchJump, NewObject, Call, ParallelCall,
    Return, ReturnVoid, Abort, Phi,
)
from codegen.param import (
    RParam, StackVar, NewStruct, RuntimeInvoke, Integer, ObjectField,
    VtableDiscriminator, ObjVtableEq,
)
from codegen import typedecl as t
from lowering.uninit_check import _build_label_index, _successors

ENABLED = os.environ.get("YAFL_RECYCLE", "") not in ("", "0")
DEFINE = "YAFL_RECYCLE 1"
_DEBUG = os.environ.get("YAFL_RECYCLE_DEBUG", "") not in ("", "0")

_BOOL = t.Int(8)
_TERMINATORS = (Return, ReturnVoid, Abort, Jump, JumpIf, SwitchJump)


def _is_terminator(op: Op) -> bool:
    return isinstance(op, _TERMINATORS) or (isinstance(op, Call) and op.musttail)


def _ptr_var(p: RParam) -> bool:
    return isinstance(p, StackVar) and isinstance(p.type, t.DataPointer)


def _eligible_class(app: Application, name: str) -> bool:
    obj = app.objects.get(name)
    return (obj is not None and not obj.is_mutable and not obj.is_foreign
            and not obj.is_pinnable and obj.length_field is None)


def _bare(param: RParam | None, name: str) -> bool:
    """`escapes.bare_pointer_in`, made precise for the two header READS that
    match lowering wraps around an object — a discriminator read and an
    is-instance test. Neither lets the pointer go anywhere, and treating them
    as publication would disqualify every object a `match` looks at. Every
    other compound is searched child by child; any child that IS the pointer
    publishes it (a call argument, a struct pack, a closure's environment, a
    virtual lookup's receiver...)."""
    if param is None:
        return False
    if isinstance(param, StackVar):
        return param.name == name
    if isinstance(param, (VtableDiscriminator, ObjVtableEq)):
        v = param.value
        return False if (isinstance(v, StackVar) and v.name == name) else _bare(v, name)
    if isinstance(param, ObjectField):
        base_ok = isinstance(param.pointer, StackVar) and param.pointer.name == name
        return (not base_ok and _bare(param.pointer, name)) or _bare(param.index, name)
    for f in dataclasses.fields(param):
        v = getattr(param, f.name)
        if isinstance(v, RParam):
            if _bare(v, name):
                return True
        elif isinstance(v, tuple):
            for item in v:
                for x in (item if isinstance(item, tuple) else (item,)):
                    if isinstance(x, RParam) and _bare(x, name):
                        return True
    return False


def _publishes(op: Op, name: str) -> bool:
    """Does `op` let the bare pointer held in local `name` escape? Copies
    between pointer locals and Phi edges are handled by the caller."""
    if isinstance(op, Move):
        if isinstance(op.target, StackVar):
            return _bare(op.source, name)
        # A store INTO the object (its own construction) passes the pointer
        # only as the base; a store of it anywhere else publishes it.
        tgt = op.target
        base_is_it = isinstance(getattr(tgt, "pointer", None), StackVar) and tgt.pointer.name == name
        if base_is_it:
            return _bare(op.source, name) or _bare(getattr(tgt, "index", None), name)
        return (_bare(op.source, name)
                or any(sv.name == name for sv in tgt.get_live_vars()))
    if isinstance(op, Call):
        reg = op.register
        return (_bare(op.function, name) or _bare(op.parameters, name)
                or (reg is not None and not isinstance(reg, StackVar)
                    and any(sv.name == name for sv in reg.get_live_vars())))
    if isinstance(op, Return):
        return _bare(op.value, name)
    if isinstance(op, (JumpIf, SwitchJump)):
        return _bare(op.condition, name)
    if isinstance(op, NewObject):
        return _bare(op.size, name)
    return any(sv.name == name for sv in op.get_live_vars()[0])


def _why(op: Op, name: str) -> str:
    """Debug label for the op that published `name` (YAFL_RECYCLE_DEBUG)."""
    if isinstance(op, Return):
        return "returned"
    if isinstance(op, Call):
        return "call-arg(direct)" if op.is_direct_call() else "call-arg(indirect)"
    if isinstance(op, Move):
        if not isinstance(op.target, StackVar):
            return "stored-into-heap"
        if isinstance(op.source, RuntimeInvoke):
            return f"runtime:{op.source.function}"
        if isinstance(op.source, NewStruct):
            return "packed-in-struct"
        return f"move:{type(op.source).__name__}"
    return type(op).__name__


class _Stats:
    new_webs = 0
    reasons: dict[str, int] = {}
    functions = 0
    webs = 0
    frees = 0
    reuses = 0
    missed_edges = 0


def _rewrite(fn: Function, app: Application, optimization_level: int) -> Function:
    ops = fn.ops
    n = len(ops)
    if n == 0:
        return fn

    # ── copy webs ────────────────────────────────────────────────────────
    defs: dict[str, list[int]] = {}
    for i, op in enumerate(ops):
        for sv in op.get_live_vars()[1]:
            defs.setdefault(sv.name, []).append(i)
    ptr_names: set[str] = set()
    for i, op in enumerate(ops):
        for p in op.all_params():
            if _ptr_var(p):
                ptr_names.add(p.name)
    params = {name for name, _ in fn.params.fields}

    parent: dict[str, str] = {}

    def find(x: str) -> str:
        root = x
        while parent.get(root, root) != root:
            root = parent[root]
        while parent.get(x, x) != root:
            parent[x], x = root, parent[x]
        return root

    is_copy: set[int] = set()
    for i, op in enumerate(ops):
        if (isinstance(op, Move) and not op.keep and _ptr_var(op.target) and _ptr_var(op.source)
                and len(defs.get(op.target.name, ())) == 1 and op.target.name not in params):
            is_copy.add(i)
            parent[find(op.target.name)] = find(op.source.name)

    members: dict[str, list[str]] = {}
    for nm in ptr_names:
        members.setdefault(find(nm), []).append(nm)

    # Each web's origin: its single non-copy definition.
    origin: dict[str, tuple[str, int, str]] = {}   # web -> (kind, op index, origin var)
    for web, names in members.items():
        if any(nm in params or len(defs.get(nm, ())) != 1 for nm in names):
            continue
        roots = [(nm, defs[nm][0]) for nm in names if defs[nm][0] not in is_copy]
        if len(roots) != 1:
            continue
        nm, i = roots[0]
        op = ops[i]
        if (isinstance(op, NewObject) and op.size is None and _ptr_var(op.register)
                and op.register.name == nm and _eligible_class(app, op.name)):
            origin[web] = ("new", i, nm)
        elif isinstance(op, Phi) and _ptr_var(op.target) and op.target.name == nm:
            origin[web] = ("phi", i, nm)
    if not origin:
        return fn

    webs = sorted(origin)
    bit = {w: 1 << k for k, w in enumerate(webs)}
    web_of = {nm: find(nm) for nm in ptr_names if find(nm) in bit}

    def web_bits(names) -> int:
        b = 0
        for nm in names:
            w = web_of.get(nm)
            if w is not None:
                b |= bit[w]
        return b

    # ── CFG with Phi-edge uses ───────────────────────────────────────────
    labels = _build_label_index(ops)
    block_label: list[str | None] = []
    cur: str | None = None
    for op in ops:
        if isinstance(op, Label):
            cur = op.name
        block_label.append(cur)
    succ = [_successors(ops, labels, i) for i in range(n)]
    preds_count = [0] * n
    preds_count[0] = 1          # the function entry is a predecessor of op 0
    for i in range(n):
        for s in succ[i]:
            preds_count[s] += 1

    def phis_at(s: int) -> list[int]:
        out = []
        j = s + 1 if isinstance(ops[s], Label) else s
        while j < n and isinstance(ops[j], Phi):
            out.append(j)
            j += 1
        return out

    # edge (i, s) -> list of (source web, target Phi op index) transfers
    edge_transfers: dict[tuple[int, int], list[tuple[str, int]]] = {}
    edge_use: dict[tuple[int, int], int] = {}
    escaped: set[str] = set()
    reason: dict[str, str] = {}

    def esc(w: str, why: str) -> None:
        if w not in escaped:
            escaped.add(w)
            reason[w] = why

    for i in range(n):
        lbl = block_label[i]
        for s in succ[i]:
            uses = 0
            for pj in phis_at(s):
                phi = ops[pj]
                for src_lbl, src in phi.sources:
                    if src_lbl != lbl:
                        continue
                    if isinstance(src, StackVar) and src.name in web_of:
                        w = web_of[src.name]
                        uses |= bit[w]
                        if _ptr_var(phi.target) and phi.target.name in web_of:
                            edge_transfers.setdefault((i, s), []).append((w, pj))
                        else:
                            esc(w, "phi-into-untracked")   # flows somewhere we do not track
                    else:
                        for sv in src.get_live_vars():
                            if sv.name in web_of:
                                esc(web_of[sv.name], "phi-compound")
                                uses |= bit[web_of[sv.name]]
            edge_use[(i, s)] = uses

    use = [0] * n
    kill = [0] * n
    for i, op in enumerate(ops):
        if isinstance(op, Phi):
            if _ptr_var(op.target) and op.target.name in web_of:
                kill[i] = bit[web_of[op.target.name]]
            continue
        reads = op.get_live_vars()[0] | op.saved_vars
        use[i] = web_bits(sv.name for sv in reads)
        for w, (kind, oi, _) in origin.items():
            if oi == i:
                kill[i] |= bit[w]

    # ── liveness (backward, to a fixpoint) ───────────────────────────────
    live_in = [0] * n
    live_out = [0] * n
    changed = True
    while changed:
        changed = False
        for i in range(n - 1, -1, -1):
            out = 0
            for s in succ[i]:
                out |= live_in[s] | edge_use.get((i, s), 0)
            inn = (out & ~kill[i]) | use[i]
            if out != live_out[i] or inn != live_in[i]:
                live_out[i], live_in[i] = out, inn
                changed = True

    # ── disqualification ────────────────────────────────────────────────
    for i, op in enumerate(ops):
        if isinstance(op, Phi) or i in is_copy:
            continue
        reads = op.get_live_vars()[0] | op.saved_vars
        for sv in reads:
            w = web_of.get(sv.name)
            if w is not None and w not in escaped and (sv in op.saved_vars or _publishes(op, sv.name)):
                esc(w, _why(op, sv.name))
        if (isinstance(op, Call) and op.may_suspend) or isinstance(op, ParallelCall):
            for w in webs:
                if live_out[i] & bit[w] & ~kill[i]:
                    esc(w, "live-across-suspension")
    for (i, s), transfers in edge_transfers.items():
        seen: set[str] = set()
        for w, _pj in transfers:
            if live_in[s] & bit[w] or w in seen:
                esc(w, "dup-at-phi")   # still reachable past the edge: a duplicate
            seen.add(w)

    if _DEBUG:
        for w in webs:
            if origin[w][0] == "new":
                _Stats.new_webs += 1
                if w in escaped:
                    _Stats.reasons[reason.get(w, "?")] = _Stats.reasons.get(reason.get(w, "?"), 0) + 1

    transferred = {w for ts in edge_transfers.values() for w, _ in ts}
    # A NewObject web that is never published and never crosses a Phi is
    # exactly what stack_promotion dissolves into locals at -O1+ — better than
    # any recycling, and a free (a bare-pointer use) would block it.
    promotable = ({w for w in webs if origin[w][0] == "new" and w not in escaped
                   and w not in transferred} if optimization_level >= 1 else set())
    freeable = [w for w in webs if w not in escaped and w not in promotable]
    if not freeable:
        return fn

    # ── ownership flags for Phi webs ─────────────────────────────────────
    new_vars: list[tuple[str, t.Type]] = []
    counter = [0]

    def fresh(prefix: str, typ: t.Type) -> StackVar:
        counter[0] += 1
        nm = f"$rc${prefix}{counter[0]}"
        new_vars.append((nm, typ))
        return StackVar(typ, nm)

    flag: dict[str, StackVar] = {}
    for w in freeable:
        if origin[w][0] == "phi":
            flag[w] = fresh("own", _BOOL)

    def owned_param(src: RParam) -> RParam | None:
        """The flag value an incoming Phi source contributes."""
        if isinstance(src, StackVar) and src.name in web_of:
            w = web_of[src.name]
            if w in escaped:
                return None
            if origin[w][0] == "new":
                return Integer(1, 8)
            return flag.get(w)
        return None

    flag_phis: dict[int, Phi] = {}
    for w in list(flag):
        _, pi, _ = origin[w]
        phi = ops[pi]
        sources = []
        any_owned = False
        for lbl, src in phi.sources:
            f = owned_param(src)
            if f is None:
                f = Integer(0, 8)
            elif not (isinstance(f, Integer) and f.value == 0):
                any_owned = True
            sources.append((lbl, f))
        if not any_owned:
            # Never owned on any edge (flags of other webs settle below).
            pass
        flag_phis[pi] = Phi(flag[w], tuple(sources))

    # A Phi web fed only by unowned values (directly or via other such webs)
    # can never free; prune those so no dead flag web is emitted.
    def never_owned(w: str, seen: set[str]) -> bool:
        if w in seen:
            return True
        seen.add(w)
        phi = flag_phis[origin[w][1]]
        for _lbl, f in phi.sources:
            if isinstance(f, Integer):
                if f.value != 0:
                    return False
            elif isinstance(f, StackVar):
                fw = next(x for x, fv in flag.items() if fv.name == f.name)
                if not never_owned(fw, seen):
                    return False
        return True
    dead_flags = {w for w in flag if never_owned(w, set())}
    for w in dead_flags:
        freeable.remove(w)
        escaped.add(w)
    for w in dead_flags:
        del flag_phis[origin[w][1]]
        del flag[w]
    # Sources naming a dropped flag contribute 0.
    for pi, phi in list(flag_phis.items()):
        live_flags = {f.name for f in flag.values()}
        flag_phis[pi] = dataclasses.replace(phi, sources=tuple(
            (lbl, f if not isinstance(f, StackVar) or f.name in live_flags else Integer(0, 8))
            for lbl, f in phi.sources))
    if not freeable:
        return fn

    def free_ops(w: str) -> list[Op]:
        ov = StackVar(t.DataPointer(), origin[w][2])
        sink = fresh("d", _BOOL)
        if w in flag:
            call = RuntimeInvoke("yafl_recycle_if",
                                 NewStruct((("_0", ov), ("_1", flag[w]))), _BOOL)
        else:
            call = RuntimeInvoke("yafl_recycle", NewStruct((("_0", ov),)), _BOOL)
        _Stats.frees += 1
        return [Move(sink, call, keep=True)]

    # ── placement ────────────────────────────────────────────────────────
    after: dict[int, list[Op]] = {}       # ops to emit after op i
    before: dict[int, list[Op]] = {}      # ops to emit before op i
    replace: dict[int, Op] = {}           # terminator rewritten onto a temp
    head: dict[int, list[Op]] = {}        # ops to emit at the head of block s
    plain_deaths: list[tuple[int, str]] = []
    hoisted: set[int] = set()             # ops moved up to a reuse site

    for w in freeable:
        b = bit[w]
        for i, op in enumerate(ops):
            if isinstance(op, (Label, Phi)):
                continue
            dies_here = (live_in[i] & b or kill[i] & b) and not (live_out[i] & b)
            if dies_here and (use[i] & b or kill[i] & b):
                if not _is_terminator(op):
                    plain_deaths.append((i, w))
                elif isinstance(op, (JumpIf, SwitchJump)):
                    cur_op = replace.get(i, op)
                    tmp = fresh("c", cur_op.condition.get_type())
                    before.setdefault(i, []).append(Move(tmp, cur_op.condition))
                    before[i].extend(free_ops(w))
                    replace[i] = dataclasses.replace(cur_op, condition=tmp)
                elif isinstance(op, Return):
                    cur_op = replace.get(i, op)
                    tmp = fresh("r", cur_op.value.get_type())
                    before.setdefault(i, []).append(Move(tmp, cur_op.value))
                    before[i].extend(free_ops(w))
                    replace[i] = dataclasses.replace(cur_op, value=tmp)
                else:
                    _Stats.missed_edges += 1       # musttail call reading it
            if live_out[i] & b:
                for s in succ[i]:
                    if live_in[s] & b or edge_use.get((i, s), 0) & b:
                        continue
                    if preds_count[s] == 1:
                        head.setdefault(s, []).extend(free_ops(w))
                    else:
                        _Stats.missed_edges += 1
        # A Phi web that is dead on arrival (e.g. the loop's exit value is
        # never read): free right after the block's Phis.
        _, pi, _ = origin[w]
        if origin[w][0] == "phi" and not (live_out[pi] & b):
            after.setdefault(pi, []).extend(free_ops(w))

    # ── reuse pairing (reset/reuse with the token in a register) ─────────
    # A plain death next to an allocation of the same class hands the dead
    # object straight to that NewObject. Forwards: the next eligible
    # NewObject in the block, with no suspension in between. Backwards: an
    # earlier NewObject in the block, if every use of the dying web after it
    # is a pure field read — immutable fields, so the reads hoist above the
    # allocation and the web dies there instead.
    def classes_of(w: str, seen: set[str]) -> set[str]:
        kind, oi, _ = origin[w]
        if kind == "new":
            return {ops[oi].name}
        if w in seen:
            return set()
        seen.add(w)
        out: set[str] = set()
        for _lbl, src in ops[oi].sources:
            if isinstance(src, StackVar) and src.name in web_of and web_of[src.name] not in escaped:
                out |= classes_of(web_of[src.name], seen)
        return out

    paired: set[int] = set()

    def can_take(j: int, w: str) -> bool:
        op = ops[j]
        if not (isinstance(op, NewObject) and op.size is None and op.reuse is None
                and _ptr_var(op.register) and j not in paired and j not in hoisted
                and _eligible_class(app, op.name) and op.name in classes_of(w, set())):
            return False
        nw = web_of.get(op.register.name)
        return nw != w and nw not in promotable

    def owned_flag(w: str) -> RParam:
        return flag[w] if w in flag else Integer(1, 8)

    def pair(j: int, w: str) -> None:
        paired.add(j)
        replace[j] = dataclasses.replace(ops[j], reuse=StackVar(t.DataPointer(), origin[w][2]),
                                         reuse_owned=owned_flag(w))
        _Stats.reuses += 1

    def is_field_read_of(op: Op, w: str) -> bool:
        if not (isinstance(op, Move) and isinstance(op.target, StackVar) and not op.keep):
            return False
        src = op.source
        if not (isinstance(src, ObjectField) and src.index is None
                and isinstance(src.pointer, StackVar) and web_of.get(src.pointer.name) == w):
            return False
        # Only a field that can never change may move earlier: the read's own
        # class must be plain immutable. ([pinnable] fields are published by
        # a late pin, [mutable] ones at any time — and a Phi web's runtime
        # class is not known statically, so the READ's class is what counts.)
        obj = app.objects.get(src.object_name)
        return obj is not None and not obj.is_mutable and not obj.is_pinnable

    unpaired: list[tuple[int, str]] = []
    for i, w in plain_deaths:
        b = bit[w]
        done = False
        # forwards
        j = i + 1
        while j < n and not isinstance(ops[j], (Label, Phi)) and not _is_terminator(ops[j]):
            if can_take(j, w):
                pair(j, w)
                done = True
                break
            if (isinstance(ops[j], Call) and ops[j].may_suspend) or isinstance(ops[j], ParallelCall):
                break
            j += 1
        # backwards, hoisting pure field reads
        if not done and is_field_read_of(ops[i], w):
            moves = [i]
            j = i - 1
            while j >= 0 and not isinstance(ops[j], (Label, Phi)) and not _is_terminator(ops[j]):
                if can_take(j, w):
                    ok = all(defs[ops[k].source.pointer.name][0] < j for k in moves)
                    if ok and not any(k in hoisted for k in moves):
                        for k in sorted(moves):
                            hoisted.add(k)
                            before.setdefault(j, []).append(ops[k])
                        pair(j, w)
                        done = True
                    break
                if use[j] & b or kill[j] & b:
                    if is_field_read_of(ops[j], w):
                        moves.append(j)
                    else:
                        break
                j -= 1
        if not done:
            unpaired.append((i, w))
    for i, w in unpaired:
        after.setdefault(i, []).extend(free_ops(w))

    new_ops: list[Op] = []
    i = 0
    while i < n:
        op = ops[i]
        if isinstance(op, Label):
            new_ops.append(op)
            # Phis (and their flag Phis) first, then the block-head frees.
            j = i + 1
            while j < n and isinstance(ops[j], Phi):
                new_ops.append(ops[j])
                if j in flag_phis:
                    new_ops.append(flag_phis[j])
                j += 1
            for k in range(i + 1, j):
                new_ops.extend(after.get(k, ()))
            new_ops.extend(head.get(i, ()))
            i = j
            continue
        if isinstance(op, Phi):     # Phis not under a Label (should not happen)
            new_ops.append(op)
            if i in flag_phis:
                new_ops.append(flag_phis[i])
            new_ops.extend(after.get(i, ()))
            i += 1
            continue
        new_ops.extend(head.get(i, ()))
        new_ops.extend(before.get(i, ()))
        if i not in hoisted:
            new_ops.append(replace.get(i, op))
        new_ops.extend(after.get(i, ()))
        i += 1

    _Stats.functions += 1
    _Stats.webs += len(freeable)
    if _DEBUG:
        print(f"[recycle] {fn.name}: {len(freeable)} web(s) "
              f"{[origin[w][2] for w in freeable]}", file=sys.stderr)
    stack_vars = t.Struct(fn.stack_vars.fields + tuple(new_vars))
    return dataclasses.replace(fn, ops=tuple(new_ops), stack_vars=stack_vars)


def recycle_dead_objects(app: Application, optimization_level: int = 0) -> Application:
    if not ENABLED:
        return app
    functions = {name: _rewrite(fn, app, optimization_level) for name, fn in app.functions.items()}
    if _DEBUG:
        print(f"[recycle] functions={_Stats.functions} webs={_Stats.webs} "
              f"frees={_Stats.frees} reuses={_Stats.reuses} missed_edges={_Stats.missed_edges}", file=sys.stderr)
        print(f"[recycle] NewObject webs={_Stats.new_webs}; disqualified by: "
              + ", ".join(f"{k}={v}" for k, v in sorted(_Stats.reasons.items(), key=lambda kv: -kv[1])),
              file=sys.stderr)
    return dataclasses.replace(app, functions=functions,
                               defines=tuple(app.defines) + (DEFINE,))
