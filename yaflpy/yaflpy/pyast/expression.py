from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Optional

from tokenizer import LineRef
from parselib import Error

import codegen.ops as cg_o
import codegen.param as cg_p
import codegen.typedecl as cg_t

import pyast.globalcontext as g
import pyast.statement as s
import pyast.typespec as t


@dataclass
class Expression:
    line_ref: LineRef

    def validate(self, gbl: g.Global) -> list[Error]:
        return []

    def get_type(self, glb: g.Global) -> t.TypeSpec|None:
        raise ValueError("Type not known")

    def to_c(self, glb: g.Global, fb: g.FunctionBuilder) -> str:
        var_expr, var_type = self.to_expr(glb, fb)
        var_name = fb.add_var(var_type)
        fb.add_op(cg_o.Move(cg_p.StackVar(var_name), var_expr))
        return var_name

    def to_expr(self, glb: g.Global, fb: g.FunctionBuilder) -> (cg_p.RParam, cg_t.Type):
        raise ValueError()

    def compile(self, glb: g.Global, expected_type: t.TypeSpec|None) -> (Expression, list[s.Statement], list[Error]):
        return self, [], []


@dataclass
class CallExpression(Expression):
    function: Expression
    parameter: Expression


    def get_type(self, glb: g.Global) -> t.TypeSpec|None:
        func_type = self.function.get_type(glb)
        return func_type.result if isinstance(func_type, t.CallableSpec) else None

    def compile(self, glb: g.Global, expected_type: t.TypeSpec|None) ->  (Expression, list[s.Statement], list[Error]):
        func_type = self.function.get_type(glb)
        prtr_type = self.parameter.get_type(glb)

        if not isinstance(prtr_type, t.TupleSpec):
            raise ValueError("parameter expression must be of TupleType")

        function , fglb, ferr = self.function.compile(glb, t.CallableSpec(self.line_ref, prtr_type, expected_type))
        parameter, pglb, perr = self.parameter.compile(glb, func_type.parameters if isinstance(func_type, t.CallableSpec) else None)

        expr = dataclasses.replace(self, function=function, parameter=parameter)
        return expr, fglb+pglb, ferr+perr

    def to_expr(self, glb: g.Global, fb: g.FunctionBuilder) -> (cg_p.RParam, cg_t.Type):
        fval, ftype = self.function.to_expr(glb, fb)
        pval, ptype = self.parameter.to_expr(glb, fb)
        if not isinstance(ptype, cg_t.Struct):
            raise ValueError("CallExpression.parameter must be of type TupleSpec")

        # For efficiency pval must be a cg_p.StackVar
        if not isinstance(pval, cg_p.StackVar):
            pvar = fb.add_var(ptype)
            fb.add_op(cg_o.Move(cg_p.StackVar(pvar), pval))
            pval = cg_p.StackVar(pvar)

        xtype = self.function.get_type(glb)
        if not isinstance(xtype, t.CallableSpec):
            raise ValueError("Callable must be of type CallableSpec")
        xtype = xtype.result.to_codegen()

        varname = fb.add_var(xtype)
        params = tuple(cg_p.StructField(pval, name) for name, etype in ptype.fields)
        fb.add_op(cg_o.Call(fval, params, varname))

        return cg_p.StackVar(varname), xtype

@dataclass
class DotExpression(Expression):
    base: Expression
    name: str

    def compile(self, glb: g.Global, expected_type: t.TypeSpec|None) ->  (DotExpression, list[s.Statement], list[Error]):
        base, bglb, berr = self.base.compile(glb, None)
        expr = dataclasses.replace(self, base=base)
        return expr, bglb, berr



def _reduce_list(glb: g.Global, expected_type: t.TypeSpec|None, list_data: list[s.FunctionStatement|s.LetStatement]) -> list[s.FunctionStatement|s.LetStatement]:
    if len(list_data) <= 1:
        return list_data
    global_data = []
    for x in list_data:
        other_type = x.get_type()
        b = t.fuzzy_assignable_equals(glb, expected_type, other_type)
        if b:
            global_data.append(x)
    return global_data


