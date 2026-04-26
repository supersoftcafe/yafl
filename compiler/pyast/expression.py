from __future__ import annotations

from typing import Callable, Any
import dataclasses
from dataclasses import dataclass, field
from functools import reduce

from langtools import cast
from parsing.tokenizer import LineRef
from parsing.parselib import Error

import codegen.ops as cg_o
import codegen.param as cg_p
import codegen.typedecl as cg_t

import pyast.resolver as g
import pyast.statement as s
import pyast.typespec as t
import pyast.utils as u


def _foreign_symbol(stmt: s.FunctionStatement) -> str | None:
    """Return the C symbol name if stmt has [foreign("symbol")], else None."""
    foreign_attr = stmt.attributes.get("foreign")
    if (isinstance(foreign_attr, TupleExpression)
            and len(foreign_attr.expressions) == 1
            and isinstance(foreign_attr.expressions[0].value, StringExpression)):
        return foreign_attr.expressions[0].value.value
    return None


def _is_impure(stmt: s.FunctionStatement) -> bool:
    """Return True if stmt has the [impure] attribute."""
    return "impure" in stmt.attributes


def _is_sync(stmt: s.FunctionStatement) -> bool:
    """Return True if stmt has the [sync] attribute."""
    return "sync" in stmt.attributes


@dataclass
class Expression:
    line_ref: LineRef

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        raise NotImplementedError()

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement]]:
        raise NotImplementedError()

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        return []

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        raise NotImplementedError()

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,Any],Any]) -> Expression:
        return cast(Expression, replace(resolver, self))


@dataclass
class NewExpression(Expression):
    type: t.TypeSpec
    parameter: Expression

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,Any],Any]) -> Expression:
        return cast(Expression, replace(resolver, dataclasses.replace(self,
            type=self.type.search_and_replace(resolver, replace),
            parameter=self.parameter.search_and_replace(resolver, replace))))

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        return self.type

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement]]:
        xtype = self.parameter.get_type(resolver)
        if not isinstance(xtype, t.TupleSpec):
            return self, []

        type, tstmt = self.type.compile(resolver)
        parm, pstmt = self.parameter.compile(resolver, None)

        return dataclasses.replace(self, type=type, parameter=parm), tstmt+pstmt

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        err = self.type.check(resolver) + self.parameter.check(resolver, None)
        if err:
            return err

        xtype = self.parameter.get_type(resolver)
        if not isinstance(xtype, t.TupleSpec):
            return [Error(self.line_ref, "parameter expression must be of TupleType")]

        ctype = self.type
        if not isinstance(ctype, t.ClassSpec):
            return [Error(self.line_ref, "type must be ClassSpec")]

        types = resolver.find_type({ctype.name})
        if not types:
            return [Error(self.line_ref, f"Couldn't find class named \"{ctype.name}\"")]
        if len(types) > 1:
            return [Error(self.line_ref, f"Found too many classes named \"{ctype.name}\"")]

        xclass = types[0].statement
        if not isinstance(xclass, s.ClassStatement):
            return [Error(self.line_ref, "type must be ClassSpec")]
        if xclass.is_interface:
            return [Error(self.line_ref, "cannot create an interface instance")]

        return []

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        xtype = cast(t.TupleSpec, self.parameter.get_type(resolver))
        ctype = cast(t.ClassSpec, self.type)
        found = resolver.find_type({ctype.name})
        if len(found) != 1:
            resolver.find_type({ctype.name})
            raise AssertionError(f"Failed to resolve {ctype.name}")
        fields = cast(s.ClassStatement, found[0].statement).get_fields(resolver)

        params_bundle = self.parameter.generate(resolver).rename_vars(1)

        params_var = cg_p.StackVar(xtype.generate(), "params")
        result_var = cg_p.StackVar(ctype.generate(), "result")

        cname = ctype.name
        ops = ( ( cg_o.Move(params_var, params_bundle.result_var),
                  cg_o.NewObject(cname, result_var) )
               + tuple(cg_o.Move(cg_p.ObjectField(x.get_type().generate(), result_var, cname, x.name, None), cg_p.StructField(params_var, f"_{index}")) for index, x in enumerate(fields))
        )

        constructor_bundle = g.OperationBundle(
            stack_vars=(params_var,result_var,),
            operations=ops,
            result_var=result_var,
        )

        return params_bundle + constructor_bundle


@dataclass
class CallExpression(Expression):
    function: Expression
    parameter: Expression

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver, Any],Any]) -> Expression:
        return cast(Expression, replace(resolver, dataclasses.replace(self,
            function=self.function.search_and_replace(resolver, replace),
            parameter=self.parameter.search_and_replace(resolver, replace))))

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        func_type = self.function.get_type(resolver)
        return func_type.result if isinstance(func_type, t.CallableSpec) else None

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) ->  tuple[Expression, list[s.Statement]]:
        func_type = self.function.get_type(resolver)
        prtr_type = self.parameter.get_type(resolver)

        if not isinstance(prtr_type, t.TupleSpec):
            return self, []

        function , fglb = self.function.compile(resolver, t.CallableSpec(self.line_ref, prtr_type, expected_type))
        parameter, pglb = self.parameter.compile(resolver, func_type.parameters if isinstance(func_type, t.CallableSpec) else None)

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
            return [Error(self.line_ref, "Callable must be of type CallableSpec")]

        if not ftype.parameters.trivially_assignable_from(resolver, ptype):
            return [Error(self.line_ref, "Parameters are not assignment compatible")]

        return []

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        ftype = self.function.get_type(resolver)
        xtype = cast(t.CallableSpec, ftype)

        fun_op_bundle = self.function.generate(resolver).rename_vars(1)
        prm_op_bundle = self.parameter.generate(resolver).rename_vars(2)

        fun_ref = fun_op_bundle.result_var
        impure = isinstance(fun_ref, cg_p.GlobalFunction) and fun_ref.impure

        result_var = cg_p.StackVar(xtype.result.generate(), "result")
        call_bundle = g.OperationBundle(
            (result_var,),
            (cg_o.Call(fun_ref, prm_op_bundle.result_var, result_var, impure=impure),),
            result_var
        )

        return fun_op_bundle + prm_op_bundle + call_bundle


