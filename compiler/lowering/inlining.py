from __future__ import annotations

import dataclasses
from typing import Callable

import pyast.statement as s
import pyast.expression as e

import pyast.resolver as g
import pyast.typespec as t
import lowering.trim as trim
from codegen.typedecl import Type, Struct
from codegen.ops import Call, Op, Move, Label, Return, Jump, ParallelCall
from codegen.gen import Application
from codegen.param import GlobalFunction, NewStruct, StackVar
from codegen.things import Function

from langtools import cast
from pyast.statement import ImportGroup


__CUTOFF_COMPLEXITY = 10




def __do_inlining(fn: Function, others: dict[str, Function],
                  should_inline: Callable[[Function], bool]) -> Function:
    """Inline eligible call sites within `fn`. The structural guards (must be a
    direct call to an internal global function with struct args, not a self-call,
    not musttail, target non-empty and ParallelCall-free) are fixed; the policy
    `should_inline(target)` decides *which* eligible targets to pull in — size
    cutoff / `[inline(always)]` for the general pass, single-caller for the
    fold-away pass. `fn` is never an inlining SINK if it is `__entrypoint__` or
    `bypass_async`: async_lower passes those through untouched, so a suspending
    body inlined into them would never get its state machine."""
    new_ops: list[Op] = []
    new_vars: list[tuple[str, Type]] = []

    # __entrypoint__ / bypass_async functions are emitted as-is by async_lower
    # (no IS_TASK insertion, no state machine), so nothing may be inlined into
    # them — a suspending callee would be left un-lowered at codegen.
    if fn.name == "__entrypoint__" or fn.bypass_async:
        return fn

    def replace_op_with_func(op: Op, unique_id: str):
        if (not isinstance(op, Call) or
                not isinstance(op.function, GlobalFunction) or
                not isinstance(op.parameters, NewStruct) or
                fn.name == op.function.name or op.musttail or
                op.function.name not in others or
                not (target := others[op.function.name]).ops or
                # The size cutoff / `[inline(always)]` / single-caller decision.
                not should_inline(target) or
                # __entrypoint__ is hand-built and skipped by async_lower;
                # inlining a body with ParallelCall here would leave that op
                # un-lowered at codegen. Refuse inlining of any body that
                # contains ParallelCall to keep the lowering pipeline coherent.
                any(isinstance(o, ParallelCall) for o in target.ops)):
            new_ops.append(op)
            return # Not a candidate for inlining

        # For each param and stack_var, create a new stack_var with a unique name
        variable_mapping: dict[str, StackVar] =\
            {name: StackVar(type, f"inl{unique_id}${name}") for name, type in (target.params + target.stack_vars).fields}
        renames: dict[str, str] =\
            {name: sv.name for name, sv in variable_mapping.items()} |\
            {label.name: f"inl{unique_id}${label.name}" for label in target.ops if isinstance(label, Label)}
        new_vars.extend((sv.name, sv.type) for sv in variable_mapping.values())

        # Capture 'this'
        if op.function.object:
            new_ops.append(Move(variable_mapping[target.params.fields[0][0]], op.function.object))

        # Convert each call parameter to a Move into the parameter variables.
        for (_, value), (param_name, _) in zip(op.parameters.values, target.params.fields[1:]):
            new_ops.append(Move(variable_mapping[param_name], value))

        end_label = f"inl{unique_id}end"
        end_jump = Jump(end_label)

        # Insert the target code, renaming every variable use
        for target_op in target.ops:
            if isinstance(target_op, Return):
                # Replace every return with a Move and jump to an end label
                if op.register:
                    new_ops.append(Move(op.register, target_op.value.rename_vars(renames)))
                new_ops.append(end_jump)
            elif isinstance(target_op, Call) and target_op.musttail:
                # Replace every musttail=True with musttail=False
                new_ops.append(dataclasses.replace(target_op, musttail=False).rename_vars(renames))
            else:
                # Just rename the variable references
                new_ops.append(target_op.rename_vars(renames))

        if end_jump in new_ops:
            if new_ops.index(end_jump) < len(new_ops)-1:
                new_ops.append(Label(end_label)) # Needs a jump target
            else:
                new_ops.pop() # The only jump is just prior to the label

    for index, old_op in enumerate(fn.ops):
        replace_op_with_func(old_op, f"{len(fn.ops)}${index}")
    stack_vars = fn.stack_vars+Struct(fields=tuple(new_vars))
    return dataclasses.replace(fn, ops=tuple(new_ops), stack_vars=stack_vars)


def inline_small_functions(app: Application, inline_always: bool = True) -> Application:
    # Inline a small function (under the cutoff) always; inline an
    # `[inline(always)]` target regardless of size only when `inline_always` is
    # set (-O3), so a chain of marked stream `next` stages fuses into its
    # consumer. The self-recursion/musttail guards in the engine still apply
    # (loops/tail back-edges preserved, not unrolled).
    def policy(target: Function) -> bool:
        return (len(target.ops) < __CUTOFF_COMPLEXITY
                or (inline_always and target.always_inline))
    functions: dict[str, Function] = {name: __do_inlining(func, app.functions, policy) for name, func in app.functions.items()}
    return dataclasses.replace(app, functions=functions)


def inline_single_caller_functions(app: Application) -> Application:
    """Inline every function referenced exactly once into that sole call site,
    regardless of its size — folding it away costs no code growth (the original
    becomes unreferenced and is removed by the next trim). Runs after the small/
    always passes (-O3) so it collapses the residual one-shot helpers a pipeline
    leaves behind. The `== 1` count already guarantees the single reference IS
    the call being inlined; address-taken or vtable-bound functions have a count
    above one (or no call site at all) and are left alone by the engine."""
    refcounts = trim.function_reference_counts(app)

    def policy(target: Function) -> bool:
        return refcounts[target.name] == 1

    functions: dict[str, Function] = {name: __do_inlining(func, app.functions, policy) for name, func in app.functions.items()}
    return dataclasses.replace(app, functions=functions)

