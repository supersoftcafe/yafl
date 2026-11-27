from __future__ import annotations

import dataclasses

import lowering.literal_discovery as ld
import lowering.trim
from codegen.gen import Application
from codegen.typedecl import DataPointer
from codegen.ir import Function, Global
from codegen.ops import Op, NewObject, Move, JumpIf, Call
from codegen.param import RParam, StackVar, GlobalVar, ObjectField, NewStruct, Integer, String


_si_counter = [0]


def reset_si_counter() -> None:
    """Restart $si$N numbering. Called once per __create_c_code, so the
    emitted names depend only on the program being compiled — not on how many
    compiles this process ran before (a reused test-pool worker previously
    leaked the counter across files, making the -O1 output compile-order
    dependent). The bootstrap port threads its counter from 0 per compile;
    this keeps the reference implementation identical."""
    _si_counter[0] = 0


def _promote_one_function(fn: Function, app: Application) -> tuple[Function, list[Global]]:
    """Stage 2 of literal discovery (lowering/literal_discovery.py): each
    construction whose value is a literal becomes a static global, and the
    construction a load of it.

    The constructions are literal discovery's: an unpinned NewObject whose
    stores are all fresh initialisation stores, every one of them constant —
    other constructions included, so a whole graph goes static, children
    first, in op order. Its emitter writes the statics: never a pinned
    object, never a [pinnable] one a late write could still fill (an array is
    trimmed to its length first, as compaction would)."""
    machine = ld.Machine(app)
    consts = ld.Constants(machine, list(fn.ops))
    known: dict[int, str] = {}
    new_globals: list[Global] = []
    promoted: dict[str, RParam] = {}
    for name in consts.builds:
        start = _si_counter[0]
        emitter = ld.Emitter(machine, _si_counter, known, prefix="$si$")
        try:
            value = emitter.value(consts[name], DataPointer(), False)
        except ld.Stop:
            _si_counter[0] = start
            continue
        known.update(emitter.names)
        new_globals.extend(emitter.globals.values())
        promoted[name] = value
    if not promoted:
        return fn, []
    ops = []
    for op in fn.ops:
        if isinstance(op, NewObject) and isinstance(op.register, StackVar) and op.register.name in promoted:
            ops.append(Move(op.register, promoted[op.register.name]))
        elif (isinstance(op, Move) and isinstance(op.target, ObjectField)
              and isinstance(op.target.pointer, StackVar) and op.target.pointer.name in promoted):
            continue
        else:
            ops.append(op)
    return dataclasses.replace(fn, ops=tuple(ops)), new_globals


def promote_static_objects(app: Application) -> Application:
    """Promote NewObject constructions with all-static fields to static globals."""
    new_functions: dict[str, Function] = {}
    all_new_globals: dict[str, Global] = {}

    for name, fn in app.functions.items():
        new_fn, new_glbs = _promote_one_function(fn, app)
        new_functions[name] = new_fn
        for g in new_glbs:
            all_new_globals[g.name] = g

    return dataclasses.replace(app, globals={**all_new_globals, **app.globals}, functions=new_functions)


# ── Single-use global inlining ────────────────────────────────────────────────

def _globals_read_by_rparam(val: RParam) -> set[str]:
    """The globals `val` reads."""
    return {p.name for p in val.flatten() if isinstance(p, GlobalVar)}


def _globals_read_by_op(op: Op) -> set[str]:
    """The globals `op` reads. Writes are not counted: a static object is a
    constant, so no op writes one, and single use is about its readers."""
    return {p.name for p in op.all_params() if isinstance(p, GlobalVar)}


def _count_global_refs(app: Application) -> tuple[dict[str, int], dict[str, str]]:
    """Reference counts per global name, AND the first function whose ops mention
    each name — both from ONE sweep.

    The first-referencing map exists so `inline_single_use_globals` does not have
    to re-scan the whole application per candidate global. That search was
    `globals x functions x ops`, with a fresh set built per op by
    `_globals_read_by_op`, and it dominated compilation: measured on the
    self-host, the four `convert_static_objects_pass` rounds were 1777s of a
    2586s compile (69%). This sweep already visits every op, so recording the
    first function costs nothing extra and makes the lookup O(1).
    """
    counts: dict[str, int] = {}
    first_fn: dict[str, str] = {}

    def _add(name: str) -> None:
        counts[name] = counts.get(name, 0) + 1

    for fn_name, fn in app.functions.items():
        for op in fn.ops:
            for name in _globals_read_by_op(op):
                _add(name)
                # FIRST in iteration order — the same function the old
                # per-candidate scan would have stopped at.
                if name not in first_fn:
                    first_fn[name] = fn_name

    for g in app.globals.values():
        if g.init:
            for name in _globals_read_by_rparam(g.init):
                _add(name)
        if g.lazy_init_flag:
            _add(g.lazy_init_flag)

    return counts, first_fn