@dataclass
class DotExpression(Expression):
    base: Expression
    name: str

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,Any],Any]) -> Expression:
        return cast(Expression, replace(resolver, dataclasses.replace(self,
            base=self.base.search_and_replace(resolver, replace))))

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        btype = self.base.get_type(resolver)
        match btype:
            case t.TupleSpec(entries=entries):
                entry = next((en for en in entries if en.name == self.name), None)
                return entry.type if entry else None
            case t.ClassSpec(_, cname):
                cdecl = resolver.find_type({cname})
                if not cdecl or len(cdecl) > 1:
                    raise ValueError("A resolved class is later resolving incorrectly. Probably a compiler bug.")
                cdecl = cdecl[0].statement
                if not isinstance(cdecl, s.ClassStatement):
                    raise ValueError("A resolved class is later resolving to a wrong type. Probably a compiler bug.")
                datas = cdecl.find_data(resolver, {self.name})
                if datas and len(datas) == 1:
                    return datas[0].statement.get_type()
            case t.EnumSpec(all_fields=fields):
                return next((ft for fn, ft in fields if fn == self.name), None)
        return None


    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) ->  tuple[DotExpression, list[s.Statement]]:
        base, new_statements = self.base.compile(resolver, None)
        name = self.name

        btype = base.get_type(resolver)
        match btype:
            case t.TupleSpec():
                pass  # field name is already the tuple entry name
            case t.ClassSpec(_, cname):
                cdecl = resolver.find_type({cname})
                if not cdecl or len(cdecl) > 1:
                    raise ValueError()
                cdecl = cdecl[0].statement
                if not isinstance(cdecl, s.ClassStatement):
                    raise ValueError()
                datas = _reduce_list(resolver, expected_type, cdecl.find_data(resolver, {self.name}))
                if len(datas) == 1:
                    name = datas[0].unique_name
            case t.EnumSpec(all_fields=fields):
                if '@' not in self.name:
                    match_field = next(((fn, ft) for fn, ft in fields if g.match_name(fn, self.name)), None)
                    if match_field:
                        name = match_field[0]

        expr = dataclasses.replace(self, base=base, name=name)
        return expr, new_statements

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        btype = self.base.get_type(resolver)
        match btype:
            case t.TupleSpec(entries=entries):
                entry = next((en for en in entries if en.name == self.name), None)
                if not entry:
                    return [Error(self.line_ref, f"Could not find field {self.name}")]
                return []
            case t.ClassSpec(_, cname):
                cdecl = resolver.find_type({cname})
                if not cdecl or len(cdecl) > 1:
                    raise ValueError()
                cdecl = cdecl[0].statement
                if not isinstance(cdecl, s.ClassStatement):
                    raise ValueError(self.line_ref, "Does not reference a class")
                datas = cdecl.find_data(resolver, {self.name})
                if not datas:
                    return [Error(self.line_ref, f"Could not find a field named {self.name}")]
                if len(datas) > 1:
                    return [Error(self.line_ref, f"Ambiguous reference to field named {self.name}")]
            case t.EnumSpec(all_fields=fields):
                if not any(fn == self.name or g.match_name(fn, self.name) for fn, _ in fields):
                    return [Error(self.line_ref, f"Could not find field {self.name}")]
                return []
        return []

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        base_bundle = self.base.generate(resolver)
        btype = self.base.get_type(resolver)
        match btype:
            case t.TupleSpec(entries=entries):
                idx = next((i for i, en in enumerate(entries) if en.name == self.name), None)
                if idx is None:
                    raise ValueError(f"Field {self.name} not found in TupleSpec")
                result_var = cg_p.StructField(base_bundle.result_var, f"_{idx}")
                return base_bundle + g.OperationBundle((), (), result_var)

            case t.ClassSpec(_, cname):
                cdecl = cast(s.ClassStatement, resolver.find_type({cname})[0].statement)
                data = cdecl.find_data(resolver, {self.name})[0].statement
                xtype = data.get_type().generate()

                if not isinstance(data, s.FunctionStatement):
                    result_var = cg_p.ObjectField(xtype, base_bundle.result_var, cdecl.name, data.name, None)
                elif "final" not in cdecl.attributes:
                    result_var = cg_p.VirtualFunction(data.name, base_bundle.result_var)
                else:
                    result_var = cg_p.GlobalFunction(data.name, base_bundle.result_var, c_symbol=_foreign_symbol(data), impure=_is_impure(data), sync=_is_sync(data))

                return base_bundle + g.OperationBundle(stack_vars=(), operations=(), result_var=result_var)

            case t.EnumSpec() as es:
                if es.is_complex:
                    # Complex enum is a heap pointer; field access goes
                    # through ObjectField (which inserts a GC write barrier
                    # for pointer-typed writes).
                    field_type_spec = next((ft for fn, ft in es.all_fields if fn == self.name), None)
                    fty = field_type_spec.generate() if field_type_spec is not None else cg_t.DataPointer()
                    result_var = cg_p.ObjectField(fty, base_bundle.result_var, es.root_name, self.name, None)
                else:
                    result_var = cg_p.StructField(base_bundle.result_var, self.name)
                return base_bundle + g.OperationBundle((), (), result_var)

        raise ValueError("Could not generate dot expression")