@dataclass
class NamedExpression(Expression):
    name: str

    def compile(self, glb: g.Global, expected_type: t.TypeSpec|None) -> (Expression, list[s.Statement], list[Error]):
        if '@' in self.name:
            return self, [], []

        name_set = {self.name}

        if '::' not in self.name:
            local_original = glb.find_local_data(name_set)
            local_data = _reduce_list(glb, expected_type, local_original)
            if len(local_data) > 1:
                return self, [], [Error(self.line_ref, f"too many local candidates when resolving {self.name}")]
            if len(local_data) == 1:
                return dataclasses.replace(self, name=local_data[0].name), [], []

        global_original = glb.find_global_data(name_set) + glb.find_global_func(name_set)
        global_data = _reduce_list(glb, expected_type, global_original)
        if len(global_data) > 1:
            return self, [], [Error(self.line_ref, f"too many global candidates when resolving {self.name}")]
        if len(global_data) == 1:
            return dataclasses.replace(self, name=global_data[0].name), [], []

        return self, [], [Error(self.line_ref, f"could not resolve {self.name}")]


    def get_type(self, glb: g.Global) -> t.TypeSpec|None:
        name_set = {self.name}

        glb_funcs = glb.find_global_func(name_set)
        if glb_funcs:
            # Global function
            return t.CallableSpec(self.line_ref, glb_funcs[0].parameters.get_type(), glb_funcs[0].return_type)

        glb_vars = glb.find_global_data(name_set)
        if glb_vars:
            # Global variable
            return glb_vars[0].declared_type

        lcl_vars = glb.find_local_data(name_set)
        if lcl_vars:
            # Local variable
            return lcl_vars[0].declared_type

        return None

    def to_expr(self, glb: g.Global, fb: g.FunctionBuilder) -> (cg_p.RParam, cg_t.Type):
        name_set = {self.name}

        glb_funcs = glb.find_global_func(name_set)
        if glb_funcs:
            # Global function. Don't need any more info to generate code.
            return cg_p.GlobalFunction(self.name), cg_t.FuncPointer()

        glb_vars = glb.find_global_data(name_set)
        if glb_vars:
            # Global variable
            return cg_p.GlobalVar(self.name), glb_vars[0].declared_type.to_codegen()

        lcl_vars = glb.find_local_data(name_set)
        if lcl_vars:
            # Local variable
            return cg_p.StackVar(self.name), lcl_vars[0].declared_type.to_codegen()

        raise ValueError(f"Failed to find NamedExpression '{self.name}'")


@dataclass
class StringExpression(Expression):
    value: str


@dataclass
class IntegerExpression(Expression):
    value: int
    size: int = 0

    def get_type(self, glb: g.Global) -> t.TypeSpec|None:
        return t.BuiltinSpec(self.line_ref, f"int{self.size}" if self.size else "int")

    def to_expr(self, glb: g.Global, fb: g.FunctionBuilder) -> (cg_p.RParam, cg_t.Type):
        xtype = cg_t.Int(self.size)
        xexpr = cg_p.Immediate(self.value)
        return xexpr, xtype


@dataclass
class FloatExpression(Expression):
    value: float


@dataclass
class BuiltinOpExpression(Expression):
    type: t.BuiltinSpec
    op: StringExpression
    params: list[Expression]

    def get_type(self, glb: g.Global) -> t.TypeSpec|None:
        return self.type

    def to_expr(self, glb: g.Global, fb: g.FunctionBuilder) -> (cg_p.RParam, cg_t.Type):
        values, types = zip(*[x.to_expr(glb, fb) for x in self.params])
        xtype = self.type.to_codegen()
        xexpr = cg_p.Invoke(f"__OP_{self.op.value}_{self.type.type_name}__", tuple(values))
        return xexpr, xtype

    def compile(self, glb: g.Global, expected_type: t.TypeSpec|None) ->  (Expression, list[s.Statement], list[Error]):
        p = [x.compile(glb, None) for x in self.params]
        params, new_statements, errors = zip(*p)
        expr = dataclasses.replace(self, params=list(params))
        return expr, list(new_statements), list(errors)


@dataclass
class LambdaExpression(Expression):
    parameters: t.TupleSpec
    statements: list[s.Statement]
    return_type: t.TypeSpec | None = None

    def compile(self, glb: g.Global, expected_type: t.TypeSpec|None) -> (Expression, list[s.Statement], list[Error]):
        return self, [], [Error(self.line_ref, "Lambda not supported")]

    def to_c(self, glb: g.Global, fb: g.FunctionBuilder):
        raise RuntimeError("LambdaExpression must be converted to Function before code generation")


@dataclass
class NothingExpression(Expression):
    declarations: list[s.Statement]


@dataclass
class TupleEntryExpression:
    name: str|None
    value: Expression


@dataclass
class TupleExpression(Expression):
    expressions: list[TupleEntryExpression]

    def get_type(self, glb: g.Global) -> t.TupleSpec|None:
        entries = [t.TupleEntrySpec(x.name, x.value.get_type(glb)) for x in self.expressions]
        return t.TupleSpec(self.line_ref, entries = entries)

    def to_expr(self, glb: g.Global, fb: g.FunctionBuilder) -> (cg_p.RParam, cg_t.Type):
        xtype = self.get_type(glb).to_codegen()
        value = cg_p.NewStruct(xtype, tuple(((f"_{idx}", x.value.to_expr(glb, fb)[0]) for idx, x in enumerate(self.expressions))))
        return value, xtype



