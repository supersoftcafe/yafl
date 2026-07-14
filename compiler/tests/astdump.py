"""Canonical AST dump for parse() results — the PORT 2 validation contract.

One line per node, depth-first, indented by tree depth:

    <Depth spaces>TypeName|line:col|salient,fields

The ported parser (bootstrap) must reproduce this byte for byte over the
whole corpus. Field selection is exhaustive over everything parse() decides:
names (with @hash6), attributes, generics, types-as-spelled, literals,
match arms/guards/ranges, tuple entry names/spread, import groups. Values
that only later phases fill (resolved specs, enum caches) are excluded.
"""
from __future__ import annotations

import dataclasses

import pyast.statement as s
import pyast.expression as e
import pyast.match as m
import pyast.typespec as t


def _lr(x) -> str:
    lr = getattr(x, "line_ref", None)
    return f"{lr.line}:{lr.offset}" if lr is not None else "-"


def _ty(spec) -> str:
    """A type AS SPELLED at parse time, compactly."""
    if spec is None:
        return "-"
    if isinstance(spec, t.NamedSpec):
        args = ",".join(_ty(a) for a in spec.type_params)
        return f"N({spec.name}{'<' + args + '>' if spec.type_params else ''})"
    if isinstance(spec, t.BuiltinSpec):
        return f"B({spec.type_name})"
    if isinstance(spec, t.TupleSpec):
        ents = ",".join(
            f"{en.name or ''}:{_ty(en.type)}{'=D' if en.default is not None else ''}"
            for en in spec.entries)
        return f"T({ents})"
    if isinstance(spec, t.CombinationSpec):
        return "U(" + "|".join(_ty(x) for x in spec.types) + ")"
    if isinstance(spec, t.CallableSpec):
        return f"F({_ty(spec.parameters)}->{_ty(spec.result)})"
    if isinstance(spec, t.GenericPlaceholderSpec):
        return f"G({spec.name})"
    if isinstance(spec, t.ClassSpec):
        args = ",".join(_ty(a) for a in spec.type_params)
        return f"C({spec.name}{'<' + args + '>' if spec.type_params else ''})"
    return type(spec).__name__


def _attrs(attributes: dict) -> str:
    if not attributes:
        return "-"
    parts = []
    for k in attributes:  # declaration order (dict preserves insertion)
        v = attributes[k]
        parts.append(k if v is None else f"{k}=<expr>")
    return ",".join(parts)


