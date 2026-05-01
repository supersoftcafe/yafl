from __future__ import annotations

import itertools
from collections.abc import Sequence
from typing import Callable, Iterable, Any
from dataclasses import dataclass, field
import dataclasses

from langtools import cast
from parsing.tokenizer import LineRef
from parsing.parselib import Error

import codegen.ops as cg_o
import codegen.param as cg_p
import codegen.typedecl as cg_t
import codegen.things as cg_x

import pyast.classtools as c
import pyast.resolver as g
import pyast.expression as e
import pyast.typespec as t

import pyast.utils as u


@dataclass
class ImportGroup:
    imports: tuple[ImportStatement, ...]


@dataclass
class Statement:
    line_ref: LineRef

    def compile(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> tuple[Statement | None, list[Statement]]:
        raise NotImplementedError()

    def check(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> list[Error]:
        raise NotImplementedError()

    def generate(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> g.OperationBundle:
        return g.OperationBundle()

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,Any],Any]) -> Statement:
        return cast(Statement, replace(resolver, self))


@dataclass
class NamedStatement(Statement):
    name: str
    imports: ImportGroup|None
    attributes: dict[str, e.Expression|None]
    type_params: tuple[TypeAliasStatement, ...]     # SomeClass<TValue1, TValue1>
    trait_params: tuple[t.TypeSpec, ...] = field(default=(), kw_only=True)   # SomeClass<TValue>() where Numeric<TValue>

    def _find_trait_data(self, resolver: g.Resolver, names: set[str]) -> list[g.Resolved[DataStatement]]:
        def find_in_class(tp: t.ClassSpec) -> list[g.Resolved[DataStatement]]:
            found = [rs.statement for rs in resolver.find_type({tp.name})]
            match found:
                case [ClassStatement() as cls]:
                    if len(tp.type_params) != len(cls.type_params):
                        return []
                    # Search direct members first
                    direct = [x for x in cls.parameters.flatten() + cls.statements
                              if g.match_names(x.name, names)]
                    if direct:
                        return [g.Resolved(x.name, x, g.ResolvedScope.TRAIT, tp, cls) for x in direct]
                    # Not found directly — recurse into parent interfaces with type params substituted.
                    # E.g. if cls is Math<TVal> : Plus<TVal> and tp is Math<Int>,
                    # substitute TVal→Int to get Plus<Int>, preserving the correct trait_scope.
                    mapping = {p.name: c for p, c in zip(cls.type_params, tp.type_params)}
                    def replace_fn(_, thing, m=mapping):
                        if isinstance(thing, t.GenericPlaceholderSpec) and thing.name in m:
                            return m[thing.name]
                        return thing
                    result = []
                    for parent_type in cls.implements:
                        substituted = parent_type.search_and_replace(resolver, replace_fn)
                        if isinstance(substituted, t.ClassSpec) and substituted.is_concrete():
                            result.extend(find_in_class(substituted))
                    return result
                case _:
                    raise LookupError(f"Failed to find class {tp.name!r}: got {[type(f).__name__ for f in found]}")
        specs: set[t.ClassSpec] = set()
        ordered_specs: list[t.ClassSpec] = []
        for tp in self.trait_params:
            if isinstance(tp, t.ClassSpec) and tp.is_concrete() and tp not in specs:
                specs.add(tp)
                ordered_specs.append(tp)
        for iface in resolver.get_implicit_where_specs():
            if isinstance(iface, t.ClassSpec) and iface.is_concrete() and iface not in specs:
                specs.add(iface)
                ordered_specs.append(iface)
        return [x for tp in ordered_specs for x in find_in_class(tp)]

    def _find_generic_types(self, names: set[str]) -> list[g.Resolved[TypeStatement]]:
        return [g.Resolved(tp.name, tp, g.ResolvedScope.LOCAL) for tp in self.type_params if g.match_names(tp.name, names)]

    def add_namespace(self, path: str):
        return dataclasses.replace(self, name=f"{path}{self.name}")

    def check_caller_type_params(self, resolver: g.Resolver, caller_type_params: Sequence[t.TypeSpec], line_ref: LineRef) -> list[Error]:
        if len(caller_type_params) > len(self.type_params):
            return [Error(line_ref, "Excess type parameters")]
        if len(caller_type_params) < len(self.type_params):
            return [Error(line_ref, "Not enough type parameters")]

        # replace type_params with real types in a temporary type ref
        type_params = [dataclasses.replace(tp, type=ct) for ct, tp in zip(caller_type_params, self.type_params)]
        resolver = g.ResolverType(resolver, lambda names:
            [g.Resolved(tp.name, tp, g.ResolvedScope.LOCAL) for tp in type_params if g.match_names(tp.name, names)])

        # for each trait_param
        #   temporary compile, to resolve real type parameters
        #   find one trait that is assignment compatible
        trait_providers = resolver.get_traits()
        for trait_param in self.trait_params:
            compiled, extra = trait_param.compile(resolver)
            if extra: # Skip if compilation is still producing new statements
                return [Error(line_ref, f"Compile steps incomplete for '{trait_param.name}'. Seeing this message indicates a compiler error.")]
            tp_found = [tp for tp in trait_providers if t.trivially_assignable_equals(resolver, compiled, tp.declared_type)]
            if len(tp_found) == 0:
                return [Error(line_ref, f"Trait parameter '{trait_param.name}' does not match any trait")]

        return []

