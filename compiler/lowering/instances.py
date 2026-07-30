"""Lower TraitInstanceStatement to the witness class + `[trait]` record let.

The `instance` statement is a first-class AST node through convergence,
checking, drops and linearity (pyast/statement/instances.py). HERE — after
every user-facing phase — each one lowers to the two statements the back
half of the pipeline (monomorphisation's constraint discharge and redirect,
codegen's static object plan) already understands:

  - a witness CLASS holding the members, implementing the pattern, carrying
    the instance's `where` clause (a member is a vtable slot: it declares no
    generics/wheres of its own; classdef compiles member bodies under a
    transient copy of the owner's clause);
  - a `[trait]` record let (`ambient` attribute when opted in) whose
    declared type is the witness instantiated over the instance's params.

Names are line-derived (path-based naming): nothing user-spellable, stable
across runs. The caller re-converges afterwards so the new statements
resolve like ordinary code.
"""
from __future__ import annotations

import pyast.expression as e
import pyast.statement as s
import pyast.typespec as t
import pyast.utils as u


def lower_trait_instances(statements: list[s.Statement]) -> tuple[list[s.Statement], bool]:
    out: list[s.Statement] = []
    changed = False
    for st in statements:
        if isinstance(st, s.TraitInstanceStatement):
            out.extend(__lower(st))
            changed = True
        else:
            out.append(st)
    return (out, changed)


def __lower(inst: s.TraitInstanceStatement) -> list[s.Statement]:
    lr = inst.line_ref
    tag = lr.hash6()
    ns = inst.name.rpartition('::')[0]
    prefix = f"{ns}::" if ns else ""
    wbare = f"_Instance${tag}"
    witness = s.ClassStatement(
        lr, f"{prefix}{wbare}@{tag}", inst.imports, {}, inst.type_params,
        s.DestructureStatement(lr, '_', None, {}, (), None, None, []),
        list(inst.statements),
        [inst.pattern], False,
        trait_params=inst.trait_params)
    own_args = tuple(t.NamedSpec(lr, p.name.split('@')[0]) for p in inst.type_params)
    value = e.CallExpression(
        lr, e.NamedExpression(lr, wbare, type_params=own_args),
        e.TupleExpression(lr, []))
    attributes: dict[str, e.Expression | None] = {'trait': None}
    if inst.ambient:
        attributes['ambient'] = None
    record = s.LetStatement(
        lr, f"{prefix}_instance${tag}@{tag}", inst.imports, attributes,
        inst.type_params, value, t.NamedSpec(lr, wbare, own_args),
        trait_params=inst.trait_params)
    return [witness, u.create_constructor(witness), record]
