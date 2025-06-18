from __future__ import annotations

from typing import Callable
import dataclasses
import pyast
from dataclasses import dataclass, field
from functools import reduce

from langtools import cast
from tokenizer import LineRef
from parselib import Error

import codegen.ops as cg_o
import codegen.param as cg_p
import codegen.typedecl as cg_t

import pyast.resolver as g
import pyast.statement as s
import pyast.typespec as t


@dataclass
class Expression:
    line_ref: LineRef

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        raise NotImplementedError()

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> (Expression, list[s.Statement]):
        raise NotImplementedError()

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        return []

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        raise NotImplementedError()

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,any],any]) -> Expression:
        return cast(Expression, replace(resolver, self))


@dataclass
class NewExpression(Expression):
    type: t.TypeSpec
    parameter: Expression

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,any],any]) -> Expression:
        return cast(Expression, replace(resolver, dataclasses.replace(self,
            parameter=self.parameter.search_and_replace(resolver, replace))))

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        return self.type

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> (Expression, list[s.Statement]):
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

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver, any],any]) -> Expression:
        return cast(Expression, replace(resolver, dataclasses.replace(self,
            function=self.function.search_and_replace(resolver, replace),
            parameter=self.parameter.search_and_replace(resolver, replace))))

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        func_type = self.function.get_type(resolver)
        return func_type.result if isinstance(func_type, t.CallableSpec) else None

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) ->  (Expression, list[s.Statement]):
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
        xtype = cast(t.CallableSpec, self.function.get_type(resolver))

        fun_op_bundle = self.function.generate(resolver).rename_vars(1)
        prm_op_bundle = self.parameter.generate(resolver).rename_vars(2)

        result_var = cg_p.StackVar(xtype.result.generate(), "result")
        call_bundle = g.OperationBundle(
            (result_var,),
            (  cg_o.Call(fun_op_bundle.result_var, prm_op_bundle.result_var, result_var),),
            result_var
        )

        return fun_op_bundle + prm_op_bundle + call_bundle


@dataclass
class DotExpression(Expression):
    base: Expression
    name: str

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,any],any]) -> Expression:
        return cast(Expression, replace(resolver, dataclasses.replace(self,
            base=self.base.search_and_replace(resolver, replace))))

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        btype = self.base.get_type(resolver)
        match btype:
            case t.TupleSpec(_, entries, _):
                raise ValueError("Dot operator on tuple not implemented yet")
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
        return None


    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) ->  (DotExpression, list[s.Statement]):
        base, new_statements = self.base.compile(resolver, None)
        name = self.name

        btype = base.get_type(resolver)
        match btype:
            case t.TupleSpec(_, entries, _):
                raise ValueError("Dot operator on tuple not implemented yet")
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

        expr = dataclasses.replace(self, base=base, name=name)
        return expr, new_statements

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        btype = self.base.get_type(resolver)
        match btype:
            case t.TupleSpec(_, entries, _):
                raise ValueError("Dot operator on tuple not implemented yet")
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
        return []

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        base_bundle = self.base.generate(resolver)
        btype = self.base.get_type(resolver)
        match btype:
            case t.TupleSpec(_, entries, _):
                raise ValueError("Dot operator on tuple not implemented yet")

            case t.ClassSpec(_, cname):
                cdecl = cast(s.ClassStatement, resolver.find_type({cname})[0].statement)
                data = cdecl.find_data(resolver, {self.name})[0].statement
                xtype = data.get_type().generate()

                if not isinstance(data, s.FunctionStatement):
                    result_var = cg_p.ObjectField(xtype, base_bundle.result_var, cdecl.name, data.name, None)
                elif "final" not in cdecl.attributes:
                    result_var = cg_p.VirtualFunction(data.name, base_bundle.result_var)
                else:
                    result_var = cg_p.GlobalFunction(data.name, base_bundle.result_var)

                return base_bundle + g.OperationBundle(stack_vars=(), operations=(), result_var=result_var)

        raise ValueError("Could not generate dot expression")


def _reduce_list(resolver: g.Resolver, expected_type: t.TypeSpec | None, list_data: list[g.Resolved[s.DataStatement]]) -> list[g.Resolved[s.DataStatement]]:
    if len(list_data) <= 1:
        return list_data
    result_list = []
    for x in list_data:
        other_type = x.statement.get_type()
        b = t.trivially_assignable_equals(resolver, expected_type, other_type)
        if b is None or b: # Might be assignable
            result_list.append(x)
    return result_list


