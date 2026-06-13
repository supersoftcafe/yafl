from __future__ import annotations

import itertools
from functools import reduce
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

    def _find_trait_data(self, resolver: g.Resolver, query: str) -> list[g.Resolved[DataStatement]]:
        def find_in_class(tp: t.ClassSpec) -> list[g.Resolved[DataStatement]]:
            found = [rs.statement for rs in resolver.find_type(tp.name)]
            match found:
                case [ClassStatement() as cls]:
                    if len(tp.type_params) != len(cls.type_params):
                        return []
                    # Search direct members first
                    direct = [x for x in cls.parameters.flatten() + cls.statements
                              if g.name_matches(x.name, query)]
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

    def _find_generic_types(self, query: str) -> list[g.Resolved[TypeStatement]]:
        return [g.Resolved(tp.name, tp, g.ResolvedScope.LOCAL) for tp in self.type_params if g.name_matches(tp.name, query)]

    def _initialiser_resolver(self, resolver: g.Resolver,
                              local_lets: Sequence[DataStatement] = ()) -> g.Resolver:
        """Resolver for a body or initialiser: this statement's generic type
        params, any local lets (a function's parameters), and the trait /
        interface methods — operators included — that are in scope. Function
        bodies and global-let initialisers share it so operators resolve the
        same in each."""
        typed = g.ResolverType(resolver, self._find_generic_types)
        def find_data(query: str) -> list[g.Resolved[DataStatement]]:
            found = [g.Resolved(let.name, let, g.ResolvedScope.LOCAL)
                     for let in local_lets if g.name_matches(let.name, query)]
            return found + self._find_trait_data(typed, query)
        return g.ResolverData(typed, find_data)

    def add_namespace(self, path: str):
        return dataclasses.replace(self, name=f"{path}{self.name}")

    def check_caller_type_params(self, resolver: g.Resolver, caller_type_params: Sequence[t.TypeSpec], line_ref: LineRef) -> list[Error]:
        if len(caller_type_params) > len(self.type_params):
            return [Error(line_ref, "Excess type parameters")]
        if len(caller_type_params) < len(self.type_params):
            return [Error(line_ref, "Not enough type parameters")]

        # replace type_params with real types in a temporary type ref
        type_params = [dataclasses.replace(tp, type=ct) for ct, tp in zip(caller_type_params, self.type_params)]
        resolver = g.ResolverType(resolver, lambda query:
            [g.Resolved(tp.name, tp, g.ResolvedScope.LOCAL) for tp in type_params if g.name_matches(tp.name, query)])

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

    def __find_locals(self, resolver: g.Resolver) -> Callable[[str],list[g.Resolved[DataStatement]]]:
        def finder(query: str) -> list[g.Resolved[DataStatement]]:
            p = [g.Resolved(let.name, let, g.ResolvedScope.LOCAL)
                 for let in self.parameters.flatten()
                 if g.name_matches(let.name, query)]
            td = self._find_trait_data(resolver, query)
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

        tail_err: list[Error] = []
        if "tail" in self.attributes:
            if self.attributes.get("tail") is not None:
                tail_err.append(Error(self.line_ref, "[tail] takes no arguments"))
            if self.body is None:
                tail_err.append(Error(self.line_ref, "[tail] cannot be applied to a foreign function"))

        terminal_err: list[Error] = []
        if "terminal" in self.attributes and self.attributes.get("terminal") is not None:
            terminal_err.append(Error(self.line_ref, "[terminal] takes no arguments"))

        return err1 + err2 + err3 + err4 + foreign_err + impure_err + sync_err + tail_err + terminal_err

    def global_codegen(self, resolver: g.Resolver) -> cg_x.Function:
        resolver = g.ResolverType(resolver, self._find_generic_types)
        resolver = g.ResolverData(resolver, self.__find_locals(resolver))

        bundle = g.OperationBundle()
        for index, parameter in enumerate(self.parameters.targets):
            bundle = bundle + parameter.to_c_destructure(None).with_prefix(f"p{index}")
        if self.body is not None:
            body_bundle = self.body.generate_to(resolver, self.return_type)
            ret_bundle = g.OperationBundle((), (cg_o.Return(body_bundle.result_var),))
            bundle = bundle + (body_bundle + ret_bundle).with_prefix("body")

        params: list[tuple[str, cg_t.Type]] = [("this", cg_t.DataPointer())]
        for prm in self.parameters.targets:
            xname = str(prm.name)
            xtype = prm.declared_type.generate(resolver)
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
            result = self.return_type.generate(resolver),
            stack_vars = cg_t.Struct(fields = tuple(vars)),
            ops = tuple(bundle.operations),
            comment = self.name,
            foreign_symbol = foreign_symbol,
            sync = "sync" in self.attributes,
            tail = "tail" in self.attributes,
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


    def __find_locals(self, resolver: g.Resolver) -> Callable[[str],list[g.Resolved[DataStatement]]]:
        # `this` inside a generic class must carry the class's type
        # placeholders, otherwise its ClassSpec has zero type params and
        # any later type-check against the class's declared arity fails
        # with "Not enough type parameters".
        this_type = t.ClassSpec(self.line_ref, self.name,
                                type_params=tuple(tp.type for tp in self.type_params))
        def finder(query: str) -> list[g.Resolved[DataStatement]]:
            m = self.find_data(resolver, query)
            l = LetStatement(self.line_ref, "this", None, {}, (), None, this_type)
            s = [g.Resolved("this", l, g.ResolvedScope.LOCAL)] if "this" == query else []
            td = self._find_trait_data(resolver, query)
            return m + s + td
        return finder

    def find_data(self, resolver: g.Resolver, query: str) -> list[g.Resolved[DataStatement]]:
        # The trailing array field is internal storage — member access to it
        # resolves to the generated accessor method (same name, see
        # create_array_accessor), not the raw field. Construction and codegen
        # reach the storage directly via get_fields/parameters, not find_data.
        array_param = self.array_field(resolver)
        s1 = [p for p in self.parameters.flatten() if p is not array_param]
        s2 = self.statements
        statements = s1 + s2
        # a) try to find in this class. Anything we find masks out parent matches, so no need to recurse.
        # b) if 'a' fails, search all parents and accumulate all the results.
        matches = [g.Resolved(x.name, x, g.ResolvedScope.MEMBER) for x in statements if g.name_matches(x.name, query)] \
               or [match for xtype, parent in c.find_classes_or_error(self.implements, resolver)
                         if isinstance(parent, ClassStatement)
                         for match in parent.find_data(resolver, query)]
        return matches


    def get_fields(self, resolver: g.Resolver) -> list[LetStatement]:
        s1 = self.parameters.flatten()
        s2 = [s for s in self.statements if isinstance(s, LetStatement)]
        return s1 + s2

    def array_field(self, resolver: g.Resolver) -> LetStatement | None:
        """The trailing variable-length array field (declared `name: Elem[lenField]`),
        or None for an ordinary class. An array class has exactly one — enforced,
        along with `[final]` and the length field's existence/type, in check()."""
        for f in self.get_fields(resolver):
            if isinstance(f.declared_type, t.ArrayFieldSpec):
                return f
        return None


    @property
    def is_abstract(self) -> bool:
        return any(1 for x in self._all_slots or [] if not x.provides)


    def get_type(self) -> t.ClassSpec|None:
        return t.ClassSpec(self.line_ref, self.name,
                           type_params=tuple(tp.type for tp in self.type_params))


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

        # Recurse to compile parameters and statements.
        # Both need access to the class's own generic type params (`type_resolver`)
        # so that a `T` referenced inside the constructor destructure (e.g.
        # `class Box<T>(value: T)`) or inside a method body resolves to the
        # class's GenericPlaceholderSpec rather than failing the lookup.
        new_parameters, prm_glb = self.parameters.compile(type_resolver, None)
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

        # Recurse to check parameters and statements.
        # Parameters need the generic-aware resolver too — a constructor
        # destructure like `class Box<T>(value: T)` must see T as a
        # GenericPlaceholderSpec, not fail to resolve.
        type_resolver = g.ResolverType(resolver, self._find_generic_types)
        prm_err = self.parameters.check(type_resolver, None)
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

        if "linear" in self.attributes:
            if self.attributes.get("linear") is not None:
                class_linear_err = [Error(self.line_ref, "[linear] takes no arguments")]
            elif "final" not in self.attributes:
                class_linear_err = [Error(self.line_ref, "[linear] classes must also be [final]")]
            else:
                class_linear_err = []
        else:
            class_linear_err = []

        linear_tp_err = [Error(self.line_ref, "[linear] type parameters are only supported on functions")
                         for tp in self.type_params if "linear" in tp.attributes]

        # A trailing variable-length array field (`name: Elem[lenField]`) requires
        # the class to be [final] (its storage is last in the object, so nothing
        # may subclass past it) and that `lenField` names an Int32 field of the
        # class. At most one such field is allowed.
        fields = self.get_fields(resolver)
        array_fields = [f for f in fields if isinstance(f.declared_type, t.ArrayFieldSpec)]
        array_err: list[Error] = []
        if array_fields:
            if len(array_fields) > 1:
                array_err.append(Error(self.line_ref, "a class may have at most one array field"))
            if "final" not in self.attributes:
                array_err.append(Error(self.line_ref, "a class with an array field must be [final]"))
            for af in array_fields:
                len_name = cast(t.ArrayFieldSpec, af.declared_type).length_field
                matches = [f for f in fields if g.name_matches(f.name, len_name)]
                if not matches:
                    array_err.append(Error(af.line_ref,
                        f"array length field '{len_name}' is not a field of this class"))
                elif not (isinstance(matches[0].declared_type, t.BuiltinSpec)
                          and matches[0].declared_type.type_name == "int32"):
                    array_err.append(Error(af.line_ref,
                        f"array length field '{len_name}' must be of type Int32"))

        return prm_err + stm_err + impl_err + cls_type_err + final_err + class_foreign_err + class_linear_err + linear_tp_err + bad_slots_err + empty_slots_err + array_err


    def global_codegen(self, resolver: g.Resolver) -> tuple[cg_x.Object, list[cg_x.Function]]:
        resolver = g.ResolverType(g.ResolverData(resolver, self.__find_locals(resolver)), self._find_generic_types)
        ast_functions = [fnc for fnc in self.statements if isinstance(fnc, FunctionStatement)]
        gen_functions = [fnc.global_codegen(resolver) for fnc in ast_functions]

        extends = () if self.is_interface else tuple(sorted(x.as_unique_id_str() for x in self._all_parents if x.as_unique_id_str()))
        functions = () if self.is_interface else tuple((y, x.name) for x in self._all_slots for y in sorted(x.provides))

        function_names = {f for s,f in functions}
        thunks = [c.create_thunk(self.name, x, resolver) for x in self.parameters.flatten() if x.name in function_names]

        params = self.parameters.flatten()
        array_param = self.array_field(resolver)
        if array_param is None:
            scalar_fields = tuple((p.name, p.get_type().generate(resolver)) for p in params)
            length_field = None
        else:
            # The array field becomes the object's trailing storage: a 0-length
            # `Array` named "array" (the Object IR requires that name/shape), with
            # the scalar fields — including the length field — laid out before it.
            af_spec = cast(t.ArrayFieldSpec, array_param.declared_type)
            scalars = [p for p in params if p is not array_param]
            scalar_fields = (tuple((p.name, p.get_type().generate(resolver)) for p in scalars)
                             + (("array", cg_t.Array(af_spec.element.generate(resolver), 0)),))
            length_field = next(p.name for p in scalars if g.name_matches(p.name, af_spec.length_field))

        xobject = cg_x.Object(
            name=self.name,
            extends=extends,
            functions=functions,
            fields=cg_t.ImmediateStruct((("type", cg_t.DataPointer()),) + scalar_fields),
            length_field=length_field,
            comment=self.name,
            is_foreign="foreign" in self.attributes
        )

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

    def is_deferred_init(self) -> bool:
        """True if this let is initialised lazily — its RHS is wrapped in
        a closure and evaluation is deferred until first force.  Today
        that means `[lazy]`; future deferred-eval attributes route through
        the same predicate so callers don't need to enumerate them.

        Used to keep multiple compiler stages in lock-step:
        `ast_inline` skips statement-level inlining; `lower_lazy_lets`
        wraps the RHS in a `()=>expr` lambda; `NamedExpression.generate`
        returns DataPointer-typed storage (the stub pointer);
        `BlockExpression.generate` hoists stub allocation to block entry.
        Any new pass that special-cases lazy lets should consult this
        predicate rather than spelling out `"lazy" in attributes`.
        """
        return "lazy" in self.attributes

    def add_namespace(self, path: str):
        return self if self.name == '_' else super().add_namespace(path)

    def to_c_destructure(self, root: cg_p.RParam | None, resolver: g.Resolver = None) -> g.OperationBundle:
        if root:
            # Leaf node, move the value into a stack var
            var = cg_p.StackVar(self.get_type().generate(resolver), self.name)
            return g.OperationBundle(
                stack_vars=(var,),
                operations=(cg_o.Move(var, root),),
                result_var=None)
        else:
            # Just a value, no work, caller does it
            return g.OperationBundle()

    def compile(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> tuple[LetStatement | None, list[Statement]]:
        dv, dv_glb = self.default_value.compile(resolver, self.declared_type) if self.default_value else (None, [])
        dt, dt_glb = self.declared_type.compile(resolver) if self.declared_type else (None, [])
        # Refine declared_type from the default value while it is not yet
        # concrete (still contains unresolved NamedSpecs anywhere in the
        # spec tree).  Use TypeSpec.is_concrete() rather than an ad-hoc
        # recursive predicate, so all compound specs (tuples, callables,
        # combinations, etc.) are checked uniformly.  The compile loop
        # iterates until the inferred type stabilises as concrete.
        if dv is not None and (dt is None or not dt.is_concrete()):
            inferred = dv.get_type(resolver)
            if inferred is not None and inferred.is_concrete():
                dt = inferred
        stmt = dataclasses.replace(self, default_value=dv, declared_type=dt)
        return stmt, dv_glb+dt_glb

    def check(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> list[Error]:
        if self.default_value and self.declared_type:
            xtype = self.default_value.get_type(resolver)
            if xtype is not None and t.trivially_assignable_equals(resolver, self.declared_type, xtype) is False:
                return [Error(self.line_ref, "Incorrect type")]
        err1 = self.default_value.check(resolver, self.declared_type) if self.default_value else []
        err2 = self.declared_type.check(resolver) if self.declared_type else []
        const_err: list[Error] = []
        if "const" in self.attributes:
            if self.attributes.get("const") is not None:
                const_err.append(Error(self.line_ref, "[const] takes no arguments"))
            if not isinstance(self.default_value, (e.IntegerExpression, e.FloatExpression, e.StringExpression, e.BoolExpression)):
                const_err.append(Error(self.line_ref, "[const] requires a literal value"))
        lazy_err: list[Error] = []
        if "lazy" in self.attributes:
            if self.attributes.get("lazy") is not None:
                lazy_err.append(Error(self.line_ref, "[lazy] takes no arguments"))
            if self.default_value is None:
                lazy_err.append(Error(self.line_ref, "[lazy] requires an initialiser"))
        return err1 + err2 + const_err + lazy_err

    def generate(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> g.OperationBundle:
        # `[lazy]` lets are handled out-of-band by `BlockExpression.generate`:
        # it hoists `generate_lazy_alloc` to block entry and emits
        # `generate_lazy_populate` at the let's textual position.  Any
        # other call site is a bug — silently emitting only the
        # closure-population half would leave the stub unallocated and
        # crash at force.  Surface the bug instead of papering over it.
        if self.is_deferred_init():
            raise RuntimeError(
                f"[lazy] let {self.name!r} reached LetStatement.generate "
                f"directly — this should only happen via "
                f"BlockExpression.generate's two-phase emission. "
                f"A new generate-site that holds nested LetStatements "
                f"needs the same hoist treatment.")
        expr_bundle = self.default_value.generate_to(resolver, self.declared_type).with_prefix("expr")
        sv = cg_p.StackVar(self.declared_type.generate(resolver), self.name)
        init_bundle = g.OperationBundle(
            stack_vars=(sv,),
            operations=(cg_o.Move(sv, expr_bundle.result_var),),
            result_var=None
        )
        unpack_bundle = self.to_c_destructure(None).with_prefix("unpack")
        return expr_bundle + init_bundle + unpack_bundle

    def generate_lazy_alloc(self, resolver: g.Resolver) -> g.OperationBundle:
        """Stub allocation half of a `[lazy]` local let — emit at block
        entry so forward references inside other lazies see the stub
        slot pointing at a real heap object.

        Allocates the `Lazy$<irmangle>` stub, clears `flag` and `closure`
        to zero.  Closure population happens later via `generate_lazy_populate`
        at the let's original textual position.
        """
        import lowering.lazy_thunks as lt

        ir_t = self.declared_type.generate(resolver)
        lt._ir_mangle(ir_t)
        cls = lt.stub_class_name(ir_t)

        sv_stub   = cg_p.StackVar(cg_t.DataPointer(), self.name)
        flag_f    = cg_p.ObjectField(cg_t.DataPointer(), sv_stub, cls, "flag",    None)
        closure_f = cg_p.ObjectField(cg_t.FuncPointer(), sv_stub, cls, "closure", None)
        return g.OperationBundle(
            stack_vars=(sv_stub,),
            operations=(
                cg_o.NewObject(cls, sv_stub),
                cg_o.Move(flag_f,    cg_p.NullPointer()),
                cg_o.Move(closure_f, cg_p.ZeroOf(cg_t.FuncPointer())),
            ),
            result_var=None,
        )

    def generate_lazy_populate(self, resolver: g.Resolver) -> g.OperationBundle:
        """Closure-population half of a `[lazy]` local let — emit at the
        let's original textual position.

        Pre-condition: `lower_lazy_lets` has wrapped the RHS in a
        `() => expr` LambdaExpression, the lambdas pass has converted it
        to a fun_t-valued expression (`DotExpression(NewExpression(...))`
        for capturing closures, `NamedExpression` for captureless ones),
        and `generate_lazy_alloc` has already emitted the stub allocation
        at block entry — so the stub stack var is bound and the slot
        points at a real heap object by the time we get here.
        """
        import lowering.lazy_thunks as lt

        ir_t = self.declared_type.generate(resolver)
        cls  = lt.stub_class_name(ir_t)

        closure_bundle = self.default_value.generate(resolver).with_prefix("closure")
        sv_stub   = cg_p.StackVar(cg_t.DataPointer(), self.name)
        closure_f = cg_p.ObjectField(cg_t.FuncPointer(), sv_stub, cls, "closure", None)
        return closure_bundle + g.OperationBundle(
            stack_vars=(),
            operations=(cg_o.Move(closure_f, closure_bundle.result_var),),
            result_var=None,
        )

    def global_codegen(self, resolver: g.Resolver) -> tuple[list[cg_x.Global], list[cg_x.Function]]:
        if self.is_deferred_init():
            return self.__global_codegen_lazy(resolver)

        # Non-`[lazy]` globals reach here only when `lower_lazy_lets` did
        # *not* auto-promote them — meaning `_is_trivial_expr` accepted
        # the AST shape.  Three direct-emission paths:
        #
        #   1. literal scalar / string → single-RParam Global.
        #   2. `ClassName(literal, …)` → static class-instance Global
        #      whose `init` is a NewStruct of the literal args.
        #   3. tuple of literals → flat-struct Global.
        #
        # None of these go through `$lazy$init`.
        if self.default_value is not None:
            static = self.__try_static_class_init(resolver)
            if static is not None:
                return [static], []

        xtype = self.get_type().generate(resolver)
        rparam: cg_p.RParam | None = None
        if self.default_value is not None:
            init = self.default_value.generate_to(resolver, self.declared_type)
            if init.operations or init.stack_vars or init.result_var is None:
                raise RuntimeError(
                    f"non-lazy global {self.name!r} produced a non-trivial "
                    f"init bundle — lower_lazy_lets should have auto-promoted "
                    f"it to [lazy].")
            rparam = init.result_var
        return [cg_x.Global(self.name, xtype, rparam)], []

    def __try_static_class_init(self, resolver: g.Resolver) -> cg_x.Global | None:
        """Match `let x: T = ClassName(literal, …)` and emit `x` directly
        as a static class-instance Global with `object_name=ClassName`
        and `init=NewStruct((field, literal_rparam), …)`.

        Returns the Global on a successful match, or None to fall back
        to the generic generate() path.  The match is the AST counterpart
        of the legacy staticinit + resolve_flat_struct_global_inits
        optimisations — performed upfront so we never spin up the lazy
        framework for a global the compiler can statically initialise.
        """
        dv = self.default_value
        if not isinstance(dv, e.CallExpression):
            return None
        if not isinstance(dv.function, e.NamedExpression):
            return None
        if not isinstance(dv.parameter, e.TupleExpression):
            return None
        found = resolver.find_type(dv.function.name)
        if len(found) != 1 or not isinstance(found[0].statement, ClassStatement):
            return None
        cls = found[0].statement
        field_defs = list(cls.parameters.flatten())
        args = dv.parameter.expressions
        if len(args) != len(field_defs):
            return None

        init_pairs: list[tuple[str, cg_p.RParam]] = []
        for arg_entry, field_def in zip(args, field_defs):
            # Any arg whose generate() produces a single RParam with no
            # operations / stack vars is acceptable as a static
            # initialiser — covers literals AND tuples of literals
            # (whose generate() produces a NewStruct of literal RParams).
            ab = arg_entry.value.generate_to(resolver, field_def.declared_type)
            if ab.operations or ab.stack_vars or ab.result_var is None:
                return None
            init_pairs.append((field_def.name, ab.result_var))

        return cg_x.Global(
            name=self.name,
            type=cg_t.DataPointer(),
            init=cg_p.NewStruct(tuple(init_pairs)),
            object_name=cls.name,
        )

    def __global_codegen_lazy(self, resolver: g.Resolver) -> tuple[list[cg_x.Global], list[cg_x.Function]]:
        """`[lazy]` global lowering — emit a static `Lazy$<irmangle>`
        instance whose `closure` points at the lifted init function.

        Pre-condition: `lower_lazy_lets` has wrapped the RHS in a
        `() => expr` LambdaExpression, and the lambdas pass has converted
        it to a fun_t-valued NamedExpression of the lifted captureless
        function (globals can't reference function-locals, so the
        closure is always captureless).
        """
        import lowering.lazy_thunks as lt

        if self.default_value is None:
            raise ValueError(f"[lazy] global {self.name!r} requires an initialiser")

        xtype = self.get_type().generate(resolver)
        lt._ir_mangle(xtype)  # raise NotImplementedError early for unsupported types
        stub_cls = lt.stub_class_name(xtype)

        init = self.default_value.generate(resolver)
        if init.operations or init.stack_vars:
            raise ValueError(
                f"[lazy] global {self.name!r}: closure expression must reduce "
                f"to a single fun_t value — lambdas pass should have lifted "
                f"the captureless lambda.  Got default_value={type(self.default_value).__name__!r}, "
                f"ops={len(init.operations)}, stack_vars={len(init.stack_vars)}")
        closure_value = init.result_var
        assert closure_value is not None

        stub_init = cg_p.NewStruct((
            ("flag",    cg_p.NullPointer()),
            ("closure", closure_value),
            ("value",   cg_p.ZeroOf(xtype)),
        ))
        return [cg_x.Global(
            name=self.name,
            type=cg_t.DataPointer(),
            init=stub_init,
            object_name=stub_cls,
        )], []

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

    def to_c_destructure(self, root: cg_p.RParam | None, resolver: g.Resolver = None) -> g.OperationBundle:
        if not root:
            # The first attempt should declare the root var
            root = cg_p.StackVar(self.get_type().generate(resolver), self.name)
        bundles = [
            target.to_c_destructure(cg_p.StructField(root, f"_{index}"), resolver).with_prefix(f"f{index}")
            for index, target in enumerate(self.targets)
        ]
        return reduce(lambda a, b: a + b, bundles) if bundles else g.OperationBundle()

    def generate(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> g.OperationBundle:
        expr_bundle = self.default_value.generate_to(resolver, self.declared_type).with_prefix("expr")
        sv = cg_p.StackVar(self.declared_type.generate(resolver), self.name)
        init_bundle = g.OperationBundle(
            stack_vars=(sv,),
            operations=(cg_o.Move(sv, expr_bundle.result_var),),
            result_var=None
        )
        # `sv` is at the un-prefixed root of init_bundle; pass it directly as
        # the destructure root rather than predicting a renamed name.
        unpack_bundle = self.to_c_destructure(sv, resolver).with_prefix("unpack")
        return expr_bundle + init_bundle + unpack_bundle

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
        if xtype is not None and t.trivially_assignable_equals(resolver, func_ret_type, xtype) is False:
            return [Error(self.line_ref, "Incorrect return type")]
        return self.value.check(resolver, func_ret_type)

    def generate(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> g.OperationBundle:
        # Coerce the returned value to the function's declared return type — a
        # narrow value flowing out of a union-returning function is boxed here.
        op_bundle = self.value.generate_to(resolver, func_ret_type)
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
        errors += [Error(self.line_ref, "[linear] type parameters are only supported on functions")
                   for tp in self.type_params if "linear" in tp.attributes]
        return errors

    def global_codegen(self, resolver: g.Resolver) -> list[cg_x.Object]:
        # Simple enums lower to flat by-value structs and need no heap
        # objects. Complex enums (recursive or many-fielded) emit one Object
        # PER VARIANT — each with its own vtable, its own (variant-sized)
        # field layout, and the variant's global discriminator id — plus a
        # never-instantiated MARKER Object for the root, which every variant
        # `extends` so union membership tests (`object_is_instance` against
        # the root) keep working. There is no $tag in the payload: the
        # discriminant lives in the vtable, once per type. Emit only at the
        # root statement (variants nested in `variants` carry the same
        # root_name).
        if self._enum_spec is None or not self._enum_spec.is_complex:
            return []
        if self._root_name is not None and self._root_name != self.name:
            return []
        discriminators = resolver.get_discriminators()
        marker = cg_x.Object(
            name=self.name,
            extends=(),
            functions=(),
            fields=cg_t.ImmediateStruct((("type", cg_t.DataPointer()),)),
            comment=f"{self.name} — enum root marker (never instantiated)")
        objects = [marker]
        leaf_field_sets = t._collect_leaf_field_sets(self, [])
        for leaf_name, leaf_fields in zip(self._enum_spec.all_leaf_names, leaf_field_sets):
            obj_name = t.enum_leaf_object_name(self.name, leaf_name)
            fields = (("type", cg_t.DataPointer()),) + tuple(
                (let.name, let.declared_type.generate(resolver)) for let in leaf_fields)
            objects.append(cg_x.Object(
                name=obj_name,
                extends=(self.name,),
                functions=(),
                fields=cg_t.ImmediateStruct(fields),
                # Strict lookup: the registry enumerates leaves from these
                # same root statements, so a miss is a compiler bug — fail
                # here, not as a runtime dispatch fall-through.
                discriminator=discriminators[f"enumleaf({obj_name})"]))
        return objects

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
    """A first-class conditional statement.

    Branches are pure scopes — any `let`s inside a branch are branch-local
    and do not escape. There is no required structure (per the "only
    ambiguity is an error" principle): a branch may contain anything,
    including nothing. A branch ending in `ret` exits the function;
    otherwise control falls through to the statements after the `if`.
    """
    condition: e.Expression
    true_block: list[Statement]
    false_block: list[Statement]   # empty when there is no `else`

    def _branch_finder(self, stmts: list[Statement]) -> Callable[[str], list[g.Resolved[DataStatement]]]:
        def finder(query: str) -> list[g.Resolved[DataStatement]]:
            lets = [g.Resolved(let.name, let, g.ResolvedScope.LOCAL)
                    for x in stmts if isinstance(x, LetStatement)
                    for let in x.flatten() if g.name_matches(let.name, query)]
            funs = [g.Resolved(fun.name, fun, g.ResolvedScope.LOCAL)
                    for fun in stmts if isinstance(fun, FunctionStatement) and g.name_matches(fun.name, query)]
            return lets + funs
        return finder

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,Any],Any]) -> Statement:
        true_resolver = g.ResolverData(resolver, self._branch_finder(self.true_block))
        false_resolver = g.ResolverData(resolver, self._branch_finder(self.false_block))
        return cast(Statement, replace(resolver, dataclasses.replace(self,
            condition=self.condition.search_and_replace(resolver, replace),
            true_block=[x.search_and_replace(true_resolver, replace) for x in self.true_block],
            false_block=[x.search_and_replace(false_resolver, replace) for x in self.false_block])))

    def compile(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> tuple[Statement | None, list[Statement]]:
        new_cond, cond_glb = self.condition.compile(resolver, t.BuiltinSpec(self.line_ref, "bool"))

        def compile_branch(stmts: list[Statement]) -> tuple[list[Statement], list[Statement]]:
            stmts = collapse_else_if(stmts)
            nested = g.ResolverData(resolver, self._branch_finder(stmts))
            results = [x.compile(nested, func_ret_type) for x in stmts]
            new_stmts = [r[0] for r in results if r[0] is not None]
            glbs = [g for r in results for g in r[1]]
            return new_stmts, glbs

        new_true, true_glb = compile_branch(self.true_block)
        new_false, false_glb = compile_branch(self.false_block)
        return dataclasses.replace(self, condition=new_cond,
                                    true_block=new_true,
                                    false_block=new_false), cond_glb + true_glb + false_glb

    def check(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> list[Error]:
        errs: list[Error] = list(self.condition.check(resolver, t.BuiltinSpec(self.line_ref, "bool")))
        cond_type = self.condition.get_type(resolver)
        if cond_type is not None and not t.trivially_assignable_equals(
                resolver, t.BuiltinSpec(self.line_ref, "bool"), cond_type):
            errs.append(Error(self.condition.line_ref, "if condition must be Bool"))
        for stmts in (self.true_block, self.false_block):
            nested = g.ResolverData(resolver, self._branch_finder(stmts))
            for x in stmts:
                errs += x.check(nested, func_ret_type)
        return errs

    def generate(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> g.OperationBundle:
        cond_bundle = self.condition.generate(resolver).with_prefix("cond")

        def gen_branch(stmts: list[Statement], prefix: str) -> g.OperationBundle:
            nested = g.ResolverData(resolver, self._branch_finder(stmts))
            bundle = g.OperationBundle()
            for i, stmt in enumerate(stmts):
                bundle = bundle + stmt.generate(nested, func_ret_type).with_prefix(f"{prefix}s{i}")
            return bundle

        true_bundle = gen_branch(self.true_block, "T")
        false_bundle = gen_branch(self.false_block, "F")

        return (
            cond_bundle
            + g.OperationBundle(operations=(
                cg_o.JumpIf("T_branch", cond_bundle.result_var),
                cg_o.Label("F_branch"),
            ))
            + false_bundle
            + g.OperationBundle(operations=(
                cg_o.Jump("if_end"),
                cg_o.Label("T_branch"),
            ))
            + true_bundle
            + g.OperationBundle(operations=(
                cg_o.Label("if_end"),
            ))
        )


@dataclass
class ElseIfStatement(Statement):
    """Parsed as a standalone statement; `collapse_else_if` folds proper
    `if`/`else if`/`else` sequences into nested `IfStatement`s. A surviving
    ElseIfStatement is an orphan (no preceding `if`) and `check()` reports it."""
    condition: e.Expression
    body: list[Statement]

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,Any],Any]) -> Statement:
        return cast(Statement, replace(resolver, dataclasses.replace(self,
            condition=self.condition.search_and_replace(resolver, replace),
            body=[x.search_and_replace(resolver, replace) for x in self.body])))

    def compile(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> tuple[Statement | None, list[Statement]]:
        return self, []

    def check(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> list[Error]:
        return [Error(self.line_ref, "`else if` without a matching preceding `if`")]

    def generate(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> g.OperationBundle:
        raise AssertionError("ElseIfStatement reached generate(); check() should have rejected it")


@dataclass
class ElseStatement(Statement):
    """See ElseIfStatement — same orphan-or-folded story."""
    body: list[Statement]

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,Any],Any]) -> Statement:
        return cast(Statement, replace(resolver, dataclasses.replace(self,
            body=[x.search_and_replace(resolver, replace) for x in self.body])))

    def compile(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> tuple[Statement | None, list[Statement]]:
        return self, []

    def check(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> list[Error]:
        return [Error(self.line_ref, "`else` without a matching preceding `if`")]

    def generate(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> g.OperationBundle:
        raise AssertionError("ElseStatement reached generate(); check() should have rejected it")


def collapse_else_if(stmts: list[Statement]) -> list[Statement]:
    """Fold `IfStatement` followed by zero or more `ElseIfStatement`s and
    at most one `ElseStatement` into a single right-nested `IfStatement`.
    Orphan `ElseIfStatement`/`ElseStatement` are passed through unchanged;
    their `check()` will report the error.

    Idempotent: if an `IfStatement` has no following `else if`/`else` it
    is passed through unchanged, preserving any `false_block` populated by
    a previous pass."""
    result: list[Statement] = []
    i = 0
    while i < len(stmts):
        stmt = stmts[i]
        if not isinstance(stmt, IfStatement):
            result.append(stmt)
            i += 1
            continue
        chain: list[tuple[e.Expression, list[Statement], LineRef]] = []
        else_body: list[Statement] | None = None
        i += 1
        while i < len(stmts):
            nxt = stmts[i]
            if isinstance(nxt, ElseIfStatement):
                chain.append((nxt.condition, nxt.body, nxt.line_ref))
                i += 1
            elif isinstance(nxt, ElseStatement):
                else_body = nxt.body
                i += 1
                break
            else:
                break
        if not chain and else_body is None:
            result.append(stmt)
            continue
        tail: list[Statement] = else_body if else_body is not None else []
        for cond, body, lr in reversed(chain):
            tail = [IfStatement(lr, cond, body, tail)]
        result.append(dataclasses.replace(stmt, false_block=tail))
    return result
