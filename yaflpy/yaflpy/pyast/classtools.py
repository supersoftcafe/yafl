from __future__ import annotations

import langtools
from typing import Iterable
from itertools import groupby
from functools import reduce
import dataclasses
import functools

import pyast.resolver as g
import pyast.expression as e
import pyast.typespec as t
import pyast.statement as s
import parselib as p

import codegen.ops as cg_o
import codegen.param as cg_p
import codegen.typedecl as cg_t
import codegen.things as cg_x


def create_slots_from_members(cls: s.ClassStatement) -> list[s.ClassFunctionSlot]:
    def to_slot(x: s.DataStatement) -> s.ClassFunctionSlot:
        slots = {x.name} if isinstance(x, s.LetStatement) or (isinstance(x, s.FunctionStatement) and x.statements) else set()
        slot = s.ClassFunctionSlot(x.name, x.get_type(), slots)
        return slot
    all_members = cls.parameters.flatten() + cls.statements
    result = [to_slot(x) for x in all_members if isinstance(x.get_type(), t.CallableSpec)]
    return result


def override_inherited_slots(
        resolver: g.Resolver,
        base_slots: list[s.ClassFunctionSlot],
        parent_slots: list[s.ClassFunctionSlot]
) -> list[s.ClassFunctionSlot]:
    # Anything that the provided slot overrides is added to its set of things it provides an implementation for
    def find_inheritance_matches(slot: s.ClassFunctionSlot) -> s.ClassFunctionSlot:
        names = {y
            for x in parent_slots
            if g.match_name(slot.name, x.name) and t.trivially_assignable_equals(resolver, x.type, slot.type)
            for y in x.provides | {x.name}}
        result = dataclasses.replace(slot, provides=slot.provides | names)
        return result
    base_enhanced = [find_inheritance_matches(x) for x in base_slots]
    exclusion_set = {y for x in base_enhanced for y in x.provides}
    parent_filtered = [x for x in parent_slots if x.name not in exclusion_set]
    # Return a list of all slots refined so that the overridden ones are not visible
    return base_enhanced + parent_filtered


def invert_and_merge_slots(slots: list[s.ClassFunctionSlot]) -> dict[str, set[str]]:
    def invert(slot: s.ClassFunctionSlot) -> dict[str, set[str]]:
        return {name: {slot.name} for name in slot.provides}
    def merge(a: dict[str, set[str]], b: dict[str, set[str]]) -> dict[str, set[str]]:
        return a | b | {name: a[name] | b[name] for name in a.keys() & b.keys()}
    result = reduce(merge, [invert(slot) for slot in slots], {})
    return result


def find_classes_or_error(
        types: Iterable[t.TypeSpec],
        resolver: g.Resolver
) -> list[(t.TypeSpec, s.ClassStatement|p.Error)]:
    def find_class_or_error(xtype: t.TypeSpec) -> (t.TypeSpec, s.ClassStatement|p.Error):
        if not isinstance(xtype, t.NamedSpec) and not isinstance(xtype, t.ClassSpec):
            return xtype, p.Error(xtype.line_ref, f"Class cannot inherit from this type \"{type(t)}\"")
        found = resolver.find_type({xtype.name})
        if not found:
            return xtype, p.Error(xtype.line_ref, f"Could not find class named \"{xtype.name}\"")
        if len(found) > 1:
            return xtype, p.Error(xtype.line_ref, f"Found too many classes named \"{xtype.name}\"")
        statement = found[0].statement
        if not isinstance(statement, s.ClassStatement):
            return xtype, p.Error(xtype.line_ref, f"Found non-class named \"{xtype.name}\"")
        return statement.get_type(), statement
    result = [find_class_or_error(xtype) for xtype in types]
    return result


def create_thunk(class_name: str, let: s.LetStatement) -> cg_x.Function:
    xtype = langtools.cast(t.CallableSpec, let.get_type())
    param_type = langtools.cast(cg_t.Struct, xtype.parameters.generate())
    param_vars = [cg_p.StackVar(ft, fn) for fn, ft in param_type.fields]
    xthis = cg_t.Struct((("this", cg_t.DataPointer()),))
    result_type = xtype.result.generate()
    result_var = cg_p.StackVar(result_type, "result")
    locals = cg_t.Struct((("result", result_type),))
    op_call = cg_o.Call(
        cg_p.ObjectField(cg_t.FuncPointer(), cg_p.StackVar(cg_t.DataPointer(), "this"), class_name, let.name, None),
        cg_p.NewStruct(tuple((sv.name, sv) for sv in param_vars)),
        result_var)
    op_return = cg_o.Return(result_var)
    thunk = cg_x.Function(let.name, xthis + param_type, result_type, locals, (op_call, op_return))
    return thunk
