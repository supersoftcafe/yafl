from __future__ import annotations

import dataclasses
import itertools

import lowering.trim
from codegen.gen import Application
from codegen.things import Function, Global
from codegen.ops import Op, NewObject, Move, Return, Label, Jump, JumpIf, Call
from codegen.param import RParam, LParam, StackVar, GlobalVar, ObjectField, NewStruct, Integer, String, StructField
from codegen.typedecl import DataPointer


_si_counter = itertools.count()


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


def _trace_to_constant(val: RParam, value_map: dict[str, RParam], globals: dict) -> RParam | None:
    """Trace val back to a compile-time constant (Integer or String), or None.
    Also returns NewStruct as an intermediate value for StructField extraction."""
    if isinstance(val, Integer):
        return val
    if isinstance(val, String):
        return val
    if isinstance(val, NewStruct):
        return val  # Intermediate: allows StructField to extract fields
    if isinstance(val, StackVar):
        src = value_map.get(val.name)
        return None if src is None else _trace_to_constant(src, value_map, globals)
    if isinstance(val, GlobalVar):
        g = globals.get(val.name)
        if g is None or g.lazy_init_function:
            return None
        if g.object_name is not None:
            return None  # Object-typed fields can't be used as C static initializer values
        if isinstance(g.init, (Integer, String)):
            return g.init
        return None
    if isinstance(val, StructField):
        struct = _trace_to_constant(val.struct, value_map, globals)
        if not isinstance(struct, NewStruct):
            return None
        fval = next((v for n, v in struct.values if n == val.field), None)
        return None if fval is None else _trace_to_constant(fval, value_map, globals)
    return None


def _promote_one_function(fn: Function, app: Application) -> tuple[Function, list[Global]]:
    """Promote NewObject ops with all-static fields to anonymous static globals."""
    value_map = _build_value_map(fn.ops)
    new_globals: list[Global] = []

    # Collect NewObject ops (fixed-size only, no arrays)
    new_obj_positions: dict[str, tuple[int, str]] = {}  # sv_name -> (op_index, class_name)
    for i, op in enumerate(fn.ops):
        if isinstance(op, NewObject) and op.size is None and isinstance(op.register, StackVar):
            new_obj_positions[op.register.name] = (i, op.name)

    if not new_obj_positions:
        return fn, []

    # Collect field assignment ops targeting each NewObject register
    field_assigns: dict[str, dict[str, tuple[int, RParam]]] = {}  # sv_name -> {field -> (idx, src)}
    for i, op in enumerate(fn.ops):
        if (isinstance(op, Move)
                and isinstance(op.target, ObjectField)
                and isinstance(op.target.pointer, StackVar)
                and op.target.pointer.name in new_obj_positions
                and op.target.index is None):
            sv = op.target.pointer.name
            if sv not in field_assigns:
                field_assigns[sv] = {}
            field_assigns[sv][op.target.field] = (i, op.source)

    ops_to_remove: set[int] = set()
    replacements: dict[int, Op] = {}

    for sv_name, (new_idx, class_name) in new_obj_positions.items():
        if class_name not in app.objects:
            continue
        obj = app.objects[class_name]
        if obj.array_type is not None:
            continue  # Skip objects with array fields

        data_fields = [(name, typ) for name, typ in obj.fields.fields if name != "type"]
        assigns = field_assigns.get(sv_name, {})

        if len(assigns) != len(data_fields):
            continue  # Not all fields are assigned

        # Trace each field's source to a compile-time constant
        field_values: list[tuple[str, RParam]] = []
        ok = True
        for field_name, _ in data_fields:
            if field_name not in assigns:
                ok = False
                break
            _, src = assigns[field_name]
            const = _trace_to_constant(src, value_map, app.globals)
            if const is None:
                ok = False
                break
            field_values.append((field_name, const))

        if not ok:
            continue

        # Create a new static global for this object
        gname = f"$si${next(_si_counter)}"
        new_globals.append(Global(
            name=gname,
            type=DataPointer(),
            init=NewStruct(tuple(field_values)),
            object_name=class_name
        ))

        # Replace NewObject with a load from the static global
        replacements[new_idx] = Move(
            target=fn.ops[new_idx].register,
            source=GlobalVar(DataPointer(), gname)
        )
        # Mark field assignment ops for removal
        for _, (assign_idx, _) in assigns.items():
            ops_to_remove.add(assign_idx)

    if not replacements:
        return fn, []

    new_ops = [
        replacements[i] if i in replacements else op
        for i, op in enumerate(fn.ops)
        if i not in ops_to_remove
    ]
    return dataclasses.replace(fn, ops=tuple(new_ops)), new_globals


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