def dump(statements) -> str:
    out: list[str] = []

    def line(depth: int, kind: str, node, extra: str):
        out.append(f"{'  ' * depth}{kind}|{_lr(node)}|{extra}")

    def walk_expr(x, depth: int):
        if x is None:
            line(depth, "None", None, "")
            return
        if isinstance(x, e.IntegerExpression):
            line(depth, "Int", x, f"{x.value}:{x.precision}")
        elif isinstance(x, e.FloatExpression):
            line(depth, "Float", x, f"{x.value}:{x.precision}")
        elif isinstance(x, e.StringExpression):
            line(depth, "Str", x, repr(x.value))
        elif isinstance(x, e.RegexExpression):
            line(depth, "Regex", x, repr(x.pattern))
        elif isinstance(x, e.NamedExpression):
            tps = ",".join(_ty(tp) for tp in x.type_params)
            line(depth, "Name", x, f"{x.name}|{tps}")
        elif isinstance(x, e.DotExpression):
            line(depth, "Dot", x, x.name)
            walk_expr(x.base, depth + 1)
        elif isinstance(x, e.CallExpression):
            line(depth, "Call", x, "")
            walk_expr(x.function, depth + 1)
            walk_expr(x.parameter, depth + 1)
        elif isinstance(x, e.TupleExpression):
            line(depth, "Tuple", x, "")
            for en in x.expressions:
                line(depth + 1, "Entry", x, f"{en.name or ''}|{'*' if en.spread else ''}")
                walk_expr(en.value, depth + 2)
        elif isinstance(x, e.TernaryExpression):
            line(depth, "Ternary", x, "")
            walk_expr(x.condition, depth + 1)
            walk_expr(x.trueResult, depth + 1)
            walk_expr(x.falseResult, depth + 1)
        elif isinstance(x, e.LambdaExpression):
            line(depth, "Lambda", x, "")
            walk_stmt(x.parameters, depth + 1)
            walk_expr(x.expression, depth + 1)
        elif isinstance(x, e.BlockExpression):
            line(depth, "Block", x, x.tag or "")
            for st in x.statements:
                walk_stmt(st, depth + 1)
            walk_expr(x.value, depth + 1)
        elif isinstance(x, m.MatchExpression):
            line(depth, "Match", x, "")
            walk_expr(x.subject, depth + 1)
            for arm in x.arms:
                extra = f"{arm.name or ''}|{_ty(arm.type_spec)}"
                line(depth + 1, "Arm", arm, extra)
                for lit in (arm.literals or ()):
                    if isinstance(lit, m.MatchRange):
                        line(depth + 2, "Range", lit, "")
                        walk_expr(lit.lo, depth + 3)
                        walk_expr(lit.hi, depth + 3)
                    else:
                        walk_expr(lit, depth + 2)
                if arm.guard is not None:
                    line(depth + 2, "Guard", arm, "")
                    walk_expr(arm.guard, depth + 3)
                walk_expr(arm.body, depth + 2)
        elif isinstance(x, e.BuiltinOpExpression):
            line(depth, "BuiltinOp", x, _ty(x.type))
            walk_expr(x.op, depth + 1)
            walk_expr(x.params, depth + 1)
        elif isinstance(x, e.ParallelExpression):
            line(depth, "Parallel", x, "")
            walk_expr(x.parameter, depth + 1)
        elif isinstance(x, e.NewEnumExpression):
            fields = ",".join(sorted(x.field_args))
            line(depth, "NewEnum", x, f"{x.root_spec_name}|{x.leaf_name}|{fields}")
        elif isinstance(x, e.BoolExpression):
            line(depth, "Bool", x, str(x.value))
        elif isinstance(x, e.NewExpression):
            line(depth, "New", x, _ty(x.type))
            walk_expr(x.parameter, depth + 1)
        elif isinstance(x, e.ArrayReadExpression):
            line(depth, "ArrayRead", x, "")
            walk_expr(x.object, depth + 1)
            walk_expr(x.index, depth + 1)
        elif isinstance(x, e.NothingExpression):
            line(depth, "Nothing", x, "")
        else:
            line(depth, type(x).__name__, x, "")

    def walk_stmt(st, depth: int):
        if isinstance(st, s.FunctionStatement):
            gens = ",".join(g.name for g in st.type_params)
            wheres = ",".join(_ty(w) for w in st.trait_params)
            line(depth, "Fun", st,
                 f"{st.name}|{_attrs(st.attributes)}|{gens}|{_ty(st.return_type)}|{wheres}")
            walk_stmt(st.parameters, depth + 1)
            walk_expr(st.body, depth + 1)
        elif isinstance(st, s.DestructureStatement):
            line(depth, "Destructure", st, f"{st.name}|{_attrs(st.attributes)}|{_ty(st.declared_type)}")
            for sub in st.targets:
                walk_stmt(sub, depth + 1)
        elif isinstance(st, s.LetStatement):
            gens = ",".join(g.name for g in st.type_params)
            line(depth, "Let", st,
                 f"{st.name}|{_attrs(st.attributes)}|{gens}|{_ty(st.declared_type)}")
            walk_expr(st.default_value, depth + 1)
        elif isinstance(st, s.ClassStatement):
            kind = "Interface" if st.is_interface else "Class"
            gens = ",".join(g.name for g in st.type_params)
            parents = ",".join(_ty(p) for p in st.implements)
            wheres = ",".join(_ty(w) for w in st.trait_params)
            line(depth, kind, st,
                 f"{st.name}|{_attrs(st.attributes)}|{gens}|{parents}|{wheres}")
            walk_stmt(st.parameters, depth + 1)
            for member in st.statements:
                walk_stmt(member, depth + 1)
        elif isinstance(st, s.EnumStatement):
            gens = ",".join(g.name for g in st.type_params)
            line(depth, "Enum", st, f"{st.name}|{gens}|{st.has_param_list}")
            walk_stmt(st.parameters, depth + 1)
            for v in st.variants:
                walk_stmt(v, depth + 1)
        elif isinstance(st, s.TypeAliasStatement):
            gens = ",".join(g.name for g in st.type_params)
            line(depth, "Typealias", st, f"{st.name}|{gens}|{_ty(st.type)}")
        elif isinstance(st, s.ReturnStatement):
            line(depth, "Ret", st, "")
            walk_expr(st.value, depth + 1)
        elif isinstance(st, s.IfStatement):
            line(depth, "If", st, "")
            walk_expr(st.condition, depth + 1)
            for b in st.true_block:
                walk_stmt(b, depth + 1)
            for b in st.false_block:
                walk_stmt(b, depth + 1)
        elif isinstance(st, s.ElseIfStatement):
            line(depth, "ElseIf", st, "")
            walk_expr(st.condition, depth + 1)
            for b in st.statements:
                walk_stmt(b, depth + 1)
        elif isinstance(st, s.ElseStatement):
            line(depth, "Else", st, "")
            for b in st.statements:
                walk_stmt(b, depth + 1)
        elif isinstance(st, s.ActionStatement):
            line(depth, "Action", st, "")
            walk_expr(st.action, depth + 1)
        else:
            line(depth, type(st).__name__, st, getattr(st, "name", ""))

    for st in statements:
        walk_stmt(st, 0)
    return "\n".join(out) + "\n"
