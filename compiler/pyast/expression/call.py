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


_BUILTIN_DISPLAY = {"bigint": "Int", "int8": "Int8", "int16": "Int16",
                    "int32": "Int32", "int64": "Int64", "float32": "Float32",
                    "float64": "Float64", "bool": "Bool", "str": "String"}


def _spec_name(name: str, type_params: "tuple | None" = None) -> str:
    """A declared type's name as the author would write it: no namespace, no
    unique-name hash, and monomorphised specialisations shown with their
    argument list rather than the `$generic$` mangling."""
    bare = g.bare_name(name)
    head, sep, tail = bare.partition("$generic$")
    head = head.split("@", 1)[0]
    args = [a for a in tail.split("_") if a] if sep else []
    if type_params:
        args = [_type_str(p) for p in type_params]
    else:
        args = [_BUILTIN_DISPLAY.get(a, a.split("@", 1)[0]) for a in args]
    return f"{head}<{', '.join(args)}>" if args else head


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
        return _spec_name(ts.name)
    if isinstance(ts, t.TupleSpec):
        return "(" + ", ".join(_type_str(e.type) for e in ts.entries) + ")"
    if isinstance(ts, t.CombinationSpec):
        return " | ".join(_type_str(m) for m in ts.types)
    if isinstance(ts, t.CallableSpec):
        return f"{_type_str(ts.parameters)}: {_type_str(ts.result)}"
    if isinstance(ts, t.ClassSpec):
        return _spec_name(ts.name, ts.type_params)
    if isinstance(ts, t.EnumSpec):
        # Without this an enum rendered as "EnumSpec" — the internal class
        # name this function exists to avoid. List/Option/Result are all
        # enums, so it was the common case.
        return _spec_name(ts.root_name, ts.type_params)
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
        # This node owns the conversion between itself and its receiver: a call
        # whose settled result type cannot meet the receiver's expected type
        # wraps ITSELF (no-op until both types are ground — needs_conversion is
        # conservative, so generic templates never wrap).
        from pyast.expression.conversion import converted
        return converted(expr, expected_type, resolver), fglb+pglb

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        # The argument tuple checks against the resolved parameter shape, so an
        # explicit `name = value` naming no parameter is reported by the tuple
        # itself (the binding is otherwise lenient about incidental names).
        callee_type = self.function.get_type(resolver)
        callee_params = callee_type.parameters if isinstance(callee_type, t.CallableSpec) else None
        fn_err = self.function.check(resolver, None)
        arg_err = self.parameter.check(resolver, callee_params)
        # A callee that never narrowed to ONE callable is explained best HERE.
        # The name on its own can only say "Ambiguous — qualify it", which
        # tells the author to disambiguate; when NO overload accepts what they
        # passed, qualifying is impossible and that message sends them the
        # wrong way. This node knows the argument types, so let it say which
        # arguments failed and what the candidates actually take. Only when
        # nothing accepts them — two candidates that both fit really are
        # ambiguous, and that message stands.
        # Only when the name HAS candidates. A name that resolves to nothing at
        # all is a different situation with its own correct message ("Failed to
        # resolve x"); rerouting that here would say "no function named x is in
        # scope", which is no better and changes an established diagnostic.
        if (fn_err and not arg_err
                and not isinstance(callee_type, t.CallableSpec)
                and self.__callee_candidates(resolver)):
            ptype = self.parameter.get_type(resolver)
            if (isinstance(ptype, t.TupleSpec)
                    and not self.__any_candidate_accepts(resolver, ptype)):
                return [self.__unresolved_call_error(resolver, ptype, callee_type)]
        if fn_err or arg_err:
            return fn_err + arg_err

        ptype = self.parameter.get_type(resolver)
        if not isinstance(ptype, t.TupleSpec):
            return [Error(self.line_ref, "parameter expression must be of TupleType")]

        ftype = self.function.get_type(resolver)
        if not isinstance(ftype, t.CallableSpec):
            return [self.__unresolved_call_error(resolver, ptype, ftype)]

        if ftype.parameters.trivially_assignable_from(resolver, ptype) is False:
            return [Error(self.line_ref, "Parameters are not assignment compatible")]

        return []

    def __callee_candidates(self, resolver: g.Resolver) -> list:
        """The named callee's resolutions, or [] when the callee is not a
        plain name (a computed callable has no candidate list to report)."""
        from pyast.expression.access import NamedExpression
        if not isinstance(self.function, NamedExpression):
            return []
        return resolver.find_data(self.function.name)

    def __any_candidate_accepts(self, resolver: g.Resolver,
                                ptype: t.TupleSpec) -> bool:
        """Does at least one overload of the callee accept these arguments?

        True means the call really is AMBIGUOUS — several readings fit and the
        author must qualify. False means none fit, which is a different error
        with a different fix. Narrowing goes through the same
        `_resolve_overloads` the compile path uses, so the two agree about what
        "fits" (in particular about a candidate's own generic parameters, which
        are wildcards it may bind)."""
        from pyast.expression.access import NamedExpression, _resolve_overloads
        if not isinstance(self.function, NamedExpression):
            return False
        candidates = resolver.find_data(self.function.name)
        if not candidates:
            return False
        shape = t.CallableSpec(self.line_ref, ptype, None)
        return bool(_resolve_overloads(resolver, shape, candidates))

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