def _reduce_list(resolver: g.Resolver, expected_type: t.TypeSpec | None, list_data: list[g.Resolved[s.DataStatement]]) -> list[g.Resolved[s.DataStatement]]:
    if len(list_data) <= 1:
        return list_data
    result_list = []
    for x in list_data:
        other_type = x.statement.get_type()
        # Apply trait type param substitution so e.g. Plus<Int>.+ has effective type
        # (Int,Int)->Int rather than (TVal,TVal)->TVal, enabling correct disambiguation.
        if (x.scope == g.ResolvedScope.TRAIT
                and x.trait_scope is not None
                and x.owner_class is not None):
            mapping = {p.name: c for p, c in zip(x.owner_class.type_params, x.trait_scope.type_params)}
            if mapping and other_type:
                def replace_fn(_, thing, m=mapping):
                    if isinstance(thing, t.GenericPlaceholderSpec) and thing.name in m:
                        return m[thing.name]
                    return thing
                other_type = other_type.search_and_replace(resolver, replace_fn)
        b = t.trivially_assignable_equals(resolver, expected_type, other_type)
        if b is None or b: # Might be assignable
            result_list.append(x)
    return result_list


@dataclass
class NamedExpression(Expression):
    name: str
    type_params: tuple[t.TypeSpec, ...] = ()
    resolved_trait_scope: t.ClassSpec | None = field(default=None, compare=False)


    def __post_init__(self):
        if self.name == 'this':
            pass


    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        # If the name resolves to just one statement we have a known type
        # The name might actually resolve to just one, or we might have gone
        # through a compile step and found the unique name of a type match.
        # Both outcomes are fine.
        datas = resolver.find_data({self.name})
        # compile() already disambiguated via resolved_trait_scope; filter to that scope
        if len(datas) > 1 and self.resolved_trait_scope is not None:
            filtered = [d for d in datas if d.trait_scope == self.resolved_trait_scope]
            if len(filtered) == 1:
                datas = filtered
        if len(datas) != 1:
            return None
        resolved = datas[0]
        statement = resolved.statement
        raw_type = statement.get_type()
        if raw_type is None:
            return None

        mapping: dict[str, t.TypeSpec] = {}

        # Case 1: explicit type params on the call site (e.g., doNothing<Int>)
        if self.type_params and hasattr(statement, 'type_params') and statement.type_params:
            for placeholder, concrete in zip(statement.type_params, self.type_params):
                mapping[placeholder.name] = concrete

        # Case 2: resolved via a 'where' clause trait — map the interface's type params
        # to the concrete types recorded in the trait_scope on this Resolved instance.
        if (resolved.scope == g.ResolvedScope.TRAIT
                and resolved.trait_scope is not None
                and resolved.owner_class is not None):
            for placeholder, concrete in zip(resolved.owner_class.type_params,
                                             resolved.trait_scope.type_params):
                mapping[placeholder.name] = concrete

        if not mapping:
            return raw_type
        def replace_fn(_, thing):
            if isinstance(thing, t.GenericPlaceholderSpec) and thing.name in mapping:
                return mapping[thing.name]
            return thing
        return raw_type.search_and_replace(resolver, replace_fn)

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,Any],Any]) -> Expression:
        rts = self.resolved_trait_scope.search_and_replace(resolver, replace) if self.resolved_trait_scope is not None else None
        return cast(Expression, replace(resolver, dataclasses.replace(self,
            type_params=tuple(tp.search_and_replace(resolver, replace) for tp in self.type_params),
            resolved_trait_scope=rts if isinstance(rts, t.ClassSpec) else None)))

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement]]:
        if self.name == 'this':
            pass
        # Resolve the statement this name refers to. Once the name is fully
        # qualified (@-hash) we skip the ambiguity check but still run the
        # generic-inference step below, because the argument types feeding
        # inference may only become known on a later iteration of the
        # compile loop.
        datas = resolver.find_data({self.name})
        if '@' not in self.name:
            datas = _reduce_list(resolver, expected_type, datas)
            if len(datas) != 1:
                return self, [] # didn't find a unique candidate
            data = datas[0]
            if data.scope == g.ResolvedScope.MEMBER:
                this = NamedExpression(self.line_ref, "this")
                dot = DotExpression(self.line_ref, this, data.unique_name)
                return dot, []
            new_name = data.unique_name
            trait_scope = (data.trait_scope
                           if data.scope == g.ResolvedScope.TRAIT
                           and isinstance(data.trait_scope, t.ClassSpec)
                           else None)
        else:
            if len(datas) != 1:
                return self, []
            data = datas[0]
            new_name = self.name
            trait_scope = self.resolved_trait_scope

        # Generic type-parameter inference: if the resolved statement has
        # type_params and the call site supplied none, try to match the
        # statement's declared signature against the expected_type from the
        # enclosing CallExpression to fill them in.
        type_params_to_compile: tuple[t.TypeSpec, ...] = self.type_params
        stmt = data.statement
        stmt_type_params = getattr(stmt, "type_params", None) or ()
        if (not self.type_params
                and stmt_type_params
                and isinstance(expected_type, t.CallableSpec)):
            placeholder_names = {tp.name for tp in stmt_type_params}
            declared = stmt.get_type() if hasattr(stmt, "get_type") else None
            if isinstance(declared, t.CallableSpec):
                mapping = t.unify_generic(declared.parameters, expected_type.parameters, placeholder_names)
                if (mapping is not None
                        and declared.result is not None
                        and expected_type.result is not None):
                    mapping = t.unify_generic(declared.result, expected_type.result,
                                              placeholder_names, mapping)
                if mapping is not None and all(p.name in mapping for p in stmt_type_params):
                    type_params_to_compile = tuple(mapping[p.name] for p in stmt_type_params)

        type_params, new_statements = u.flatten_lists(x.compile(resolver) for x in type_params_to_compile)
        return dataclasses.replace(self, name=new_name, type_params=tuple(type_params), resolved_trait_scope=trait_scope), new_statements

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        tp_errors = [te for tp in self.type_params for te in tp.check(resolver)]
        datas = resolver.find_data({self.name})
        # compile() already disambiguated via resolved_trait_scope; filter to that scope
        if len(datas) > 1 and self.resolved_trait_scope is not None:
            filtered = [d for d in datas if d.trait_scope == self.resolved_trait_scope]
            if len(filtered) == 1:
                datas = filtered
        match datas:
            case []:
                return [Error(self.line_ref, f"Failed to resolve {self.name}")] + tp_errors
            case [resolved]:
                return resolved.statement.check_caller_type_params(resolver, self.type_params, self.line_ref) + tp_errors
            case _:
                return [Error(self.line_ref, f"Resolved too many {self.name}")] + tp_errors

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        if self.name == 'this':
            pass
        x = resolver.find_data({self.name})
        if not x:
            raise ValueError(f"Could not find {self.name}")
        x = x[0]
        match (x.scope, x.statement):
            case (g.ResolvedScope.GLOBAL, stmt) if isinstance(stmt, s.FunctionStatement):
                return g.OperationBundle((), (), cg_p.GlobalFunction(self.name, c_symbol=_foreign_symbol(stmt), impure=_is_impure(stmt), sync=_is_sync(stmt)))
            case (g.ResolvedScope.GLOBAL, stmt) if isinstance(stmt, s.LetStatement):
                xtype = stmt.declared_type
                if not xtype: raise ValueError(f"Failed to resolve {self.name} due to missing type")
                return g.OperationBundle((), (), cg_p.GlobalVar(xtype.generate(), self.name))
            case (g.ResolvedScope.LOCAL, stmt) if isinstance(stmt, s.LetStatement):
                xtype = stmt.declared_type
                if not xtype: raise ValueError(f"Failed to resolve {self.name} due to missing type")
                return g.OperationBundle((), (), cg_p.StackVar(xtype.generate(), self.name))
            case (scope, stmt):
                raise ValueError(f"Reference to {scope} / {type(stmt)} for named reference {self.name} not implemented yet")