def _global_names_in_rparam(val: RParam) -> set[str]:
    """Return set of global names referenced in an RParam."""
    if isinstance(val, GlobalVar):
        return {val.name}
    if isinstance(val, NewStruct):
        result: set[str] = set()
        for _, v in val.values:
            result |= _global_names_in_rparam(v)
        return result
    if isinstance(val, StructField):
        return _global_names_in_rparam(val.struct)
    return set()


def _global_names_in_op(op: Op) -> set[str]:
    """Return set of global names referenced in an Op."""
    result: set[str] = set()
    if isinstance(op, Move):
        if isinstance(op.target, GlobalVar):
            result.add(op.target.name)
        elif isinstance(op.target, ObjectField):
            result |= _global_names_in_rparam(op.target.pointer)
        result |= _global_names_in_rparam(op.source)
    elif isinstance(op, NewObject):
        if op.size:
            result |= _global_names_in_rparam(op.size)
    elif isinstance(op, Call):
        result |= _global_names_in_rparam(op.function)
        result |= _global_names_in_rparam(op.parameters)
        if op.register:
            if isinstance(op.register, GlobalVar):
                result.add(op.register.name)
    elif isinstance(op, Return):
        result |= _global_names_in_rparam(op.value)
    elif isinstance(op, JumpIf):
        result |= _global_names_in_rparam(op.condition)
    return result


def _count_global_refs(app: Application) -> dict[str, int]:
    """Count how many times each global name is referenced across all ops and global inits."""
    counts: dict[str, int] = {}

    def _add(name: str) -> None:
        counts[name] = counts.get(name, 0) + 1

    for fn in app.functions.values():
        for op in fn.ops:
            for name in _global_names_in_op(op):
                _add(name)

    for g in app.globals.values():
        if g.init:
            for name in _global_names_in_rparam(g.init):
                _add(name)
        if g.lazy_init_flag:
            _add(g.lazy_init_flag)

    return counts


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
    ref_counts = _count_global_refs(app)

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

        # Find the single function that references this global
        ref_fn_name: str | None = None
        for fn_name, fn in app.functions.items():
            for op in fn.ops:
                if si_name in _global_names_in_op(op):
                    ref_fn_name = fn_name
                    break
            if ref_fn_name:
                break

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
    """One iteration of: promote NewObjects → inline single-use globals → trim."""
    app = promote_static_objects(app)
    app = inline_single_use_globals(app)
    return lowering.trim.removed_unused_stuff(app)


def _resolve_rparam_constants(val: RParam, globals: dict) -> RParam | None:
    """Replace GlobalVar refs in val with traced Integer/String constants, or None if any fails."""
    if isinstance(val, (Integer, String)):
        return val
    if isinstance(val, GlobalVar):
        return _trace_to_constant(val, {}, globals)
    if isinstance(val, NewStruct):
        resolved = []
        for name, v in val.values:
            r = _resolve_rparam_constants(v, globals)
            if r is None:
                return None
            resolved.append((name, r))
        return NewStruct(tuple(resolved))
    return None


def resolve_flat_struct_global_inits(app: Application) -> Application:
    """Resolve GlobalVar refs in flat-struct global inits to Integer/String constants."""
    updated: dict[str, Global] = {}
    for name, g in app.globals.items():
        if g.object_name is not None or g.lazy_init_function or not isinstance(g.init, NewStruct):
            continue
        resolved = _resolve_rparam_constants(g.init, app.globals)
        if resolved is not None and resolved != g.init:
            updated[name] = dataclasses.replace(g, init=resolved)
    if not updated:
        return app
    return dataclasses.replace(app, globals={name: updated.get(name, g) for name, g in app.globals.items()})