def _build_value_map(ops) -> dict[str, RParam]:
    """Build a map from StackVar name to its source for singly-assigned vars."""
    counts: dict[str, int] = {}
    values: dict[str, RParam] = {}
    for op in ops:
        if isinstance(op, Move) and isinstance(op.target, StackVar):
            n = op.target.name
            counts[n] = counts.get(n, 0) + 1
            values[n] = op.source
    return {k: v for k, v in values.items() if counts[k] == 1}


def _trace_to_global(val: RParam, value_map: dict[str, RParam]) -> str | None:
    """Trace val through StackVar copies to a GlobalVar name, or None."""
    if isinstance(val, GlobalVar):
        return val.name
    if isinstance(val, StackVar):
        src = value_map.get(val.name)
        return None if src is None else _trace_to_global(src, value_map)
    return None


def _is_trivial_copy_fn(fn: Function, source_name: str, target_name: str) -> bool:
    """Return True if fn does nothing but copy the source global to the target global."""
    for op in fn.ops:
        if isinstance(op, (Call, NewObject, JumpIf)):
            return False

    value_map = _build_value_map(fn.ops)
    target_writes = [
        op for op in fn.ops
        if isinstance(op, Move) and isinstance(op.target, GlobalVar)
        and op.target.name == target_name
    ]
    if len(target_writes) != 1:
        return False

    traced = _trace_to_global(target_writes[0].source, value_map)
    return traced == source_name


def inline_single_use_globals(app: Application) -> Application:
    """Inline static globals that are used only once as the source of a trivial lazy-init copy."""
    ref_counts, ref_fn_of = _count_global_refs(app)

    # Map lazy-init function name -> (target global name, target Global)
    lazy_init_targets: dict[str, tuple[str, Global]] = {
        g.lazy_init_function: (name, g)
        for name, g in app.globals.items()
        if g.lazy_init_function
    }

    # Static globals: have object_name set, no lazy_init_function
    static_globals = {
        name: g for name, g in app.globals.items()
        if g.object_name is not None and g.lazy_init_function is None
    }

    to_remove_globals: set[str] = set()
    to_remove_functions: set[str] = set()
    updated_globals: dict[str, Global] = {}

    for si_name, si_global in static_globals.items():
        if ref_counts.get(si_name, 0) != 1:
            continue

        # The single function that references this global — from the index
        # built alongside the counts, not a fresh sweep per candidate.
        ref_fn_name = ref_fn_of.get(si_name)

        if ref_fn_name is None or ref_fn_name not in lazy_init_targets:
            continue

        target_name, target_global = lazy_init_targets[ref_fn_name]

        if not _is_trivial_copy_fn(app.functions[ref_fn_name], si_name, target_name):
            continue

        # Fold: make the target global itself the static object global
        updated_globals[target_name] = dataclasses.replace(
            target_global,
            object_name=si_global.object_name,
            init=si_global.init,
            lazy_init_function=None,
            lazy_init_flag=None
        )
        to_remove_globals.add(si_name)
        to_remove_functions.add(ref_fn_name)

    if not updated_globals:
        return app

    return dataclasses.replace(app,
        globals={
            name: updated_globals.get(name, g)
            for name, g in app.globals.items()
            if name not in to_remove_globals
        },
        functions={
            name: fn for name, fn in app.functions.items()
            if name not in to_remove_functions
        },
    )


def convert_static_objects_pass(app: Application) -> Application:
    """One iteration of: promote constructions → settle globals whose
    initialiser is now a constant → inline single-use globals → trim."""
    app = promote_static_objects(app)
    app = ld.settle_globals(app)
    app = inline_single_use_globals(app)
    return lowering.trim.removed_unused_stuff(app)


def _resolved_constants(val: RParam, machine: "ld.Machine", emitter: "ld.Emitter") -> RParam:
    """`val` with each global it reads replaced by that global's constant
    (literal discovery's reading of it); Stop when one has none."""
    match val:
        case GlobalVar():
            return emitter.value(machine.global_value(val.name), val.type, True)
        case NewStruct():
            return NewStruct(tuple((n, _resolved_constants(v, machine, emitter)) for n, v in val.values))
        case Integer() | String():
            return val
    raise ld.Stop(ld.OPAQUE)


def resolve_flat_struct_global_inits(app: Application) -> Application:
    """Resolve GlobalVar refs in flat-struct global inits to their constants."""
    machine = ld.Machine(app)
    emitter = ld.Emitter(machine, [0], {})
    updated: dict[str, Global] = {}
    for name, g in app.globals.items():
        if g.object_name is not None or g.lazy_init_function or not isinstance(g.init, NewStruct):
            continue
        try:
            resolved = _resolved_constants(g.init, machine, emitter)
        except ld.Stop:
            continue
        if resolved != g.init:
            updated[name] = dataclasses.replace(g, init=resolved)
    if not updated:
        return app
    return dataclasses.replace(app, globals={name: updated.get(name, g) for name, g in app.globals.items()})
