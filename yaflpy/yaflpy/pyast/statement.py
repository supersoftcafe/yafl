from __future__ import annotations


from abc import abstractmethod
from dataclasses import dataclass, field
import dataclasses

from tokenizer import LineRef
from parselib import Error


import codegen.ops as cg_o
import codegen.param as cg_p
import codegen.typedecl as cg_t
import codegen.things as cg_x

import pyast.globalcontext as g
import pyast.expression as e
import pyast.typespec as t


@dataclass
class ImportGroup:
    imports: tuple[ImportStatement, ...]


@dataclass
class Statement:
    line_ref: LineRef

    def compile(self, glb: g.Global, expected_type: t.TypeSpec|None) -> (Statement|None, list[Statement], list[Error]):
        return self, [], []

    def to_c(self, glb: g.Global, fb: g.FunctionBuilder):
        pass


@dataclass
class NamedStatement(Statement):
    name: str
    imports: ImportGroup|None

    def add_namespace(self, path: str):
        return dataclasses.replace(self, name=f"{path}{self.name}")

    @abstractmethod
    def get_type(self) -> t.TypeSpec|None:
        pass


@dataclass
class FunctionStatement(NamedStatement):
    parameters: DestructureStatement
    statements: list[Statement]
    return_type: t.TypeSpec|None = None
    is_global: bool = True

    def get_type(self) -> t.TypeSpec|None:
        return t.CallableSpec(self.line_ref, self.parameters.get_type(), self.return_type)

    def __find_locals(self, names: set[str]) -> list[LetStatement]:
        p = [x for x in self.parameters.targets if g._match_names(x.name, names)]
        l = [x for x in self.statements if isinstance(x, LetStatement) and g._match_names(x.name, names)]
        return p + l

    def compile(self, glb: g.Global, expected_type: t.TypeSpec|None) -> (FunctionStatement|None, list[Statement], list[Error]):
        if not self.is_global:
            raise ValueError(f"Function is not global {self.name}")

        rettype, rettype_glb, rettype_err = self.return_type.compile(glb) if self.return_type else (None,[],[])
        prms, prms_glb, prms_err = self.parameters.compile(glb, None)

        glb = g.LocalData(glb, self.__find_locals)
        smt_results = [x.compile(glb, self.return_type) for x in self.statements]

        new_statements = [x[0] for x in smt_results if x[0]]
        globals = [xg for x in smt_results for xg in x[1]] + rettype_glb + prms_glb
        errors  = [xe for x in smt_results for xe in x[2]] + rettype_err + prms_err

        new_self = dataclasses.replace(self, parameters = prms, statements = new_statements, return_type = rettype)
        return new_self, globals, errors

    def global_codegen(self, glb: g.Global) -> cg_x.Function:
        if not self.is_global:
            raise ValueError("Function must be global before code generation")

        glb = g.LocalData(glb, self.__find_locals)

        fb = g.FunctionBuilder()
        for statement in self.statements:
            statement.to_c(glb, fb)

        params = [("this", cg_t.DataPointer())]
        for prm in self.parameters.targets:
            xname = str(prm.name)
            xtype = prm.declared_type.to_codegen()
            params.append( (xname, xtype) )

        vars = []
        for xname, xtype in fb.stack_vars.items():
            vars.append( (xname, xtype) )

        return cg_x.Function(
            name = self.name,
            params = cg_x.Struct(fields = tuple(params)),
            result = self.return_type.to_codegen(),
            stack_vars = cg_x.Struct(fields = tuple(vars)),
            ops = tuple(fb.operations)
        )


@dataclass
class LetStatement(NamedStatement):
    default_value: e.Expression|None
    declared_type: t.TypeSpec|None

    def get_type(self) -> t.TypeSpec|None:
        return self.declared_type

    def add_namespace(self, path: str):
        return self if self.name == '_' else super(self).add_namespace(path)

    def global_codegen(self, glb: g.Global) -> cg_x.Global:
        # Probably can't do de-structuring at the global level yet either
        raise ValueError("Not implemented")

    def compile(self, glb: g.Global, expected_type: t.TypeSpec|None) -> (Statement|None, list[Statement], list[Error]):
        dv, dv_glb, dv_err = self.default_value.compile(glb, self.declared_type) if self.default_value else (None, [], [])
        dt, dt_glb, dt_err = self.declared_type.compile(glb) if self.declared_type else (None, [], [])
        stmt = dataclasses.replace(self, default_value=dv, declared_type=dt)
        return stmt, dv_glb+dt_glb, dv_err+dt_err


@dataclass
class DestructureStatement(LetStatement):
    targets: list[LetStatement]

    def get_type(self) -> t.TupleSpec:
        return t.TupleSpec(self.line_ref, [t.TupleEntrySpec(x.name, x.get_type(), None) for x in self.targets])

    def add_namespace(self, path: str):
        x: DestructureStatement = super(self).add_namespace(path)
        return dataclasses.replace(x, targets=[l.add_namespace(path) for l in self.targets])

    def compile(self, glb: g.Global, expected_type: t.TypeSpec|None) -> (DestructureStatement, list[Statement], list[Error]):
        stmt, stmt_glb, stmt_err = super().compile(glb, expected_type)
        results = [x.compile(glb, None) for x in self.targets]
        tgts = [x[0] for x in results]
        tgts_glb = [g for x in results for g in x[1]]
        tgts_err = [e for x in results for e in x[2]]
        stmt = dataclasses.replace(stmt, targets=tgts)
        return stmt, stmt_glb+tgts_glb, stmt_err+tgts_err


@dataclass
class ReturnStatement(Statement):
    value: e.Expression

    def to_c(self, glb: g.Global, fb: g.FunctionBuilder):
        var_name = self.value.to_c(glb, fb)
        fb.add_op(cg_o.Return(cg_p.StackVar(var_name)))

    def compile(self, glb: g.Global, expected_type: t.TypeSpec|None) -> (Statement|None, list[Statement], list[Error]):
        new_value, stmts, err = self.value.compile(glb, expected_type)
        new_type = new_value.get_type(glb)
        err2 = [] if t.assignable_equals(glb, expected_type, new_type) else [Error(self.line_ref, "incorrect return type")]
        return dataclasses.replace(self, value = new_value), stmts, (err + err2)


@dataclass
class ImportStatement(Statement):
    path: str


@dataclass
class NamespaceStatement(Statement):
    path: str

@dataclass
class TypeAliasStatement(NamedStatement):
    type: t.TypeSpec