@dataclass
class StringExpression(Expression):
    value: str

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        return t.BuiltinSpec(self.line_ref, "str")

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement]]:
        return self, []

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        return []

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        xexpr = cg_p.String(self.value)
        return g.OperationBundle( (), (), xexpr )


@dataclass
class IntegerExpression(Expression):
    value: int
    precision: int = 0

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        return t.BuiltinSpec(self.line_ref, f"int{self.precision}" if self.precision else "bigint")

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement]]:
        return self, []

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        return []

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        xexpr = cg_p.Integer(self.value, self.precision)
        return g.OperationBundle( (), (), xexpr )


@dataclass
class FloatExpression(Expression):
    value: float
    precision: int = 64

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        return t.BuiltinSpec(self.line_ref, f"float{self.precision}")

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement]]:
        return self, []

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        return []

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        xexpr = cg_p.Float(self.value, self.precision)
        return g.OperationBundle( (), (), xexpr )


@dataclass
class BuiltinOpExpression(Expression):
    type: t.BuiltinSpec
    op: StringExpression
    params: Expression

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,Any],Any]) -> Expression:
        return cast(Expression, replace(resolver, dataclasses.replace(self,
            type=self.type.search_and_replace(resolver, replace),
            params=self.params.search_and_replace(resolver, replace))))

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        return self.type

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) ->  tuple[Expression, list[s.Statement]]:
        new_params, new_statements = self.params.compile(resolver, None)
        expr = dataclasses.replace(self, params=new_params)
        return expr, list(new_statements)

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        return self.params.check(resolver, None)

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        params_bundle = self.params.generate(resolver)
        if params_bundle.result_var is None:
            raise ValueError("BuiltinOpExpression has no parameters")
        ptype = params_bundle.result_var.get_type()
        if not isinstance(ptype, cg_t.Struct):
            raise ValueError("BuiltinOpExpression parameters must be tuple")

        xtype = self.type.generate()
        xexpr = cg_p.Invoke(self.op.value, params_bundle.result_var, xtype)
        final_bundle = g.OperationBundle( (), (), xexpr )

        return params_bundle + final_bundle


@dataclass
class LambdaExpression(Expression):
    parameters: s.DestructureStatement
    expression: Expression
    return_type: t.CallableSpec | None = None

    def _find_locals(self, names: set[str]) -> list[g.Resolved[s.DataStatement]]:
        p = [g.Resolved(let.name, let, g.ResolvedScope.LOCAL)
             for let in self.parameters.flatten()
             if g.match_names(let.name, names)]
        return p

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver, Any],Any]) -> Expression:
        nested_resolver = g.ResolverData(resolver, self._find_locals)
        return cast(Expression, replace(resolver, dataclasses.replace(
            self,
            parameters=cast(s.DestructureStatement, self.parameters.search_and_replace(resolver, replace)),
            expression=self.expression.search_and_replace(nested_resolver, replace),
            return_type=self.return_type.search_and_replace(resolver, replace) if self.return_type else None)))

    def get_type(self, resolver: g.Resolver) -> t.CallableSpec | None:
        return self.return_type

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement]]:
        # Include parameters in data resolution hierarchy
        resolver = g.ResolverData(resolver, self._find_locals)

        # Compile the parameter types
        new_prm, new_prm_glb = self.parameters.compile(resolver, None)

        # Compile the expression
        sub_expected_type = expected_type.result if isinstance(expected_type, t.CallableSpec) else None
        new_xpr, new_xpr_glb = self.expression.compile(resolver, sub_expected_type)

        # Calculate the return type. Prefer the expected result type from the
        # enclosing call site — that way a lambda whose body is narrower than
        # the declared parameter widens via boxing, and the call's parameter
        # check sees matching types.
        body_type = new_xpr.get_type(resolver)
        if (sub_expected_type is not None
                and body_type is not None
                and sub_expected_type.is_concrete()
                and sub_expected_type.trivially_assignable_from(resolver, body_type) is True):
            new_ret_result = sub_expected_type
        else:
            new_ret_result = body_type
        new_ret = t.CallableSpec(self.line_ref, self.parameters.get_type(), new_ret_result)

        return dataclasses.replace(
            self, parameters=new_prm, expression=new_xpr,
            return_type=new_ret), (new_prm_glb + new_xpr_glb)

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        # Include parameters in data resolution hierarchy
        resolver = g.ResolverData(resolver, self._find_locals)

        sub_expected_type = expected_type.result if isinstance(expected_type, t.CallableSpec) else None
        prm_err = self.parameters.check(resolver, None)
        xpr_err = self.expression.check(resolver, sub_expected_type)
        ret_err = self.return_type.check(resolver) if self.return_type else [Error(self.line_ref, "Lambda return type is unknown")]
        return prm_err + xpr_err + ret_err

    def generate(self, glb: g.Resolver) -> g.OperationBundle:
        raise ValueError("Lambda code generation is not directly supported. Code lowering should have got rid of this. Look there and keep this error.")


