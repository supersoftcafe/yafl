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
import pyast.hints as h
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


def no_overload_accepts_error(line_ref: LineRef, name: str, shape: t.CallableSpec,
                              candidate_types: list[t.TypeSpec | None]) -> Error:
    """No candidate of `name` accepts the call's arguments. Qualifying is
    impossible here, so say which arguments failed and what the candidates
    actually take."""
    raw = g.bare_name(name)
    shown = raw if raw.startswith("`") else f"`{raw}`"
    sigs = "; ".join(sorted({_type_str(c) for c in candidate_types
                             if isinstance(c, t.CallableSpec)}))
    return Error(line_ref,
        f"no {shown} accepts arguments {_type_str(shape.parameters)} — candidates: {sigs}")


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
        # enums, so it was the common case. A level is named as itself:
        # `Pay1`, never its root `Payload` — they are different types.
        return _spec_name(ts.path[-1] if ts.path else ts.root_name, ts.type_params)
    if isinstance(ts, t.GenericPlaceholderSpec):
        return g.bare_name(ts.name)
    return type(ts).__name__


def _has_hole_member(spec: t.TypeSpec | None, resolver: g.Resolver) -> bool:
    """`spec`, or a member of it when it is a union, is a placeholder that does
    not resolve here — a callee's own unbound `T` standing where a type goes."""
    members = spec.repr_members() if isinstance(spec, t.CombinationSpec) else (spec,)
    return any(isinstance(m, t.GenericPlaceholderSpec) and not t.resolves_in_scope(m.name, resolver)
               for m in members)


def _parameters_of(ftype: t.TypeSpec | None) -> t.TypeSpec | None:
    return ftype.parameters if isinstance(ftype, t.CallableSpec) else None


@dataclass
class CallExpression(Expression):
    function: Expression
    parameter: Expression
    # What the call was lowered FROM, when the user never wrote it (an
    # interpolation slot's `show` call): its errors are phrased in terms of
    # what they did write. Not identity: a lowered call is the same call.
    origin: "InterpolationOrigin | None" = field(default=None, compare=False)

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver, Any],Any]) -> Expression:
        return rw.rewrite(self, replace, resolver,
            function=self.function.search_and_replace(resolver, replace),
            parameter=self.parameter.search_and_replace(resolver, replace))

    def __callee_type(self, resolver: g.Resolver, function: Expression, parameter: Expression) -> t.TypeSpec | None:
        """The callee's type as THIS call sees it: tuples its signature leaves
        unnamed carry the field names the arguments supply."""
        return t.named_at_call_site(function.get_type(resolver), parameter.get_type(resolver))

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        func_type = self.__callee_type(resolver, self.function, self.parameter)
        if not isinstance(func_type, t.CallableSpec):
            return None
        # A generic callee whose result IS one of its own placeholders — bare,
        # or a member of the result union (`head`'s `T|None`) — has no result
        # type until its arguments are typed and bind it: reported now, that
        # hole reaches a receiver's inferred type as a union member no later
        # answer can fill. A placeholder INSIDE a named type (`put`'s
        # `Dict<K,V>`) is a shape, and inference fills it from siblings.
        result = func_type.result
        if _has_hole_member(result, resolver):
            ptype = self.parameter.get_type(resolver)
            if ptype is None or not ptype.is_concrete():
                return None
        return result

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement], h.Hints]:
        func_type = self.__callee_type(resolver, self.function, self.parameter)

        # Compile the ARGUMENT before inferring the function's generic type
        # params. The argument may itself be a generic call (e.g. `c(wrap(x))`);
        # only once it is compiled does its result type become concrete
        # (`Wrap<Leaf>` rather than the still-generic `Wrap<S>`). Inferring the
        # outer function's params from the un-compiled argument would bind them
        # to a placeholder-bearing type that never monomorphises.
        parameter, pglb, phints = self.parameter.compile(resolver, _parameters_of(func_type))
        prtr_type = parameter.get_type(resolver)

        if not isinstance(prtr_type, t.TupleSpec):
            return dataclasses.replace(self, parameter=parameter), pglb, phints

        function, fglb, fhints = self.function.compile(resolver, t.CallableSpec(self.line_ref, prtr_type, expected_type))

        # The callee pinned just now: give the open arguments its parameter types.
        pinned = _parameters_of(self.__callee_type(resolver, function, parameter))
        if _parameters_of(func_type) is None and pinned is not None and not prtr_type.is_concrete():
            parameter, retry_glb, phints = parameter.compile(resolver, pinned)
            pglb = pglb + retry_glb

        expr = dataclasses.replace(self, function=function, parameter=parameter)
        # This node owns the conversion between itself and its receiver: a call
        # whose settled result type cannot meet the receiver's expected type
        # wraps ITSELF (no-op until both types are ground — needs_conversion is
        # conservative, so a generic template wraps only a by-name tuple binding).
        from pyast.expression.conversion import converted
        return converted(expr, expected_type, resolver), fglb+pglb, h.merge(fhints, phints)

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        errors = self.__check(resolver, expected_type)
        if self.origin is None:
            return errors
        # The call's OWN errors are about a call the user never wrote: say what
        # they did write. An argument's errors are already about their code —
        # and when there are any, they are the cause: an argument of unknown
        # type makes every `show` a candidate, so the call's own complaint
        # would only be noise.
        own = [err for err in errors if err.line_ref.same_start(self.line_ref)]
        if len(own) < len(errors):
            return [err for err in errors if not err.line_ref.same_start(self.line_ref)]
        return [dataclasses.replace(err, message=self.origin.reword(err.message)) for err in own]

    def __check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        # The argument tuple checks against the resolved parameter shape, so an
        # explicit `name = value` naming no parameter is reported by the tuple
        # itself (the binding is otherwise lenient about incidental names).
        callee_type = self.function.get_type(resolver)
        callee_params = callee_type.parameters if isinstance(callee_type, t.CallableSpec) else None
        # The callee is LOADED to be called, so its check gets everything this
        # call knows about it: a function taking these arguments. It is the
        # load that narrows its overloads by that shape and reports none or
        # several, exactly as compile selected them.
        shape = self.__call_shape(resolver)
        fn_err = self.function.check(resolver, shape)
        arg_err = self.parameter.check(resolver, callee_params)
        # An argument with an error has no type to narrow by, so every
        # candidate "might" take it and the callee would only add noise
        # ("ambiguous"): the argument's error is the cause.
        if arg_err and not self.__arguments_typed(resolver):
            return arg_err
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

    def __arguments_typed(self, resolver: g.Resolver) -> bool:
        ptype = self.parameter.get_type(resolver)
        return isinstance(ptype, t.TupleSpec) and all(e.type is not None for e in ptype.entries)

    def __call_shape(self, resolver: g.Resolver) -> t.CallableSpec | None:
        """What this call tells its callee: a function of the argument tuple
        (None while the arguments have no type to say)."""
        ptype = self.parameter.get_type(resolver)
        if not isinstance(ptype, t.TupleSpec):
            return None
        return t.CallableSpec(self.line_ref, ptype, None)

    def __unresolved_call_error(self, resolver: g.Resolver,
                                ptype: t.TupleSpec, ftype: t.TypeSpec | None) -> Error:
        """The callee didn't resolve to a single callable. Say WHY in terms
        the author wrote — the called name, the argument types, and the
        candidate signatures — never the internal spec class name."""
        from pyast.expression.access import NamedExpression, candidate_signature
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
            ctype = candidate_signature(resolver, cand)
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
