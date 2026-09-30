"""Clean every function up, once, before dedup and emission.

The optimiser leaves copies it never propagated, unreachable ops, jumps to the
next label, repeated subexpressions, and Phis for emission to lower. This
stage removes them with a fixed per-function chain — lower Phis to per-edge
moves (while the CFG and predecessor labels are intact: everything after it is
Phi-unaware), strip unused operations, simplify control flow, fold struct
fields, propagate copies, simplify control flow again, eliminate common
subexpressions — and then drops the locals the chain has left unused.

It is the only place the chain runs: emission used to run it per function
itself, and now only emits. Running it here puts it before representation
dedup, which compares code as written and declarations as a set, so instances
that differed only in this debris now merge. It runs at every -O level and
under --profile (profile instrumentation happens at emission, after it).

`Function.lower_phis` and `Function.strip_unused_operations` stay on the IR
class: other stages use them too (phi_removal; branch_threading, known_tags).
The other four transforms belong to this stage alone and live here.
"""
from __future__ import annotations

import dataclasses

import codegen.ops as o
import codegen.param as p
import codegen.typedecl as t
from codegen.gen import Application
from codegen.ir import Function
from codegen.ops import Op, Move, Call, NewObject, Jump, JumpIf, IfTask, SwitchJump, Label


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def clean_functions(app: Application) -> Application:
    """See module docstring."""
    return dataclasses.replace(app, functions={
        n: _cleaned(fn) for n, fn in app.functions.items()})


def _cleaned(fn: Function) -> Function:
    if fn.foreign_symbol or not fn.ops:
        return fn
    fn = fn.lower_phis().strip_unused_operations()
    fn = _simplify_control_flow(fn)
    fn = _fold_struct_fields(fn)
    fn = _copy_propagate(fn)
    fn = _simplify_control_flow(fn)
    fn = _eliminate_common_subexpressions(fn)
    return _without_unused_locals(fn)


def _without_unused_locals(fn: Function) -> Function:
    used = _mentioned_locals(fn)
    kept = tuple((n, ty) for n, ty in fn.stack_vars.fields if n in used)
    if len(kept) == len(fn.stack_vars.fields):
        return fn
    return dataclasses.replace(fn, stack_vars=t.Struct(kept))


def _mentioned_locals(fn: Function) -> set[str]:
    """Every local the body reads, writes or saves. flatten() leaves out a
    local being written, so writes are collected from the ops themselves."""
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
# The chain's own transforms
# ---------------------------------------------------------------------------

def _fold_struct_field(rparam: p.RParam) -> p.RParam:
    """Fold StructField(NewStruct/NewStructTyped, name) → the named value directly.
    Eliminates construct-then-immediately-access patterns."""
    if isinstance(rparam, p.StructField):
        struct = rparam.struct
        if isinstance(struct, (p.NewStruct, p.NewStructTyped)):
            for name, value in struct.values:
                if name == rparam.field:
                    return value
    return rparam


def _fold_struct_fields(fn: Function) -> Function:
    """Fold StructField(NewStruct/NewStructTyped, name) → the value directly,
    bottom-up across all ops.  Eliminates redundant struct construct/access pairs."""
    return fn.replace_params(_fold_struct_field)


