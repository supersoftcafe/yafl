from __future__ import annotations

from typing import Callable, Any
import dataclasses
import pyast.rewrite as rw
from dataclasses import dataclass, field
from functools import reduce

from langtools import checked_cast
from parsing.tokenizer import LineRef
from parsing.parselib import Error

import codegen.ops as cg_o
import codegen.param as cg_p
import codegen.typedecl as cg_t

import pyast.resolver as g
import pyast.statement as s
import pyast.typespec as t
import pyast.utils as u
from pyast.expression.base import Expression


def _type_str(ts: t.TypeSpec | None) -> str:
    """A source-shaped rendering of a type for diagnostics (best-effort;
    never the internal class name)."""
    if ts is None:
        return "unknown"
    if isinstance(ts, t.BuiltinSpec):
        return {"bigint": "Int", "int8": "Int8", "int16": "Int16",
                "int32": "Int32", "int64": "Int64", "float32": "Float32",
                "float64": "Float64", "bool": "Bool", "str": "String"}.get(
                    ts.type_name, ts.type_name)
    if isinstance(ts, t.NamedSpec):
        return g.bare_name(ts.name)
    if isinstance(ts, t.TupleSpec):
        return "(" + ", ".join(_type_str(e.type) for e in ts.entries) + ")"
    if isinstance(ts, t.CombinationSpec):
        return " | ".join(_type_str(m) for m in ts.types)
    if isinstance(ts, t.CallableSpec):
        return f"{_type_str(ts.parameters)}: {_type_str(ts.result)}"
    if isinstance(ts, t.ClassSpec):
        return g.bare_name(ts.name)
    if isinstance(ts, t.GenericPlaceholderSpec):
        return g.bare_name(ts.name)
    return type(ts).__name__


@dataclass
class CallExpression(Expression):
    function: Expression
    parameter: Expression

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver, Any],Any]) -> Expression:
        return rw.rewrite(self, replace, resolver,
            function=self.function.search_and_replace(resolver, replace),
            parameter=self.parameter.search_and_replace(resolver, replace))

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        func_type = self.function.get_type(resolver)
        return func_type.result if isinstance(func_type, t.CallableSpec) else None

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) ->  tuple[Expression, list[s.Statement]]:
        func_type = self.function.get_type(resolver)

        # Compile the ARGUMENT before inferring the function's generic type
        # params. The argument may itself be a generic call (e.g. `c(wrap(x))`);
        # only once it is compiled does its result type become concrete
        # (`Wrap<Leaf>` rather than the still-generic `Wrap<S>`). Inferring the
        # outer function's params from the un-compiled argument would bind them
        # to a placeholder-bearing type that never monomorphises.
        parameter, pglb = self.parameter.compile(resolver, func_type.parameters if isinstance(func_type, t.CallableSpec) else None)
        prtr_type = parameter.get_type(resolver)

        if not isinstance(prtr_type, t.TupleSpec):
            return dataclasses.replace(self, parameter=parameter), pglb

        function, fglb = self.function.compile(resolver, t.CallableSpec(self.line_ref, prtr_type, expected_type))

        expr = dataclasses.replace(self, function=function, parameter=parameter)
        return expr, fglb+pglb

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        # TODO: Figure out what expected type to pass in
        err = self.function.check(resolver, None) + self.parameter.check(resolver, None)
        if err:
            return err

        ptype = self.parameter.get_type(resolver)
        if not isinstance(ptype, t.TupleSpec):
            return [Error(self.line_ref, "parameter expression must be of TupleType")]

        ftype = self.function.get_type(resolver)
        if not isinstance(ftype, t.CallableSpec):
            return [self.__unresolved_call_error(resolver, ptype, ftype)]

        if ftype.parameters.trivially_assignable_from(resolver, ptype) is False:
            return [Error(self.line_ref, "Parameters are not assignment compatible")]

        return []

    def __unresolved_call_error(self, resolver: g.Resolver,
                                ptype: t.TupleSpec, ftype: t.TypeSpec | None) -> Error:
        """The callee didn't resolve to a single callable. Say WHY in terms
        the author wrote — the called name, the argument types, and the
        candidate signatures — never the internal spec class name."""
        from pyast.expression.access import NamedExpression
        args = _type_str(ptype)
        if not isinstance(self.function, NamedExpression):
            return Error(self.line_ref,
                f"the value being called is not a function (its type is "
                f"{_type_str(ftype)})")
        raw = g.bare_name(self.function.name)
        name = raw if raw.startswith("`") else f"`{raw}`"
        candidates = resolver.find_data(self.function.name)
        callable_sigs = []
        non_callable = None
        for cand in candidates:
            ctype = cand.statement.get_type()
            if isinstance(ctype, t.CallableSpec):
                callable_sigs.append(_type_str(ctype))
            elif ctype is not None:
                non_callable = _type_str(ctype)
        if not candidates:
            return Error(self.line_ref, f"no function named {name} is in scope")
        if not callable_sigs and non_callable is not None:
            return Error(self.line_ref,
                f"{name} is not a function — it is a {non_callable}")
        sigs = "; ".join(sorted(set(callable_sigs)))
        return Error(self.line_ref,
            f"no {name} accepts arguments {args} — candidates: {sigs}")

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        ftype = self.function.get_type(resolver)
        xtype = checked_cast(t.CallableSpec, ftype)

        fun_op_bundle = self.function.generate(resolver).with_prefix("fn")
        # Coerce each argument to its declared parameter type — a narrow argument
        # flowing into a union-typed parameter is boxed here. `self.parameter` is
        # a tuple, so generate_to widens the matching fields (see coerce._coerce_tuple).
        prm_op_bundle = self.parameter.generate_to(resolver, xtype.parameters).with_prefix("args")

        fun_ref = fun_op_bundle.result_var
        impure = isinstance(fun_ref, cg_p.GlobalFunction) and fun_ref.impure

        result_var = cg_p.StackVar(xtype.result.generate(resolver), "result")
        call_bundle = g.OperationBundle(
            (result_var,),
            (cg_o.Call(fun_ref, prm_op_bundle.result_var, result_var, impure=impure),),
            result_var
        )

        return fun_op_bundle + prm_op_bundle + call_bundle