@dataclass
class TypeStatement(NamedStatement):
    def get_type(self) -> t.TypeSpec|None:
        raise NotImplementedError()


@dataclass
class DataStatement(NamedStatement):
    def compile(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> tuple[DataStatement, list[Statement]]:
        raise NotImplementedError()

    def get_type(self) -> t.TypeSpec|None:
        raise NotImplementedError()


@dataclass
class FunctionStatement(DataStatement):
    parameters: DestructureStatement
    body: e.Expression | None
    return_type: t.TypeSpec|None = None

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,Any],Any]) -> Statement:
        nested_resolver = g.ResolverData(resolver, self.__find_locals(resolver))
        return cast(Statement, replace(nested_resolver, dataclasses.replace(self,
            parameters=cast(DestructureStatement, self.parameters.search_and_replace(resolver, replace)),
            body=self.body.search_and_replace(nested_resolver, replace) if self.body is not None else None,
            return_type=self.return_type.search_and_replace(resolver, replace) if self.return_type else None,
            trait_params=tuple(tp.search_and_replace(resolver, replace) for tp in self.trait_params))))

    def get_type(self) -> t.TypeSpec|None:
        return t.CallableSpec(self.line_ref, self.parameters.get_type(), self.return_type)

    def __find_locals(self, resolver: g.Resolver) -> Callable[[set[str]],list[g.Resolved[DataStatement]]]:
        def finder(names: set[str]) -> list[g.Resolved[DataStatement]]:
            p = [g.Resolved(let.name, let, g.ResolvedScope.LOCAL)
                 for let in self.parameters.flatten()
                 if g.match_names(let.name, names)]
            td = self._find_trait_data(resolver, names)
            return p + td
        return finder

    def compile(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> tuple[FunctionStatement | None, list[Statement]]:
        resolver = g.ResolverType(resolver, self._find_generic_types)
        rettype, rettype_glb = self.return_type.compile(resolver) if self.return_type else (None, [])
        prms, prms_glb = self.parameters.compile(resolver, None)
        trts, trts_glb = u.flatten_lists(tp.compile(resolver) for tp in self.trait_params)

        body_resolver = g.ResolverData(resolver, self.__find_locals(resolver))
        if self.body is not None:
            new_body, body_glb = self.body.compile(body_resolver, self.return_type)
            if rettype is None:
                rettype = new_body.get_type(body_resolver)
        else:
            new_body, body_glb = None, []

        globals = body_glb + rettype_glb + prms_glb + trts_glb
        new_self = dataclasses.replace(self, trait_params=tuple(trts), parameters=prms, body=new_body, return_type=rettype)
        return new_self, globals

    def check(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> list[Error]:
        resolver = g.ResolverType(resolver, self._find_generic_types)
        body_resolver = g.ResolverData(resolver, self.__find_locals(resolver))
        err1 = self.return_type.check(resolver) if self.return_type else []
        err2 = self.parameters.check(resolver, None)
        err3 = self.body.check(body_resolver, self.return_type) if self.body is not None else []
        err4 = [e for x in self.trait_params for e in x.check(resolver)]

        if "foreign" in self.attributes:
            foreign_attr = self.attributes.get("foreign")
            if (not isinstance(foreign_attr, e.TupleExpression)
                    or len(foreign_attr.expressions) != 1
                    or not isinstance(foreign_attr.expressions[0].value, e.StringExpression)):
                foreign_err = [Error(self.line_ref, '[foreign] requires exactly one string argument: [foreign("symbol")]')]
            elif self.body is not None:
                foreign_err = [Error(self.line_ref, "[foreign] functions must have no body")]
            else:
                foreign_err = []
        else:
            foreign_err = []

        if "impure" in self.attributes:
            impure_err = [] if self.attributes.get("impure") is None else [Error(self.line_ref, "[impure] takes no arguments")]
        else:
            impure_err = []

        if "sync" in self.attributes:
            sync_err = [] if self.attributes.get("sync") is None else [Error(self.line_ref, "[sync] takes no arguments")]
        else:
            sync_err = []

        return err1 + err2 + err3 + err4 + foreign_err + impure_err + sync_err

    def global_codegen(self, resolver: g.Resolver) -> cg_x.Function:
        resolver = g.ResolverType(resolver, self._find_generic_types)
        resolver = g.ResolverData(resolver, self.__find_locals(resolver))

        bundle = g.OperationBundle()
        for index, parameter in enumerate(self.parameters.targets):
            bundle = bundle + parameter.to_c_destructure(None).rename_vars(f"p{index}_")
        if self.body is not None:
            body_bundle = self.body.generate(resolver)
            ret_bundle = g.OperationBundle((), (cg_o.Return(body_bundle.result_var),))
            bundle = bundle + (body_bundle + ret_bundle).rename_vars("body_")

        params: list[tuple[str, cg_t.Type]] = [("this", cg_t.DataPointer())]
        for prm in self.parameters.targets:
            xname = str(prm.name)
            xtype = prm.declared_type.generate()
            params.append( (xname, xtype) )

        vars = []
        for sv in bundle.stack_vars:
            vars.append( (sv.name, sv.type) )

        foreign_attr = self.attributes.get("foreign")
        foreign_symbol = (foreign_attr.expressions[0].value.value
                          if isinstance(foreign_attr, e.TupleExpression)
                          and len(foreign_attr.expressions) == 1
                          and isinstance(foreign_attr.expressions[0].value, e.StringExpression)
                          else None)

        return cg_x.Function(
            name = self.name,
            params = cg_t.Struct(fields = tuple(params)),
            result = self.return_type.generate(),
            stack_vars = cg_t.Struct(fields = tuple(vars)),
            ops = tuple(bundle.operations),
            comment = self.name,
            foreign_symbol = foreign_symbol,
            sync = "sync" in self.attributes
        )


@dataclass
class ClassFunctionSlot:
    name: str
    type: t.CallableSpec | None
    provides: set[str]

    def __post_init__(self):
        if not isinstance(self.provides, set):
            raise ValueError()


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


    def __find_locals(self, resolver: g.Resolver) -> Callable[[set[str]],list[g.Resolved[DataStatement]]]:
        def finder(names: set[str]) -> list[g.Resolved[DataStatement]]:
            m = self.find_data(resolver, names)
            l = LetStatement(self.line_ref, "this", None, {}, (), None, t.ClassSpec(self.line_ref, self.name))
            s = [g.Resolved("this", l, g.ResolvedScope.LOCAL)] if "this" in names else []
            td = self._find_trait_data(resolver, names)
            return m + s + td
        return finder

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


    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,Any],Any]) -> Statement:
        nested_resolver = g.ResolverType(g.ResolverData(resolver, self.__find_locals(resolver)), self._find_generic_types)
        return cast(Statement, replace(nested_resolver, dataclasses.replace(self,
            parameters=cast(DestructureStatement, self.parameters.search_and_replace(resolver, replace)),
            statements=[x.search_and_replace(nested_resolver, replace) for x in self.statements],
            implements=[tp.search_and_replace(resolver, replace) for tp in self.implements],
            trait_params=tuple(tp.search_and_replace(resolver, replace) for tp in self.trait_params),
            _all_parents=({p.search_and_replace(resolver, replace) for p in self._all_parents}
                          if self._all_parents is not None else None))))


    def compile(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> tuple[Statement | None, list[Statement]]:
        # Resolve each of the inherited types and update the implements list
        # Use a resolver that includes this class's own generic type params so that
        # e.g. `TVal` in `class Foo<TVal> : Bar<TVal>` resolves to GenericPlaceholderSpec.
        type_resolver = g.ResolverType(resolver, self._find_generic_types)
        unpacked_implements = [y for x in self.implements for y in (x.types if isinstance(x, t.CombinationSpec) else [x])]
        resolved_inheritance = c.find_classes_or_error(unpacked_implements, type_resolver)
        resolved_classes = [(xtype, xcls) for (xtype, xcls) in resolved_inheritance if isinstance(xcls, ClassStatement)]
        classes = [xcls for (xtype, xcls) in resolved_classes]
        new_implements = [xtype for (xtype, xcls) in resolved_inheritance]

        # Build slots list of all functions
        base_slots = c.create_slots_from_members(self)
        parent_slots = [y for x in classes for y in (x._all_slots or [])]
        new_all_slots = c.override_inherited_slots(resolver, base_slots, parent_slots)

        # Build transitive parent set, substituting type params so that e.g.
        # `class Foo : Bar<Int>` where `Bar<TVal> : Baz<TVal>` gets `Baz<Int>` (not `Baz<TVal>`)
        # in its transitive parents, enabling monomorphization and trait lookup to work correctly.
        new_all_parents: set[t.TypeSpec] = set()
        for xtype, xcls in resolved_classes:
            new_all_parents.add(xtype)
            if xcls._all_parents:
                if isinstance(xtype, t.ClassSpec) and xcls.type_params and xtype.type_params:
                    mapping = {p.name: concrete for p, concrete in zip(xcls.type_params, xtype.type_params)}
                    def replace_fn(_, thing, m=mapping):
                        if isinstance(thing, t.GenericPlaceholderSpec) and thing.name in m:
                            return m[thing.name]
                        return thing
                    for parent in xcls._all_parents:
                        new_all_parents.add(parent.search_and_replace(resolver, replace_fn))
                else:
                    new_all_parents.update(xcls._all_parents)

        # Recurse to compile parameters and statements
        new_parameters, prm_glb = self.parameters.compile(resolver, None)
        statement_resolver = g.ResolverType(g.ResolverData(resolver, self.__find_locals(resolver)), self._find_generic_types)
        new_statements, stm_glb = u.flatten_lists(x.compile(statement_resolver, None) for x in self.statements)

        trts, trts_glb = u.flatten_lists(x.compile(resolver) for x in self.trait_params)

        result = dataclasses.replace(self,
              implements=new_implements,
              parameters=new_parameters,
              statements=new_statements,
              trait_params=tuple(trts),
              _all_slots=new_all_slots,
            _all_parents=new_all_parents)

        return result, prm_glb + trts_glb + stm_glb


    def check(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> list[Error]:
        if self._all_parents is None:
            return [Error(self.line_ref, "Missed compile step")]

        # Report any errors resolving any in the implements list
        resolved_inheritance = c.find_classes_or_error(self.implements, resolver)
        impl_err = [xerr for (xtype, xerr) in resolved_inheritance if isinstance(xerr, Error)]

        cls_type_err = [] if all(x[1].is_interface for x in resolved_inheritance if isinstance(x[1], ClassStatement)) else\
            [Error(self.line_ref, "Must only inherit from pure interfaces")]

        final_err = [Error(self.line_ref, f"Cannot inherit from final class '{xcls.name}'")
                     for (xtype, xcls) in resolved_inheritance
                     if isinstance(xcls, ClassStatement) and "final" in xcls.attributes]

        # Slots that have more than one implementor
        slots = c.invert_and_merge_slots(self._all_slots)
        bad_slots_err = [Error(self.line_ref, "One or more slots have multiple overrides")]\
            if any(1 for n,s in slots.items() if len(s)>1) else []
        empty_slots_err = [Error(self.line_ref, "One or more slots have no implementation")]\
            if any(1 for n,s in slots.items() if not s) else []

        # Recurse to check parameters and statements
        prm_err = self.parameters.check(resolver, None)
        resolver = g.ResolverType(g.ResolverData(resolver, self.__find_locals(resolver)), self._find_generic_types)
        stm_err = [x for stm in self.statements for x in stm.check(resolver, None)]

        if "foreign" in self.attributes:
            foreign_attr = self.attributes.get("foreign")
            if foreign_attr is not None:
                class_foreign_err = [Error(self.line_ref, "[foreign] on a class takes no argument — instances are returned by foreign functions")]
            elif "final" not in self.attributes:
                class_foreign_err = [Error(self.line_ref, "[foreign] classes must also be [final]")]
            elif self.parameters.flatten():
                class_foreign_err = [Error(self.line_ref, "[foreign] classes must have no parameters — instances are returned by foreign functions, not constructed directly")]
            elif any(not (isinstance(s, FunctionStatement) and "foreign" in s.attributes)
                     for s in self.statements):
                class_foreign_err = [Error(self.line_ref, "[foreign] classes may only contain [foreign] methods")]
            else:
                class_foreign_err = []
        else:
            class_foreign_err = []

        return prm_err + stm_err + impl_err + cls_type_err + final_err + class_foreign_err + bad_slots_err + empty_slots_err


    def global_codegen(self, resolver: g.Resolver) -> tuple[cg_x.Object, list[cg_x.Function]]:
        resolver = g.ResolverType(g.ResolverData(resolver, self.__find_locals(resolver)), self._find_generic_types)
        ast_functions = [fnc for fnc in self.statements if isinstance(fnc, FunctionStatement)]
        gen_functions = [fnc.global_codegen(resolver) for fnc in ast_functions]

        extends = () if self.is_interface else tuple(sorted(x.as_unique_id_str() for x in self._all_parents if x.as_unique_id_str()))
        functions = () if self.is_interface else tuple((y, x.name) for x in self._all_slots for y in sorted(x.provides))

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
            comment=self.name,
            is_foreign="foreign" in self.attributes
        ) # TODO: Array support

        return xobject, gen_functions+thunks


@dataclass
class LetStatement(DataStatement):
    default_value: e.Expression|None
    declared_type: t.TypeSpec|None

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,Any],Any]) -> Statement:
        return cast(Statement, replace(resolver, dataclasses.replace(self,
            default_value=self.default_value and self.default_value.search_and_replace(resolver, replace),
            declared_type=self.declared_type.search_and_replace(resolver, replace) if self.declared_type else None)))

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

    def compile(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> tuple[LetStatement | None, list[Statement]]:
        def has_named_spec(spec: t.TypeSpec) -> bool:
            if isinstance(spec, t.NamedSpec):
                return True
            if isinstance(spec, t.CombinationSpec):
                return any(has_named_spec(s) for s in spec.types)
            return False

        dv, dv_glb = self.default_value.compile(resolver, self.declared_type) if self.default_value else (None, [])
        dt, dt_glb = self.declared_type.compile(resolver) if self.declared_type else (None, [])
        if (dt is None or isinstance(dt, t.NamedSpec)) and dv is not None:
            inferred = dv.get_type(resolver)
            if inferred is not None and not has_named_spec(inferred):
                dt = inferred
        stmt = dataclasses.replace(self, default_value=dv, declared_type=dt)
        return stmt, dv_glb+dt_glb

    def check(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> list[Error]:
        if self.default_value and self.declared_type:
            xtype = self.default_value.get_type(resolver)
            if xtype and not t.trivially_assignable_equals(resolver, self.declared_type, xtype):
                return [Error(self.line_ref, "Incorrect type")]
        err1 = self.default_value.check(resolver, self.declared_type) if self.default_value else []
        err2 = self.declared_type.check(resolver) if self.declared_type else []
        const_err: list[Error] = []
        if "const" in self.attributes:
            if self.attributes.get("const") is not None:
                const_err.append(Error(self.line_ref, "[const] takes no arguments"))
            if not isinstance(self.default_value, (e.IntegerExpression, e.FloatExpression, e.StringExpression)):
                const_err.append(Error(self.line_ref, "[const] requires a literal value"))
        return err1 + err2 + const_err

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

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,Any],Any]) -> Statement:
        return cast(Statement, replace(resolver, dataclasses.replace(self,
            default_value=self.default_value and self.default_value.search_and_replace(resolver, replace),
            declared_type=self.declared_type.search_and_replace(resolver, replace) if self.declared_type else None,
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

    def generate(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> g.OperationBundle:
        expr_bundle = self.default_value.generate(resolver).rename_vars(1)
        sv = cg_p.StackVar(self.declared_type.generate(), self.name)
        init_bundle = g.OperationBundle(
            stack_vars=(sv,),
            operations=(cg_o.Move(sv, expr_bundle.result_var),),
            result_var=None
        )
        # After (expr_bundle + init_bundle).rename_vars(1), `_` lands at index
        # len(expr_bundle.stack_vars) in the combined tuple, so its renamed name
        # is uvar_1_N.  Pass that renamed var as root so unpack ops reference it
        # directly — they survive rename_vars(2) untouched.
        sv_renamed = cg_p.StackVar(sv.type, f"uvar_1_{len(expr_bundle.stack_vars)}")
        unpack_bundle = self.to_c_destructure(sv_renamed)
        return (expr_bundle + init_bundle).rename_vars(1) + unpack_bundle.rename_vars(2)

    def add_namespace(self, path: str):
        x: DestructureStatement = cast(DestructureStatement, super().add_namespace(path))
        return dataclasses.replace(x, targets=[l.add_namespace(path) for l in self.targets])

    def compile(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> tuple[DestructureStatement, list[Statement]]:
        stmt, stmt_glb = super().compile(resolver, func_ret_type)
        # Propagate inferred tuple entry types to targets that have no declared_type.
        parent_type = stmt.declared_type
        targets = stmt.targets
        if isinstance(parent_type, t.TupleSpec) and len(parent_type.entries) == len(targets):
            targets = [
                dataclasses.replace(tgt, declared_type=entry.type)
                if tgt.declared_type is None and entry.type is not None
                else tgt
                for tgt, entry in zip(targets, parent_type.entries)
            ]
            stmt = dataclasses.replace(stmt, targets=targets)
        results = [x.compile(resolver, None) for x in stmt.targets]
        tgts = [x[0] for x in results]
        tgts_glb = [g for x in results for g in x[1]]
        stmt = dataclasses.replace(stmt, targets=tgts)
        return cast(DestructureStatement, stmt), stmt_glb+tgts_glb

    # def check(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> list[Error]:
    #     return super(self).check(resolver, func_ret_type)
    #

    def flatten_to(self, path_to_thing, path):
        return [path_to_thing(path + [entry]) for target in self.targets for entry in target.flatten()]


@dataclass
class ReturnStatement(Statement):
    value: e.Expression

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,Any],Any]) -> Statement:
        return cast(Statement, replace(resolver, dataclasses.replace(self,
            value=self.value.search_and_replace(resolver, replace))))

    def compile(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> tuple[Statement | None, list[Statement]]:
        new_value, stmts = self.value.compile(resolver, func_ret_type)
        return dataclasses.replace(self, value=new_value), stmts

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

    def compile(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> tuple[Statement | None, list[Statement]]:
        return self, []

    def check(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> list[Error]:
        return []


@dataclass
class NamespaceStatement(Statement):
    path: str

    def compile(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> tuple[Statement | None, list[Statement]]:
        return self, []

    def check(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> list[Error]:
        return []


@dataclass
class TypeAliasStatement(TypeStatement):
    type: t.TypeSpec

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,Any],Any]) -> Statement:
        return cast(Statement, replace(resolver, dataclasses.replace(self,
            type=self.type.search_and_replace(resolver, replace))))

    def get_type(self) -> t.TypeSpec|None:
        return self.type if self.type.is_concrete() else None

    def compile(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> tuple[Statement | None, list[Statement]]:
        new_type, new_statements = self.type.compile(resolver)
        return dataclasses.replace(self, type=new_type), new_statements

    def check(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> list[Error]:
        return self.type.check(resolver)


@dataclass
class EnumStatement(TypeStatement):
    parameters: DestructureStatement
    variants: list[EnumStatement]
    _root_name: str | None = field(default=None, compare=False)
    _enum_spec: t.EnumSpec | None = field(default=None, compare=False)

    def get_type(self) -> t.EnumSpec | None:
        return self._enum_spec

    def add_namespace(self, path: str):
        new_variants = [v.add_namespace(path) for v in self.variants]
        return dataclasses.replace(self, name=f"{path}{self.name}", variants=new_variants)

    def _collect_leaf_names(self) -> list[str]:
        if not self.variants:
            return [self.name]
        return [ln for v in self.variants for ln in v._collect_leaf_names()]

    def _collect_data_fields(self) -> list[tuple[str, t.TypeSpec]]:
        seen: set[str] = set()
        result: list[tuple[str, t.TypeSpec]] = []
        def collect(node: EnumStatement):
            for let in node.parameters.flatten():
                if let.name not in seen and let.declared_type is not None:
                    seen.add(let.name)
                    result.append((let.name, let.declared_type))
            for v in node.variants:
                collect(v)
        collect(self)
        return result

    def _assign_specs(self, root_name: str, all_leaf_names: tuple[str, ...], all_fields: tuple[tuple[str, t.TypeSpec], ...]) -> EnumStatement:
        my_leaves = frozenset(self._collect_leaf_names())
        my_spec = t.EnumSpec(self.line_ref, root_name, my_leaves, all_leaf_names, all_fields)
        new_variants = [v._assign_specs(root_name, all_leaf_names, all_fields) for v in self.variants]
        return dataclasses.replace(self, variants=new_variants, _root_name=root_name, _enum_spec=my_spec)

    def compile(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> tuple[EnumStatement, list[Statement]]:
        # Expose this enum's generic type params (K, V, …) so that variant
        # parameter types like `tail: _Bucket<K,V>` can resolve K and V.
        if self.type_params:
            resolver = g.ResolverType(resolver, self._find_generic_types)
        new_parameters, prm_stmts = self.parameters.compile(resolver, None)
        new_variants: list[EnumStatement] = []
        var_stmts: list[Statement] = []
        for v in self.variants:
            cv, vg = v.compile(resolver, None)
            new_variants.append(cv)
            var_stmts.extend(vg)
        root_name = self.name
        tag_field: tuple[str, t.TypeSpec] = ("$tag", t.BuiltinSpec(self.line_ref, "int32"))
        temp = dataclasses.replace(self, parameters=new_parameters, variants=new_variants)
        all_leaf_names = tuple(temp._collect_leaf_names())
        data_fields = temp._collect_data_fields()
        all_fields = (tag_field,) + tuple(data_fields)
        final_variants = [v._assign_specs(root_name, all_leaf_names, all_fields) for v in new_variants]
        my_leaves = frozenset(all_leaf_names)
        my_spec = t.EnumSpec(self.line_ref, root_name, my_leaves, all_leaf_names, all_fields)
        new_self = dataclasses.replace(self,
            parameters=new_parameters, variants=final_variants,
            _root_name=root_name, _enum_spec=my_spec)
        return new_self, prm_stmts + var_stmts

    def check(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> list[Error]:
        if self._enum_spec is None:
            return [Error(self.line_ref, "Missed compile step")]
        errors: list[Error] = list(self.parameters.check(resolver, None))
        for v in self.variants:
            errors += v.check(resolver, None)
        return errors

    def global_codegen(self, resolver: g.Resolver) -> cg_x.Object | None:
        # Simple enums lower to flat by-value structs and need no heap
        # object. Complex enums (recursive or many-fielded) register a
        # single Object keyed by the root name; emit only at the root
        # statement (skip variants nested in `variants`, which carry the
        # same root_name).
        if self._enum_spec is None or not self._enum_spec.is_complex:
            return None
        if self._root_name is not None and self._root_name != self.name:
            return None
        # First field MUST be ("type", DataPointer()) per Object's contract.
        # all_fields[0] is already ("$tag", Int(32)); subsequent entries are
        # the union of all variants' data fields.
        fields = (("type", cg_t.DataPointer()),) + tuple(
            (name, ftype.generate()) for name, ftype in self._enum_spec.all_fields)
        return cg_x.Object(
            name=self.name,
            extends=(),
            functions=(),
            fields=cg_t.ImmediateStruct(fields))

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver, Any], Any]) -> Statement:
        # Expose generic type params so variant field types resolve correctly.
        variant_resolver = g.ResolverType(resolver, self._find_generic_types) if self.type_params else resolver
        new_params = cast(DestructureStatement, self.parameters.search_and_replace(variant_resolver, replace))
        new_variants = [cast(EnumStatement, v.search_and_replace(variant_resolver, replace)) for v in self.variants]
        new_spec = self._enum_spec.search_and_replace(resolver, replace) if self._enum_spec else None
        new_self = dataclasses.replace(self,
            parameters=new_params, variants=new_variants,
            _enum_spec=new_spec if isinstance(new_spec, t.EnumSpec) else None)
        return cast(Statement, replace(resolver, new_self))


@dataclass
class ActionStatement(Statement):
    action: e.Expression

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,Any],Any]) -> Statement:
        return cast(Statement, replace(resolver, dataclasses.replace(self,
            action=self.action.search_and_replace(resolver, replace))))

    def compile(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> tuple[Statement | None, list[Statement]]:
        new_action, stmts = self.action.compile(resolver, None)
        return dataclasses.replace(self, action = new_action), stmts

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        return self.action.check(resolver, None)

    def generate(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> g.OperationBundle:
        return self.action.generate(resolver)


@dataclass
class IfStatement(Statement):
    condition: e.Expression
    if_true: Statement
    if_false: Statement