@dataclass
class BlockExpression(Expression):
    """A sequence of statements followed by a value expression.

    Used as the body of FunctionStatement and produced by the inliner
    when a call is substituted at expression position.
    """
    statements: list[s.Statement]
    value: Expression

    def _find_locals(self) -> Callable[[set[str]], list[g.Resolved]]:
        def finder(names: set[str]) -> list[g.Resolved]:
            return [g.Resolved(let.name, let, g.ResolvedScope.LOCAL)
                    for x in self.statements
                    if isinstance(x, s.LetStatement)
                    for let in x.flatten()
                    if g.match_names(let.name, names)]
        return finder

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver, Any], Any]) -> Expression:
        nested = g.ResolverData(resolver, self._find_locals())
        new_stmts = [x.search_and_replace(nested, replace) for x in self.statements]
        new_val = self.value.search_and_replace(nested, replace)
        return cast(Expression, replace(resolver, dataclasses.replace(self, statements=new_stmts, value=new_val)))

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        nested = g.ResolverData(resolver, self._find_locals())
        return self.value.get_type(nested)

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement]]:
        nested = g.ResolverData(resolver, self._find_locals())
        stmt_results = [x.compile(nested, expected_type) for x in self.statements]
        new_stmts = [r[0] for r in stmt_results if r[0]]
        glbs: list[s.Statement] = [g for r in stmt_results for g in r[1]]
        new_val, val_glbs = self.value.compile(nested, expected_type)
        return dataclasses.replace(self, statements=new_stmts, value=new_val), glbs + val_glbs

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        nested = g.ResolverData(resolver, self._find_locals())
        stmt_errs = [err for x in self.statements for err in x.check(nested, expected_type)]
        val_errs = self.value.check(nested, expected_type)
        if not val_errs and expected_type is not None:
            xtype = self.value.get_type(nested)
            if xtype is not None and not t.trivially_assignable_equals(nested, expected_type, xtype):
                val_errs = [Error(self.value.line_ref, "Incorrect type")]
        return stmt_errs + val_errs

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        nested = g.ResolverData(resolver, self._find_locals())
        bundle = g.OperationBundle()
        for i, stmt in enumerate(self.statements):
            bundle = bundle + stmt.generate(nested, None).rename_vars(f"b{i}_")
        return bundle + self.value.generate(nested)


@dataclass
class NothingExpression(Expression):
    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,Any],Any]) -> Expression:
        return cast(Expression, replace(resolver, self))

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        return None

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement]]:
        return self, []

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        return []

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        return g.OperationBundle()


@dataclass
class TupleEntryExpression:
    name: str|None
    value: Expression

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,Any],Any]) -> TupleEntryExpression:
        return dataclasses.replace(self,
            value=self.value.search_and_replace(resolver, replace))

    def get_type(self, resolver: g.Resolver) -> t.TupleSpec | None:
        return self.value.get_type(resolver)

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[TupleEntryExpression, list[s.Statement]]:
        new_value, new_statements = self.value.compile(resolver, expected_type)
        return dataclasses.replace(self, value=new_value), new_statements

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        return self.value.check(resolver, expected_type)

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        return self.value.generate(resolver)


@dataclass
class TupleExpression(Expression):
    expressions: list[TupleEntryExpression]

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,Any],Any]) -> Expression:
        return cast(Expression, replace(resolver, dataclasses.replace(self,
            expressions=[x.search_and_replace(resolver, replace) for x in self.expressions])))

    def get_type(self, resolver: g.Resolver) -> t.TupleSpec | None:
        entries = [t.TupleEntrySpec(x.name, x.get_type(resolver)) for x in self.expressions]
        return t.TupleSpec(self.line_ref, entries = entries)

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement]]:
        expected_entries = expected_type.entries if isinstance(expected_type, t.TupleSpec) else []
        def entry_expected(i: int) -> t.TypeSpec | None:
            return expected_entries[i].type if i < len(expected_entries) else None
        p = [x.compile(resolver, entry_expected(i)) for i, x in enumerate(self.expressions)]
        new_expressions, new_statements_lists = zip(*p) if p else ([], [])
        expr = dataclasses.replace(self, expressions=list(new_expressions))
        return expr, list(x for l in new_statements_lists for x in l)

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        # TODO: Breakdown expected_type and pass it into the check function
        errors = [e for x in self.expressions for e in x.check(resolver, None)]
        return errors or []

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        param_bundles = [expr.generate(resolver).rename_vars(f"{index}_") for index, expr in enumerate(self.expressions)]
        # xtype = self.get_type(resolver).generate()
        value = cg_p.NewStruct(tuple(((f"_{idx}", x.result_var) for idx, x in enumerate(param_bundles))))
        final_bundle = g.OperationBundle((), (), value)
        total_bundle = reduce(lambda x, y: y + x, reversed(param_bundles), final_bundle)
        return total_bundle

    def trim_left(self, amount: int) -> TupleExpression:
        return dataclasses.replace(self, expressions=self.expressions[amount:])


