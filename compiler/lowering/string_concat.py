"""Flatten String `+` chains into one exact-size n-ary concatenation.

`a + b + c + d` reaches this IR (after the tiny `+` impl inlines) as a chain of
`RuntimeInvoke("string_append")` steps, each materialising an intermediate
String that the next step immediately consumes — n-1 allocations, all but the
last garbage. This stage rewrites any chain of three or more operands into a
single `RuntimeInvoke("string_concat_n")` (yafllib/string.c): sum the lengths,
allocate once at exact size, copy each piece. No intermediates, and none of a
StringBuilder's growth/resize overhead — for a statically-known chain this is
the optimal shape.

The chain is discovered through the SSA def-chains (lowering/ssa_defs.py):
an operand that is a directly-nested append, or a StackVar read exactly once
whose sole def is an append, is absorbed into the flat operand list (its Move
is then dropped). Absorption relocates a pure computation from its def site to
its sole read site — safe for `string_append` (pure allocation), and dominance
holds by SSA construction. Chains longer than the runtime's 16-operand cap are
grouped recursively. Runs in the pre-async fixpoint at -O1+: every elided
intermediate is also a value that never needs saving across a suspension.
"""
from __future__ import annotations

import dataclasses

from codegen.gen import Application
from codegen.ops import Op, Move
from codegen.param import RParam, StackVar, NewStruct, Integer, RuntimeInvoke
from codegen.typedecl import DataPointer
from lowering.ssa_defs import single_defs, read_counts

_APPEND = "string_append"
_CONCAT_N = "string_concat_n"
_RUNTIME_CAP = 16   # string_concat_n's fixed operand arrays


def _append_args(invoke: RuntimeInvoke) -> tuple[RParam, RParam] | None:
    """The (left, right) operands of a string_append invoke, when visible."""
    if invoke.function != _APPEND or not isinstance(invoke.parameters, NewStruct):
        return None
    values = [v for _, v in invoke.parameters.values]
    return (values[0], values[1]) if len(values) == 2 else None


def _concat_of(operands: list[RParam]) -> RParam:
    """A string_concat_n invoke over `operands`, grouped in runtime-cap-sized
    chunks when the chain is longer than the C side's fixed arrays."""
    if len(operands) == 1:
        return operands[0]
    if len(operands) > _RUNTIME_CAP:
        head = _concat_of(operands[:_RUNTIME_CAP])
        return _concat_of([head] + operands[_RUNTIME_CAP:])
    fields = ((("count", Integer(len(operands), 32)),)
              + tuple((f"s{i}", v) for i, v in enumerate(operands)))
    return RuntimeInvoke(_CONCAT_N, NewStruct(fields), DataPointer())


def flatten_string_appends(app: Application) -> Application:
    new_functions = {}
    for name, fn in app.functions.items():
        defs = single_defs(fn)
        reads = read_counts(fn)
        # keep=True Moves anchor side effects — never absorb them (absorbing
        # would duplicate the computation at the read site while the anchor
        # keeps the original alive).
        anchored = {op.target.name for op in fn.ops
                    if isinstance(op, Move) and op.keep and isinstance(op.target, StackVar)}
        absorbed: set[str] = set()

        def spine(param: RParam, taking: list[str]) -> list[RParam]:
            """The flattened operand list of the append tree rooted at
            `param`: nested appends, already-flattened concat_n invokes
            (replace_params rewrites bottom-up, so an inner chain may have
            been folded before its consumer is visited), and single-read
            locals chased through their defs. Names of locals the chase
            passed through are collected into `taking` — the caller commits
            them to `absorbed` ONLY if it actually rewrites; exploring a
            chain that stays under the fold threshold must drop nothing."""
            if isinstance(param, RuntimeInvoke):
                args = _append_args(param)
                if args is not None:
                    return spine(args[0], taking) + spine(args[1], taking)
                if param.function == _CONCAT_N and isinstance(param.parameters, NewStruct):
                    return [v for fname, v in param.parameters.values if fname != "count"]
            if (isinstance(param, StackVar) and reads.get(param.name) == 1
                    and param.name not in anchored):
                source = defs.get(param.name)
                # Chase through single-read locals: an append chain in a fused
                # body is threaded through plain copies (`sv2 = sv1`) that
                # copy-propagation's adjacent-op rule never folds. A copy, an
                # append, or an already-folded concat all absorb; any other
                # def (call result, Phi, impure invoke) stays a leaf operand.
                if isinstance(source, StackVar) or (
                        isinstance(source, RuntimeInvoke)
                        and (_append_args(source) is not None
                             or source.function == _CONCAT_N)):
                    taking.append(param.name)
                    return spine(source, taking)
            return [param]

        def replacer(p: RParam) -> RParam:
            if isinstance(p, RuntimeInvoke) and _append_args(p) is not None:
                taking: list[str] = []
                operands = spine(p, taking)
                if len(operands) >= 3:
                    absorbed.update(taking)
                    return _concat_of(operands)
            return p

        new_ops: list[Op] = [op.replace_params(replacer) for op in fn.ops]
        if absorbed:
            new_ops = [op for op in new_ops
                       if not (isinstance(op, Move) and isinstance(op.target, StackVar)
                               and op.target.name in absorbed)]
        new_functions[name] = dataclasses.replace(fn, ops=tuple(new_ops))
    return dataclasses.replace(app, functions=new_functions)