def _simplify_control_flow(fn: Function) -> Function:
    ops = list(fn.ops)
    changed = True
    while changed:
        changed = False
        new_ops: list[Op] = []
        i = 0
        while i < len(ops):
            op = ops[i]
            next_op  = ops[i + 1] if i + 1 < len(ops) else None
            next2_op = ops[i + 2] if i + 2 < len(ops) else None

            # goto L; L: → drop the goto
            if isinstance(op, Jump) and isinstance(next_op, Label) and op.name == next_op.name:
                changed = True
                i += 1
                continue

            # if (c) goto L; L: → drop the conditional jump
            if isinstance(op, JumpIf) and isinstance(next_op, Label) and op.label == next_op.name:
                changed = True
                i += 1
                continue

            # if (c) goto L1; goto L2; L1: → if (!c) goto L2; L1:
            if (isinstance(op, JumpIf) and not op.invert
                    and isinstance(next_op, Jump)
                    and isinstance(next2_op, Label)
                    and op.label == next2_op.name):
                new_ops.append(dataclasses.replace(op, label=next_op.name, invert=True))
                changed = True
                i += 2  # consume JumpIf + Jump; Label stays
                continue

            new_ops.append(op)
            i += 1
        ops = new_ops

    # Remove labels that no jump targets any more
    referenced: set[str] = set()
    for op in ops:
        if isinstance(op, Jump):
            referenced.add(op.name)
        elif isinstance(op, JumpIf):
            referenced.add(op.label)
        elif isinstance(op, IfTask):
            referenced.add(op.target)
        elif isinstance(op, SwitchJump):
            for _, lbl in op.cases:
                referenced.add(lbl)
    ops = [op for op in ops if not (isinstance(op, Label) and op.name not in referenced)]

    return dataclasses.replace(fn, ops=tuple(ops))


def _copy_propagate(fn: Function) -> Function:
    """Eliminate variable-to-variable copy assignments.

    Two cases:
    1. Simple aliases (single write, no null-init): a = b  →  replace all
       reads of a with b and drop the op.
    2. Phi-chain copies (ZeroOf null-init + one real write): a = b  →  same,
       provided b is GC-safe at the function entry (also null-inited or a
       parameter) and not reassigned after the copy.

    In both cases b must be written at most once (real writes only) so that
    substituting a → b can never observe a later version of b.
    """
    param_names: set[str] = {name for name, _ in fn.params.fields}

    # Separate ZeroOf inits from real writes.
    real_writes: dict[str, int] = {}
    zero_init_vars: set[str] = set()
    for op in fn.ops:
        if isinstance(op, Move) and isinstance(op.target, p.StackVar):
            name = op.target.name
            if isinstance(op.source, p.ZeroOf):
                zero_init_vars.add(name)
            else:
                real_writes[name] = real_writes.get(name, 0) + 1
        elif isinstance(op, (Call, NewObject)):
            reg = op.register
            if isinstance(reg, p.StackVar):
                real_writes[reg.name] = real_writes.get(reg.name, 0) + 1

    # GC-safe vars: always hold a valid (possibly null) pointer at function entry.
    gc_safe: set[str] = param_names | zero_init_vars

    # Build alias map: eliminated_var → source StackVar (unresolved).
    aliases: dict[str, p.StackVar] = {}
    for op in fn.ops:
        if not (isinstance(op, Move)
                and isinstance(op.target, p.StackVar)
                and isinstance(op.source, p.StackVar)):
            continue
        a, b = op.target.name, op.source.name
        if real_writes.get(a, 0) != 1:
            continue
        if real_writes.get(b, 0) > 1:
            # b may be overwritten after a = b; unsafe to alias.
            continue
        if a in zero_init_vars:
            # Null-init case: only safe when b is also GC-safe from the start.
            if b not in gc_safe and b not in param_names:
                continue
        aliases[a] = op.source

    if not aliases:
        return fn

    # Resolve chains (a → b → c becomes a → c).
    def resolve(sv: p.StackVar) -> p.StackVar:
        seen: set[str] = set()
        while sv.name in aliases and sv.name not in seen:
            seen.add(sv.name)
            sv = aliases[sv.name]
        return sv

    resolved: dict[str, p.StackVar] = {a: resolve(sv) for a, sv in aliases.items()}
    eliminated: set[str] = set(resolved)
    renames: dict[str, str] = {a: sv.name for a, sv in resolved.items()}

    new_ops: list[Op] = []
    for op in fn.ops:
        # Check original target BEFORE renaming: if we're writing to an
        # eliminated var (null-init or the real copy), drop the op entirely.
        if (isinstance(op, Move)
                and isinstance(op.target, p.StackVar)
                and op.target.name in eliminated):
            continue
        new_ops.append(op.rename_vars(renames))

    new_stack_vars = t.Struct(
        tuple((name, typ) for name, typ in fn.stack_vars.fields
              if name not in eliminated)
    )
    return dataclasses.replace(fn, ops=tuple(new_ops), stack_vars=new_stack_vars)


