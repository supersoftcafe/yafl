from __future__ import annotations

import itertools
from typing import Callable
from dataclasses import dataclass, field
import dataclasses

from langtools import cast
from tokenizer import LineRef
from parselib import Error

import codegen.ops as cg_o
import codegen.param as cg_p
import codegen.typedecl as cg_t
import codegen.things as cg_x

import pyast.classtools as c
import pyast.resolver as g
import pyast.expression as e
import pyast.typespec as t


@dataclass
class ImportGroup:
    imports: tuple[ImportStatement, ...]


@dataclass
class Statement:
    line_ref: LineRef

    def compile(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> (Statement | None, list[Statement]):
        raise NotImplementedError()

    def check(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> list[Error]:
        raise NotImplementedError()

    def generate(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> g.OperationBundle:
        return g.OperationBundle()

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,any],any]) -> Statement:
        return cast(Statement, replace(resolver, self))


@dataclass
class NamedStatement(Statement):
    name: str
    imports: ImportGroup|None
    attributes: dict[str, e.Expression]

    def add_namespace(self, path: str):
        return dataclasses.replace(self, name=f"{path}{self.name}")


@dataclass
class TypeStatement(NamedStatement):
    def get_type(self) -> t.TypeSpec|None:
        raise NotImplementedError()


@dataclass
class DataStatement(NamedStatement):
    def get_type(self) -> t.TypeSpec|None:
        raise NotImplementedError()