@dataclass
class TernaryExpression(Expression):
    condition: Expression
    trueResult: Expression
    falseResult: Expression

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,Any],Any]) -> Expression:
        return cast(Expression, replace(resolver, dataclasses.replace(self,
            condition=self.condition.search_and_replace(resolver, replace),
            trueResult=self.trueResult.search_and_replace(resolver, replace),
            falseResult=self.falseResult.search_and_replace(resolver, replace))))

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        trueType = self.trueResult.get_type(resolver)
        falseType = self.falseResult.get_type(resolver)
        if not trueType: return falseType
        if not falseType: return trueType
        return falseType if falseType.trivially_assignable_from(resolver, trueType) else trueType

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement]]:
        condition, conditionStatements = self.condition.compile(resolver, t.Bool())
        trueResult, trueStatements = self.trueResult.compile(resolver, self.falseResult.get_type(resolver))
        falseResult, falseStatements = self.falseResult.compile(resolver, self.trueResult.get_type(resolver))
        return (dataclasses.replace(self, condition=condition, trueResult=trueResult, falseResult=falseResult),
                conditionStatements + trueStatements + falseStatements)

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        cond_err = self.condition.check(resolver, t.Bool())
        true_err = self.trueResult.check(resolver, expected_type)
        false_err = self.falseResult.check(resolver, expected_type)
        self_err = [] if self.get_type(resolver) else [Error(self.line_ref, "Failed to resolve type of ternery expression")]
        return cond_err + true_err + false_err + self_err

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        result_var = cg_p.StackVar(self.get_type(resolver).generate(), "result")

        cond_bundle = self.condition.generate(resolver).rename_vars("a")
        cond_bundle_suffix = g.OperationBundle(
            operations=(cg_o.JumpIf("on_true", cond_bundle.result_var),))

        false_bundle = self.falseResult.generate(resolver).rename_vars("b")
        false_bundle_suffix = g.OperationBundle(
            operations=(cg_o.Move(result_var, false_bundle.result_var), cg_o.Jump("end"), cg_o.Label("on_true")))

        true_bundle = self.trueResult.generate(resolver).rename_vars("c")
        true_bundle_suffix = g.OperationBundle(
            stack_vars=(result_var,),
            operations=(cg_o.Move(result_var, true_bundle.result_var), cg_o.Label("end")),
            result_var=result_var)

        result = (cond_bundle + cond_bundle_suffix + false_bundle + false_bundle_suffix + true_bundle + true_bundle_suffix)

        return result.rename_vars("")



@dataclass
class BoxExpression(Expression):
    """Widen a value of a variant type into its enclosing union type."""
    inner: Expression
    union_spec: t.CombinationSpec

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver, Any], Any]) -> Expression:
        return cast(Expression, replace(resolver, dataclasses.replace(self,
            inner=self.inner.search_and_replace(resolver, replace),
            union_spec=cast(t.CombinationSpec, self.union_spec.search_and_replace(resolver, replace)))))

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec:
        return self.union_spec

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement]]:
        inner, stmts = self.inner.compile(resolver, None)
        union_spec, spec_stmts = self.union_spec.compile(resolver)
        return dataclasses.replace(self, inner=inner, union_spec=cast(t.CombinationSpec, union_spec)), stmts + spec_stmts

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        return self.inner.check(resolver, None)

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        inner_bundle = self.inner.generate(resolver)
        target_ctype = self.union_spec.generate()

        # DataPointer union: exactly one non-unit pointer variant + optional unit (None)
        if isinstance(target_ctype, cg_t.DataPointer):
            inner_ctype = self.inner.get_type(resolver).generate()
            if inner_ctype == cg_t.Struct(()):  # unit/None variant
                return g.OperationBundle(inner_bundle.stack_vars, inner_bundle.operations, cg_p.NullPointer())
            return inner_bundle  # Already a DataPointer — pass through

        # UnionContainer union
        assert isinstance(target_ctype, cg_t.UnionContainer), f"Expected UnionContainer, got {target_ctype}"
        variant_types = [v.generate() for v in self.union_spec.types]
        _, variant_map = cg_t.UnionContainer.compute(variant_types)

        inner_ctype = self.inner.get_type(resolver).generate()
        variant_idx = next(i for i, vt in enumerate(variant_types) if vt == inner_ctype)

        discriminators = resolver.get_discriminators()
        tag_value = discriminators.get(self.union_spec.types[variant_idx].as_unique_id_str(), 0)
        slot_values = self.__build_variant_slots(inner_ctype, inner_bundle, variant_map[variant_idx], target_ctype.slots)
        slot_values.append(("$tag", cg_p.Integer(tag_value, 32)))
        return inner_bundle + g.OperationBundle((), (), cg_p.union_struct(target_ctype, dict(slot_values)))

    def __build_variant_slots(self, inner_ctype, inner_bundle, slot_assignments, slot_fields):
        """Map the inner value's primitives to their union slots; returns slot (name, value) pairs."""
        inner_prims = cg_t._flatten_primitives(inner_ctype)
        if len(inner_prims) == 0:
            return []  # unit variant: no slot values
        if len(inner_prims) == 1:
            si, _ = slot_assignments[0]
            if isinstance(inner_ctype, cg_t.Struct):
                field_name = inner_ctype.fields[0][0]
                return [(slot_fields[si][0], cg_p.StructField(inner_bundle.result_var, field_name))]
            return [(slot_fields[si][0], inner_bundle.result_var)]
        # Multi-primitive variant: inner must be a flat Struct; map each field to its union slot.
        assert isinstance(inner_ctype, cg_t.Struct), \
            f"Boxing multi-primitive non-struct type {inner_ctype} not yet supported"
        result = []
        for prim_idx, (field_name, field_type) in enumerate(inner_ctype.fields):
            assert len(cg_t._flatten_primitives(field_type)) == 1, \
                f"Nested multi-primitive struct field '{field_name}: {field_type}' in boxing not yet supported"
            si, _ = slot_assignments[prim_idx]
            result.append((slot_fields[si][0], cg_p.StructField(inner_bundle.result_var, field_name)))
        return result