@dataclass
class NamedExpression(Expression):
    name: str

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        # If the name resolves to just one statement we have a known type
        # The name might actually resolve to just one, or we might have gone
        # through a compile step and found the unique name of a type match.
        # Both outcomes are fine.
        datas = resolver.find_data({self.name})
        return datas[0].statement.get_type() if len(datas) == 1 else None

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> (Expression, list[s.Statement]):
        if '@' in self.name:
            return self, [] # Early exit because we previously succeeded
        datas_full_list = resolver.find_data({self.name})
        datas = _reduce_list(resolver, expected_type, datas_full_list)
        if len(datas) != 1:
            return self, [] # Early exit because we didn't find a unique candidate
        data = datas[0]
        if data.scope == g.ResolvedScope.MEMBER:
            this = NamedExpression(self.line_ref, "this")
            dot = DotExpression(self.line_ref, this, data.unique_name)
            return dot, []
        return dataclasses.replace(self, name=data.unique_name), []

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        datas = resolver.find_data({self.name})
        if not datas:
            return [Error(self.line_ref, f"Failed to resolve {self.name}")]
        if len(datas) > 1:
            return [Error(self.line_ref, f"Resolved too many {self.name}")]
        return []

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        x = resolver.find_data({self.name})
        if not x:
            raise ValueError(f"Could not find {self.name}")
        x = x[0]
        match (x.scope, x.statement):
            case (g.ResolvedScope.GLOBAL, stmt) if isinstance(stmt, s.FunctionStatement):
                return g.OperationBundle( (), (), cg_p.GlobalFunction(self.name) )
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

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> (Expression, list[s.Statement]):
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

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> (Expression, list[s.Statement]):
        return self, []

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        return []

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        xexpr = cg_p.Integer(self.value, self.precision)
        return g.OperationBundle( (), (), xexpr )


@dataclass
class BuiltinOpExpression(Expression):
    type: t.BuiltinSpec
    op: StringExpression
    params: Expression

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,any],any]) -> Expression:
        return cast(Expression, replace(resolver, dataclasses.replace(self,
            params=self.params.search_and_replace(resolver, replace))))

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        return self.type

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) ->  (Expression, list[s.Statement]):
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

    def __find_locals(self, names: set[str]) -> list[g.Resolved[s.DataStatement]]:
        p = [g.Resolved(let.name, let, g.ResolvedScope.LOCAL)
             for let in self.parameters.flatten()
             if g.match_names(let.name, names)]
        return p

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver, any],any]) -> Expression:
        nested_resolver = g.ResolverData(resolver, self.__find_locals)
        return cast(Expression, replace(resolver, dataclasses.replace(
            self,
            parameters=cast(s.DestructureStatement, self.parameters.search_and_replace(resolver, replace)),
            expression=self.expression.search_and_replace(nested_resolver, replace))))

    def get_type(self, resolver: g.Resolver) -> t.CallableSpec | None:
        return self.return_type

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> (Expression, list[s.Statement]):
        # Include parameters in data resolution hierarchy
        resolver = g.ResolverData(resolver, self.__find_locals)

        # Compile the parameter types
        new_prm, new_prm_glb = self.parameters.compile(resolver, None)

        # Compile the expression
        sub_expected_type = expected_type.result if isinstance(expected_type, t.CallableSpec) else None
        new_xpr, new_xpr_glb = self.expression.compile(resolver, sub_expected_type)

        # Calculate the return type from parameter types and expression
        new_sub_expected_type = new_xpr.get_type(resolver)
        new_ret = t.CallableSpec(self.line_ref, self.parameters.get_type(), new_sub_expected_type)

        return dataclasses.replace(
            self, parameters=new_prm, expression=new_xpr,
            return_type=new_ret), (new_prm_glb + new_xpr_glb)

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        # Include parameters in data resolution hierarchy
        resolver = g.ResolverData(resolver, self.__find_locals)

        sub_expected_type = expected_type.result if isinstance(expected_type, t.CallableSpec) else None
        prm_err = self.parameters.check(resolver, None)
        xpr_err = self.expression.check(resolver, sub_expected_type)
        ret_err = self.return_type.check(resolver) if self.return_type else [Error(self.line_ref, "Lambda return type is unknown")]
        return prm_err + xpr_err + ret_err

    def generate(self, glb: g.Resolver) -> g.OperationBundle:
        raise ValueError("Lambda code generation is not directly supported. Code lowering should have got rid of this. Look there and keep this error.")


@dataclass
class NothingExpression(Expression):
    declarations: list[s.Statement]

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,any],any]) -> Expression:
        return cast(Expression, replace(resolver, dataclasses.replace(self,
            declarations=[x.search_and_replace(resolver, replace) for x in self.declarations])))


@dataclass
class TupleEntryExpression:
    name: str|None
    value: Expression

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,any],any]) -> TupleEntryExpression:
        return dataclasses.replace(self,
            value=self.value.search_and_replace(resolver, replace))

    def get_type(self, resolver: g.Resolver) -> t.TupleSpec | None:
        return self.value.get_type(resolver)

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> (TupleEntryExpression, list[s.Statement]):
        new_value, new_statements = self.value.compile(resolver, expected_type)
        return dataclasses.replace(self, value = new_value), new_statements

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        return self.value.check(resolver, expected_type)

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        return self.value.generate(resolver)


@dataclass
class TupleExpression(Expression):
    expressions: list[TupleEntryExpression]

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,any],any]) -> Expression:
        return cast(Expression, replace(resolver, dataclasses.replace(self,
            expressions=[x.search_and_replace(resolver, replace) for x in self.expressions])))

    def get_type(self, resolver: g.Resolver) -> t.TupleSpec | None:
        entries = [t.TupleEntrySpec(x.name, x.get_type(resolver)) for x in self.expressions]
        return t.TupleSpec(self.line_ref, entries = entries)

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> (Expression, list[s.Statement]):
        # TODO: Split the expected type, if tuple, and pass it through
        p = [x.compile(resolver, None) for x in self.expressions]
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
class TerneryExpression(Expression):
    condition: Expression
    trueResult: Expression
    falseResult: Expression

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,any],any]) -> Expression:
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

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> (Expression, list[s.Statement]):
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