@dataclass
class FunctionStatement(DataStatement):
    parameters: DestructureStatement
    statements: list[Statement]
    return_type: t.TypeSpec|None = None

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,any],any]) -> Statement:
        nested_resolver = g.ResolverData(resolver, self.__find_locals)
        return cast(Statement, replace(nested_resolver, dataclasses.replace(self,
            parameters=cast(DestructureStatement, self.parameters.search_and_replace(resolver, replace)),
            statements=[x.search_and_replace(nested_resolver, replace) for x in self.statements])))

    def get_type(self) -> t.TypeSpec|None:
        return t.CallableSpec(self.line_ref, self.parameters.get_type(), self.return_type)

    def __find_locals(self, names: set[str]) -> list[g.Resolved[DataStatement]]:
        p = [g.Resolved(let.name, let, g.ResolvedScope.LOCAL)
             for let in self.parameters.flatten()
             if g.match_names(let.name, names)]
        l = [g.Resolved(let.name, let, g.ResolvedScope.LOCAL)
             for x in self.statements if isinstance(x, LetStatement) for let in x.flatten()
             if g.match_names(x.name, names)]
        # s = [g.Resolved(self.local_this.name, self.local_this, g.ResolvedScope.LOCAL)] if self.local_this and self.local_this.name in names else []
        return p + l # + s

    def compile(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> (FunctionStatement | None, list[Statement]):
        rettype, rettype_glb = self.return_type.compile(resolver) if self.return_type else (None, [])
        prms, prms_glb = self.parameters.compile(resolver, None)

        resolver = g.ResolverData(resolver, self.__find_locals)
        smt_results = [x.compile(resolver, self.return_type) for x in self.statements]

        new_statements = [x[0] for x in smt_results if x[0]]
        globals = [xg for x in smt_results for xg in x[1]] + rettype_glb + prms_glb

        new_self = dataclasses.replace(self, parameters = prms, statements = new_statements, return_type = rettype)
        return new_self, globals

    def check(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> list[Error]:
        resolver = g.ResolverData(resolver, self.__find_locals)
        err1 = self.return_type.check(resolver) if self.return_type else []
        err2 = self.parameters.check(resolver, None)
        err3 = [e for x in self.statements for e in x.check(resolver, self.return_type)]
        return err1 + err2 + err3

    def global_codegen(self, resolver: g.Resolver) -> cg_x.Function:
        resolver = g.ResolverData(resolver, self.__find_locals)

        bundle = g.OperationBundle()
        for index, parameter in enumerate(self.parameters.targets):
            bundle = bundle + parameter.to_c_destructure(None).rename_vars(f"p{index}_")
        for index, statement in enumerate(self.statements):
            bundle = bundle + statement.generate(resolver, None).rename_vars(f"s{index}_")

        params: list[tuple[str, cg_t.Type]] = [("this", cg_t.DataPointer())]
        for prm in self.parameters.targets:
            xname = str(prm.name)
            xtype = prm.declared_type.generate()
            params.append( (xname, xtype) )

        vars = []
        for sv in bundle.stack_vars:
            vars.append( (sv.name, sv.type) )

        return cg_x.Function(
            name = self.name,
            params = cg_t.Struct(fields = tuple(params)),
            result = self.return_type.generate(),
            stack_vars = cg_t.Struct(fields = tuple(vars)),
            ops = tuple(bundle.operations),
            comment = self.name
        )


@dataclass
class ClassFunctionSlot:
    name: str
    type: t.CallableSpec | None
    provides: set[str]

    def __post_init__(self):
        if not isinstance(self.provides, set):
            raise Error()


@dataclass
class ClassStatement(TypeStatement):
    parameters: DestructureStatement
    statements: list[DataStatement]
    implements: list[t.TypeSpec]
    is_interface: bool = False
    _all_parents: set[t.TypeSpec] | None = None # Compiler needs to find all inherited classes
    _all_slots: list[ClassFunctionSlot] | None = None


    def __post_init__(self):
        if not isinstance(self.statements, list):
            raise ValueError()


    def __find_locals(self, resolver: g.Resolver, names: set[str]) -> list[g.Resolved[DataStatement]]:
        m = self.find_data(resolver, names)
        l = LetStatement(self.line_ref, "this", None, {}, None, t.ClassSpec(self.line_ref, self.name))
        s = [g.Resolved("this", l, g.ResolvedScope.LOCAL)] if "this" in names else []
        return m + s


    def find_data(self, resolver: g.Resolver, names: set[str]) -> list[g.Resolved[DataStatement]]:
        s1 = self.parameters.flatten()
        s2 = self.statements
        statements = s1 + s2
        # a) try to find in this class. Anything we find masks out parent matches, so no need to recurse.
        # b) if 'a' fails, search all parents and accumulate all the results.
        matches = [g.Resolved(x.name, x, g.ResolvedScope.MEMBER) for x in statements if g.match_names(x.name, names)] \
               or [match for xtype, parent in c.find_classes_or_error(self.implements, resolver)
                         if isinstance(parent, ClassStatement)
                         for match in parent.find_data(resolver, names)]
        return matches


    def get_fields(self, resolver: g.Resolver) -> list[LetStatement]:
        s1 = self.parameters.flatten()
        s2 = [s for s in self.statements if isinstance(s, LetStatement)]
        return s1 + s2


    @property
    def is_abstract(self) -> bool:
        return any(1 for x in self._all_slots or [] if not x.provides)


    def get_type(self) -> t.ClassSpec|None:
        return t.ClassSpec(self.line_ref, self.name)


    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,any],any]) -> Statement:
        nested_resolver = g.ResolverData(resolver, lambda names: self.__find_locals(resolver, names))
        return cast(Statement, replace(nested_resolver, dataclasses.replace(self,
            parameters=cast(DestructureStatement, self.parameters.search_and_replace(resolver, replace)),
            statements=[x.search_and_replace(nested_resolver, replace) for x in self.statements])))


    def compile(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> (Statement | None, list[Statement]):
        # Resolve each of the inherited types and update the implements list
        unpacked_implements = [y for x in self.implements for y in (x.types if isinstance(x, t.CombinationSpec) else [x])]
        resolved_inheritance = c.find_classes_or_error(unpacked_implements, resolver)
        classes = [xcls for (xtype, xcls) in resolved_inheritance if isinstance(xcls, ClassStatement)]
        new_implements = [xtype for (xtype, xcls) in resolved_inheritance]

        # Build slots list of all functions
        base_slots = c.create_slots_from_members(self)
        parent_slots = [y for x in classes for y in (x._all_slots or [])]
        new_all_slots = c.override_inherited_slots(resolver, base_slots, parent_slots)

        # Try to find all parent class type specs
        new_all_parents = {y for x in classes for y in (x._all_parents or [])} | {x.get_type() for x in classes}

        # Recurse to compile parameters and statements
        new_parameters, prm_glb = self.parameters.compile(resolver, None)
        statement_resolver = g.ResolverData(resolver, lambda names: self.__find_locals(resolver, names))
        tmp_result = [x.compile(statement_resolver, None) for x in self.statements]
        new_statements, stm_glb = zip(*tmp_result) if tmp_result else ([], [])

        result = dataclasses.replace(self,
              implements=new_implements,
              parameters=new_parameters,
              statements=list(new_statements),
              _all_slots=new_all_slots,
            _all_parents=new_all_parents)

        return result, prm_glb + [x for stm in stm_glb for x in stm]


    def check(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> list[Error]:
        if self._all_parents is None:
            return [Error(self.line_ref, "Missed compile step")]

        # Report any errors resolving any in the implements list
        resolved_inheritance = c.find_classes_or_error(self.implements, resolver)
        impl_err = [xerr for (xtype, xerr) in resolved_inheritance if isinstance(xerr, Error)]

        cls_type_err = [] if all(x[1].is_interface for x in resolved_inheritance if isinstance(x[1], ClassStatement)) else\
            [Error(self.line_ref, "Must only inherit from pure interfaces")]

        # Slots that have more than one implementor
        slots = c.invert_and_merge_slots(self._all_slots)
        bad_slots_err = [Error(self.line_ref, "One or more slots have multiple overrides")]\
            if any(1 for n,s in slots.items() if len(s)>1) else []
        empty_slots_err = [Error(self.line_ref, "One or more slots have no implementation")]\
            if any(1 for n,s in slots.items() if not s) else []

        # Recurse to check parameters and statements
        prm_err = self.parameters.check(resolver, None)
        resolver = g.ResolverData(resolver, lambda names: self.__find_locals(resolver, names))
        stm_err = [x for stm in self.statements for x in stm.check(resolver, None)]

        return prm_err + stm_err + impl_err + cls_type_err + bad_slots_err + empty_slots_err


    def global_codegen(self, resolver: g.Resolver) -> (cg_x.Object, list[cg_x.Function]):
        resolver = g.ResolverData(resolver, lambda names: self.__find_locals(resolver, names))
        ast_functions = [fnc for fnc in self.statements if isinstance(fnc, FunctionStatement)]
        gen_functions = [fnc.global_codegen(resolver) for fnc in ast_functions]

        extends = () if self.is_interface else tuple(x.as_unique_id_str() for x in self._all_parents)
        functions = () if self.is_interface else tuple((y, x.name) for x in self._all_slots for y in x.provides)

        function_names = {f for s,f in functions}
        thunks = [c.create_thunk(self.name ,x) for x in self.parameters.flatten() if x.name in function_names]

        xobject = cg_x.Object(
            name=self.name,
            extends=extends,
            functions=functions,
            fields=cg_t.ImmediateStruct(
                (("type", cg_t.DataPointer()),) +
                tuple((p.name, p.get_type().generate()) for p in self.parameters.flatten())
            ),
            length_field=None,
            comment=self.name
        ) # TODO: Array support

        return xobject, gen_functions+thunks


@dataclass
class LetStatement(DataStatement):
    default_value: e.Expression|None
    declared_type: t.TypeSpec|None

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,any],any]) -> Statement:
        return cast(Statement, replace(resolver, dataclasses.replace(self,
            default_value=self.default_value and self.default_value.search_and_replace(resolver, replace))))

    def get_type(self) -> t.TypeSpec|None:
        return self.declared_type

    def add_namespace(self, path: str):
        return self if self.name == '_' else super().add_namespace(path)

    def to_c_destructure(self, root: cg_p.RParam | None) -> g.OperationBundle:
        if root:
            # Leaf node, move the value into a stack var
            var = cg_p.StackVar(self.get_type().generate(), self.name)
            return g.OperationBundle(
                stack_vars=(var,),
                operations=(cg_o.Move(var, root),),
                result_var=None)
        else:
            # Just a value, no work, caller does it
            return g.OperationBundle()

    def compile(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> (Statement | None, list[Statement]):
        dv, dv_glb = self.default_value.compile(resolver, self.declared_type) if self.default_value else (None, [])
        dt, dt_glb = self.declared_type.compile(resolver) if self.declared_type else (None, [])
        stmt = dataclasses.replace(self, default_value=dv, declared_type=dt)
        return stmt, dv_glb+dt_glb

    def check(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> list[Error]:
        err1 = self.default_value.check(resolver, self.declared_type) if self.default_value else []
        err2 = self.declared_type.check(resolver) if self.declared_type else []
        return err1 + err2

    def generate(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> g.OperationBundle:
        expr_bundle = self.default_value.generate(resolver).rename_vars(1)
        sv = cg_p.StackVar(self.declared_type.generate(), self.name)
        init_bundle = g.OperationBundle(
            stack_vars=(sv,),
            operations=(cg_o.Move(sv, expr_bundle.result_var),),
            result_var=None
        )
        unpack_bundle = self.to_c_destructure(None)
        return (expr_bundle + init_bundle).rename_vars(1) + unpack_bundle.rename_vars(2)

    def global_codegen(self, resolver: g.Resolver) -> tuple[list[cg_x.Global], list[cg_x.Function]]:
        init_funcs: list[cg_x.Function] = []
        global_vars: list[cg_x.Global] = []

        init_func_name: str|None = None
        init_flag_name: str|None = None
        rparam: cg_p.RParam|None = None
        xtype = self.get_type().generate()
        if self.default_value:
            init = self.default_value.generate(resolver)
            if not init.operations and not init.stack_vars and init.result_var:
                rparam = init.result_var
            else:
                init_func_name = f"{self.name}$lazy$init"
                init_flag_name = f"{self.name}$lazy$flag"
                set_value = cg_o.Move(cg_p.GlobalVar(xtype, self.name), init.result_var)
                return_zero = cg_o.Return(cg_p.Integer(0, 32))
                init_funcs.append(cg_x.Function(
                    init_func_name,
                    cg_t.Struct( (("this", cg_t.DataPointer()),) ),
                    cg_t.Int(32),
                    cg_t.Struct(tuple((sv.name, sv.type) for sv in init.stack_vars)),
                    init.operations + (set_value,return_zero)  ))
                global_vars.append(cg_x.Global(
                    init_flag_name,
                    cg_t.DataPointer()  ))
        global_vars.append(cg_x.Global(
            self.name,
            xtype,
            rparam,
            lazy_init_function=init_func_name,
            lazy_init_flag=init_flag_name  ))
        return global_vars, init_funcs

    def flatten_to(self, path_to_thing, path):
        return [path_to_thing(path + [self])]

    def flatten(self) -> list[LetStatement]:
        return self.flatten_to(lambda path: path[-1], [])


@dataclass
class DestructureStatement(LetStatement):
    targets: list[LetStatement]

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,any],any]) -> Statement:
        return cast(Statement, replace(resolver,dataclasses.replace(self,
            default_value=self.default_value and self.default_value.search_and_replace(resolver, replace),
            targets=[cast(LetStatement, x.search_and_replace(resolver, replace)) for x in self.targets])))

    def get_type(self) -> t.TupleSpec:
        return t.TupleSpec(self.line_ref, [t.TupleEntrySpec(x.name, x.get_type(), None) for x in self.targets])

    def to_c_destructure(self, root: cg_p.RParam | None) -> g.OperationBundle:
        if not root:
            # The first attempt should declare the root var
            root = cg_p.StackVar(self.get_type().generate(), self.name)
        result = g.OperationBundle()
        for index, target in enumerate(self.targets):
            destr = target.to_c_destructure(cg_p.StructField(root, f"_{index}"))
            result = result.rename_vars(1) + destr.rename_vars(2)
        return result

    def add_namespace(self, path: str):
        x: DestructureStatement = cast(DestructureStatement, super(self).add_namespace(path))
        return dataclasses.replace(x, targets=[l.add_namespace(path) for l in self.targets])

    def compile(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> (DestructureStatement, list[Statement]):
        stmt, stmt_glb = super().compile(resolver, func_ret_type)
        results = [x.compile(resolver, None) for x in stmt.targets]
        tgts = [x[0] for x in results]
        tgts_glb = [g for x in results for g in x[1]]
        stmt = dataclasses.replace(stmt, targets=tgts)
        return stmt, stmt_glb+tgts_glb

    # def check(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> list[Error]:
    #     return super(self).check(resolver, func_ret_type)
    #

    def generate(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> g.OperationBundle:
        raise NotImplementedError()

    def flatten_to(self, path_to_thing, path):
        return [path_to_thing(path + [entry]) for target in self.targets for entry in target.flatten()]


@dataclass
class ReturnStatement(Statement):
    value: e.Expression

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,any],any]) -> Statement:
        return cast(Statement, replace(resolver, dataclasses.replace(self,
            value=self.value.search_and_replace(resolver, replace))))

    def compile(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> (Statement | None, list[Statement], list[Error]):
        new_value, stmts = self.value.compile(resolver, func_ret_type)
        return dataclasses.replace(self, value = new_value),[]

    def check(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> list[Error]:
        xtype = self.value.get_type(resolver)
        if xtype and not t.trivially_assignable_equals(resolver, func_ret_type, xtype):
            return [Error(self.line_ref, "Incorrect return type")]
        return self.value.check(resolver, func_ret_type)

    def generate(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> g.OperationBundle:
        xtype = self.value.get_type(resolver)
        op_bundle = self.value.generate(resolver)
        ret_bundle = g.OperationBundle( (), ( cg_o.Return(op_bundle.result_var), ) )
        return op_bundle + ret_bundle


@dataclass
class ImportStatement(Statement):
    path: str

    def compile(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> (Statement | None, list[Statement]):
        return self, []

    def check(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> list[Error]:
        return []


@dataclass
class NamespaceStatement(Statement):
    path: str

    def compile(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> (Statement | None, list[Statement]):
        return self, []

    def check(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> list[Error]:
        return []


@dataclass
class TypeAliasStatement(TypeStatement):
    type: t.TypeSpec

    def get_type(self) -> t.TypeSpec|None:
        return self.type if self.type.is_concrete() else None

    def compile(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> (Statement | None, list[Statement]):
        new_type, new_statements = self.type.compile(resolver)
        return dataclasses.replace(self, type=new_type), new_statements

    def check(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> list[Error]:
        return self.type.check(resolver)

@dataclass
class ActionStatement(Statement):
    action: e.Expression

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,any],any]) -> Statement:
        return cast(Statement, replace(resolver, dataclasses.replace(self,
            action=self.action.search_and_replace(resolver, replace))))

    def compile(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> (Statement | None, list[Statement]):
        new_action, stmts = self.action.compile(resolver, func_ret_type)
        return dataclasses.replace(self, action = new_action), stmts

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        return self.action.check(resolver, None)

    def generate(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> g.OperationBundle:
        return self.action.generate(resolver)