@dataclass
class WideExpression(Expression):
    """Widen a value of one union type to a strictly wider union type.

    Handles DataPointer → UnionContainer (null-check) and
    UnionContainer → UnionContainer (tag-based re-slot) widening.
    """
    inner: Expression
    source_spec: t.CombinationSpec
    target_spec: t.CombinationSpec

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver, Any], Any]) -> Expression:
        return cast(Expression, replace(resolver, dataclasses.replace(self,
            inner=self.inner.search_and_replace(resolver, replace),
            source_spec=cast(t.CombinationSpec, self.source_spec.search_and_replace(resolver, replace)),
            target_spec=cast(t.CombinationSpec, self.target_spec.search_and_replace(resolver, replace)))))

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec:
        return self.target_spec

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement]]:
        inner, stmts = self.inner.compile(resolver, None)
        src, src_stmts = self.source_spec.compile(resolver)
        tgt, tgt_stmts = self.target_spec.compile(resolver)
        return dataclasses.replace(self,
            inner=inner,
            source_spec=cast(t.CombinationSpec, src),
            target_spec=cast(t.CombinationSpec, tgt)), stmts + src_stmts + tgt_stmts

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        return self.inner.check(resolver, None)

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        inner_bundle = self.inner.generate(resolver)
        src_ctype = self.source_spec.generate()
        tgt_ctype = self.target_spec.generate()

        # DataPointer → DataPointer widening is a pass-through. Both unions use
        # the same tag-bit-dispatch encoding, and every variant in the source
        # spec is also a variant in the target spec with identical pointer
        # representation.
        if isinstance(tgt_ctype, cg_t.DataPointer):
            assert isinstance(src_ctype, cg_t.DataPointer), \
                f"WideExpression: DataPointer target requires DataPointer source, got {src_ctype}"
            return inner_bundle

        assert isinstance(tgt_ctype, cg_t.UnionContainer), \
            f"WideExpression: target must be UnionContainer, got {tgt_ctype}"

        tgt_container, tgt_variant_map = cg_t.UnionContainer.compute([v.generate() for v in self.target_spec.types])
        discriminators = resolver.get_discriminators()
        result_var = cg_p.StackVar(tgt_ctype, "wide_result")
        end_label = "wide_end"
        sv = inner_bundle.result_var

        if isinstance(src_ctype, cg_t.DataPointer):
            body = self.__widen_from_datapointer(
                sv, src_ctype, tgt_ctype, tgt_variant_map, tgt_container.slots, discriminators, result_var, end_label)
        else:
            assert isinstance(src_ctype, cg_t.UnionContainer), \
                f"WideExpression: source must be DataPointer or UnionContainer, got {src_ctype}"
            body = self.__widen_from_container(
                sv, src_ctype, tgt_ctype, tgt_variant_map, tgt_container.slots, discriminators, result_var, end_label)

        bundles = [inner_bundle] + body + [g.OperationBundle(operations=(cg_o.Label(end_label),), result_var=result_var)]
        return reduce(lambda a, b: a + b, bundles).rename_vars("")

    def __widen_from_datapointer(self, sv, src_ctype, tgt_ctype, tgt_variant_map, tgt_slot_fields,
                                  discriminators, result_var, end_label):
        """Widen a DataPointer union (null = unit/None, non-null = pointer variant) to a UnionContainer."""
        unit_type = cg_t.Struct(())
        src_variant_types = [v.generate() for v in self.source_spec.types]
        ptr_variant = next((v for v, vt in zip(self.source_spec.types, src_variant_types) if vt != unit_type), None)
        unit_variant = next((v for v, vt in zip(self.source_spec.types, src_variant_types) if vt == unit_type), None)
        assert ptr_variant is not None, "DataPointer union must have a non-unit pointer variant"

        null_label = "wide_null"
        ptr_uid = ptr_variant.as_unique_id_str()
        ptr_tag = discriminators.get(ptr_uid, 0)
        tgt_ptr_idx = next((i for i, v in enumerate(self.target_spec.types) if v.as_unique_id_str() == ptr_uid), None)
        slot_values = [(tgt_slot_fields[tgt_si][0], sv) for tgt_si, _ in tgt_variant_map[tgt_ptr_idx]] \
            if tgt_ptr_idx is not None else []
        slot_values.append(("$tag", cg_p.Integer(ptr_tag, 32)))

        unit_tag = discriminators.get(unit_variant.as_unique_id_str(), 0) if unit_variant else 0

        return [
            g.OperationBundle(operations=(cg_o.JumpIf(null_label, cg_p.IntEqConst(sv, 0)),)),
            g.OperationBundle(stack_vars=(result_var,),
                              operations=(cg_o.Move(result_var, cg_p.union_struct(tgt_ctype, dict(slot_values))),)),
            g.OperationBundle(operations=(cg_o.Jump(end_label), cg_o.Label(null_label))),
            g.OperationBundle(operations=(cg_o.Move(result_var,
                                                     cg_p.union_struct(tgt_ctype, {"$tag": cg_p.Integer(unit_tag, 32)})),)),
        ]

    def __widen_from_container(self, sv, src_ctype, tgt_ctype, tgt_variant_map, tgt_slot_fields,
                                discriminators, result_var, end_label):
        """Widen a UnionContainer to a wider UnionContainer by re-slotting each variant."""
        src_variant_types = [v.generate() for v in self.source_spec.types]
        _, src_variant_map = cg_t.UnionContainer.compute(src_variant_types)
        src_tag_field = cg_p.StructField(sv, "$tag")

        bundles = []
        first_arm = True
        for i, src_var in enumerate(self.source_spec.types):
            var_uid = src_var.as_unique_id_str()
            var_tag = discriminators.get(var_uid, 0)
            arm_label, next_label = f"wide_arm_{i}", f"wide_next_{i}"

            tgt_var_idx = next(
                (ti for ti, tv in enumerate(self.target_spec.types) if tv.as_unique_id_str() == var_uid), None)
            slot_values = []
            if tgt_var_idx is not None:
                for pi in range(len(cg_t._flatten_primitives(src_var.generate()))):
                    tgt_si, _ = tgt_variant_map[tgt_var_idx][pi]
                    src_si, _ = src_variant_map[i][pi]
                    slot_values.append((tgt_slot_fields[tgt_si][0], cg_p.StructField(sv, src_ctype.slots[src_si][0])))
            slot_values.append(("$tag", cg_p.Integer(var_tag, 32)))

            bundles.append(g.OperationBundle(operations=(
                cg_o.JumpIf(arm_label, cg_p.IntEqConst(src_tag_field, var_tag)),
                cg_o.Jump(next_label), cg_o.Label(arm_label),
            )))
            bundles.append(g.OperationBundle(
                stack_vars=(result_var,) if first_arm else (),
                operations=(cg_o.Move(result_var, cg_p.union_struct(tgt_ctype, dict(slot_values))),
                             cg_o.Jump(end_label))))
            bundles.append(g.OperationBundle(operations=(cg_o.Label(next_label),)))
            first_arm = False
        # All source variants are enumerated; any tag outside that set is
        # unreachable at runtime.  Make that explicit so the end-label join
        # has no uninitialised-result path.
        bundles.append(g.OperationBundle(operations=(
            cg_o.Abort(reason="container-widening fell through all source variants"),)))
        return bundles