def _eliminate_common_subexpressions(fn: Function) -> Function:
    # Pre-pass: find StackVars written more than once.  These are not SSA-stable:
    # aliasing another var to a multi-write var would break correctness when the
    # var is overwritten.  Expressions that depend on multi-write vars are also
    # excluded from caching.
    write_counts: dict[str, int] = {}
    for op in fn.ops:
        if isinstance(op, Move) and isinstance(op.target, p.StackVar):
            n = op.target.name
            write_counts[n] = write_counts.get(n, 0) + 1
        elif isinstance(op, (Call, NewObject)):
            reg = op.register
            if isinstance(reg, p.StackVar):
                write_counts[reg.name] = write_counts.get(reg.name, 0) + 1
    multi_write: set[str] = {n for n, c in write_counts.items() if c > 1}

    def is_eligible(rparam: p.RParam) -> bool:
        if isinstance(rparam, (p.StackVar, p.GlobalVar, p.GlobalFunction)):
            return False
        return not rparam.test(
            lambda x: isinstance(x, p.StackVar) and x.name in multi_write)

    # available: pure RParam expression -> StackVar that already holds its value
    available: dict[p.RParam, p.StackVar] = {}
    # renames: eliminated var name -> canonical var name (applied to all later ops)
    renames: dict[str, str] = {}
    eliminated: set[str] = set()
    new_ops: list[Op] = []

    for op in fn.ops:
        if renames:
            op = op.rename_vars(renames)

        if isinstance(op, Label):
            # Basic-block boundary: expressions valid above may not hold on all
            # paths leading here.  Renames remain valid (each eliminated var is
            # single-write, so the alias holds for the rest of the function).
            available.clear()
            new_ops.append(op)

        elif isinstance(op, Move) and isinstance(op.target, p.StackVar):
            source = op.source
            target_name = op.target.name
            if (is_eligible(source) and source in available
                    and target_name not in multi_write):
                # Duplicate computation — alias this single-write var to the
                # existing single-write var that holds the same value.
                renames[target_name] = available[source].name
                eliminated.add(target_name)
                # Don't emit: the target var is gone.
            else:
                if is_eligible(source) and target_name not in multi_write:
                    available[source] = op.target
                new_ops.append(op)

        elif isinstance(op, (Call, NewObject)) or (
                isinstance(op, Move) and isinstance(op.target, p.ObjectField)):
            # A call, heap allocation, or heap field write may mutate object
            # state. Invalidate every cached expression that READS memory —
            # StructField as well as heap dereferences (ObjectField,
            # ArrayElement). Mutable heap slots (e.g. an async state object's
            # coalesced array slots) are read AND written through ObjectField,
            # so a cached read becomes stale the moment the slot is rewritten;
            # reusing it would substitute the slot's previous occupant (a
            # different logical variable) for its current one. Pure
            # computations over plain values remain valid.
            available = {k: v for k, v in available.items()
                         if not k.test(lambda x: isinstance(
                             x, (p.StructField, p.ObjectField, p.ArrayElement)))}
            new_ops.append(op)

        else:
            new_ops.append(op)

    if not eliminated:
        return fn

    new_stack_vars = t.Struct(
        tuple((name, typ) for name, typ in fn.stack_vars.fields
              if name not in eliminated)
    )
    return dataclasses.replace(fn, ops=tuple(new_ops), stack_vars=new_stack_vars)