@dataclass
class NewEnumExpression(Expression):
    root_spec_name: str
    leaf_name: str
    field_args: dict[str, Expression]

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        types = resolver.find_type({self.root_spec_name})
        if len(types) == 1 and isinstance(types[0].statement, s.EnumStatement):
            return types[0].statement._enum_spec
        return None

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[NewEnumExpression, list[s.Statement]]:
        new_field_args: dict[str, Expression] = {}
        all_stmts: list[s.Statement] = []
        for fname, fexpr in self.field_args.items():
            new_fexpr, stmts = fexpr.compile(resolver, None)
            new_field_args[fname] = new_fexpr
            all_stmts.extend(stmts)
        return dataclasses.replace(self, field_args=new_field_args), all_stmts

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        errors: list[Error] = []
        for fname, fexpr in self.field_args.items():
            errors += fexpr.check(resolver, None)
        return errors

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver, Any], Any]) -> Expression:
        new_field_args = {k: v.search_and_replace(resolver, replace) for k, v in self.field_args.items()}
        return cast(Expression, replace(resolver, dataclasses.replace(self, field_args=new_field_args)))

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        types = resolver.find_type({self.root_spec_name})
        assert len(types) == 1
        root_stmt = cast(s.EnumStatement, types[0].statement)
        root_spec = root_stmt._enum_spec
        assert root_spec is not None
        leaf_idx = root_spec.all_leaf_names.index(self.leaf_name)
        tag_const = cg_p.Integer(leaf_idx, 32)

        if root_spec.is_complex:
            # Heap-allocated path: NewObject + per-field ObjectField writes,
            # mirroring the class constructor at expression.py:127-130.
            result_var = cg_p.StackVar(cg_t.DataPointer(), "result")
            ops: list[cg_o.Op] = [
                cg_o.NewObject(root_spec.root_name, result_var),
                cg_o.Move(
                    cg_p.ObjectField(cg_t.Int(32), result_var, root_spec.root_name, "$tag", None),
                    tag_const),
            ]
            bundles: list[g.OperationBundle] = []
            for idx, (field_name, field_type_spec) in enumerate(root_spec.all_fields[1:]):
                fty = field_type_spec.generate()
                if field_name in self.field_args:
                    arg_bundle = self.field_args[field_name].generate(resolver).rename_vars(f"arg{idx}_")
                    bundles.append(arg_bundle)
                    ops.append(cg_o.Move(
                        cg_p.ObjectField(fty, result_var, root_spec.root_name, field_name, None),
                        arg_bundle.result_var))
                else:
                    ops.append(cg_o.Move(
                        cg_p.ObjectField(fty, result_var, root_spec.root_name, field_name, None),
                        cg_p.ZeroOf(fty)))
            ctor_bundle = g.OperationBundle(
                stack_vars=(result_var,),
                operations=tuple(ops),
                result_var=result_var)
            if bundles:
                return reduce(lambda a, b: a + b, bundles + [ctor_bundle])
            return ctor_bundle

        # Non-recursive: flat by-value struct via NewStruct.
        bundles2: list[g.OperationBundle] = []
        field_values: list[tuple[str, cg_p.RParam]] = [("$tag", tag_const)]
        for idx, (field_name, field_type_spec) in enumerate(root_spec.all_fields[1:]):
            if field_name in self.field_args:
                arg_bundle = self.field_args[field_name].generate(resolver).rename_vars(f"arg{idx}_")
                bundles2.append(arg_bundle)
                field_values.append((field_name, arg_bundle.result_var))
            else:
                field_values.append((field_name, cg_p.ZeroOf(field_type_spec.generate())))
        result_param = cg_p.NewStruct(tuple(field_values))
        final_bundle = g.OperationBundle((), (), result_param)
        if bundles2:
            return reduce(lambda a, b: a + b, bundles2 + [final_bundle])
        return final_bundle
