"""`class` / `interface` declarations: member resolution, trait parents,
vtable slot assignment, and class codegen.
"""
from __future__ import annotations

from functools import reduce
from collections.abc import Sequence
from typing import Callable, Iterable, Any
from dataclasses import dataclass, field
import dataclasses
import pyast.rewrite as rw

from langtools import checked_cast
from parsing.tokenizer import LineRef
from parsing.parselib import Error

import codegen.typedecl as cg_t
import codegen.ir as cg_ir

import pyast.classtools as c
import pyast.resolver as g
import pyast.expression as e
import pyast.typespec as t

import pyast.utils as u

from pyast.statement.base import Statement, NamedStatement, TypeStatement, DataStatement, ImportGroup
from pyast.statement.lets import LetStatement, DestructureStatement
from pyast.statement.function import FunctionStatement


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

    def member_index(self) -> "g.Statements":
        """This class's own members (constructor params + statements) as a
        by-name-indexed collection, built once per class instance and reused
        for every member lookup. A rewritten class is a new instance with a
        fresh index, so there is nothing stale to invalidate."""
        idx = getattr(self, "_member_index", None)
        if idx is None:
            idx = g.Statements(self.parameters.flatten() + self.statements)
            object.__setattr__(self, "_member_index", idx)
        return idx


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
            # No trait data here: each method (a FunctionStatement) establishes
            # its own trait scope in its body resolver, so adding it here too
            # would double the in-scope operators.
            return m + s
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
        if self._all_parents is None:
            new_parents = rw.UNCHANGED
        else:
            pout, pchanged = set(), False
            for p in self._all_parents:
                r = p.search_and_replace(resolver, replace)
                pout.add(p if r is rw.UNCHANGED else r)
                pchanged = pchanged or r is not rw.UNCHANGED
            new_parents = pout if pchanged else rw.UNCHANGED
        return rw.rewrite(self, replace, nested_resolver,
            parameters=self.parameters.search_and_replace(resolver, replace),
            statements=rw.seq(self.statements, nested_resolver, replace),
            implements=rw.seq(self.implements, resolver, replace),
            trait_params=rw.seq(self.trait_params, resolver, replace),
            _all_parents=new_parents)


    def compile(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> tuple[Statement | None, list[Statement]]:
        # Resolve each of the inherited types and update the implements list
        # Use a resolver that includes this class's own generic type params so that
        # e.g. `TVal` in `class Foo<TVal> : Bar<TVal>` resolves to GenericPlaceholderSpec.
        type_resolver = g.ResolverType(resolver, self._find_generic_types)
        # `implements` is a flat list of individual interfaces (the parser splits
        # the `A | B` inheritance spelling — see __flatten_inheritance), so there
        # is no union left to unpack here.
        resolved_inheritance = c.find_classes_or_error(self.implements, type_resolver)
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
                    for parent in xcls._all_parents:
                        new_all_parents.add(t.substitute_placeholders(parent, mapping, resolver))
                else:
                    new_all_parents.update(xcls._all_parents)

        # Recurse to compile parameters and statements.
        # Both need access to the class's own generic type params (`type_resolver`)
        # so that a `T` referenced inside the constructor destructure (e.g.
        # `class Box<T>(value: T)`) or inside a method body resolves to the
        # class's GenericPlaceholderSpec rather than failing the lookup.
        new_parameters, prm_glb = self.parameters.compile(type_resolver, None)
        statement_resolver = g.ResolverType(g.ResolverData(resolver, self.__find_locals(resolver)), self._find_generic_types)
        # Member bodies resolve through the CLASS's `where` clause: a member
        # declares no generics/wheres of its own (a vtable slot has a fixed
        # signature), so each member function COMPILES under a transient copy
        # carrying the owner's clause — and the stored statement keeps none.
        new_statements, stm_glb = u.flatten_lists(
            self.__strip_owner_wheres(x, self.__with_owner_wheres(x).compile(statement_resolver, None))
            for x in self.statements)

        # A class `where` clause references the class's own type params (e.g.
        # `Wrap<S,E> … where Stream<S,Int,E>`), so it must compile under the
        # generic-types-in-scope resolver, like the parameters above.
        trts, trts_glb = u.flatten_lists(x.compile(type_resolver) for x in self.trait_params)

        result = dataclasses.replace(self,
              implements=new_implements,
              parameters=new_parameters,
              statements=new_statements,
              trait_params=tuple(trts),
              _all_slots=new_all_slots,
            _all_parents=new_all_parents)

        return result, prm_glb + trts_glb + stm_glb


    def __with_owner_wheres(self, x: Statement) -> Statement:
        if isinstance(x, FunctionStatement) and self.trait_params:
            return dataclasses.replace(x, trait_params=self.trait_params)
        return x

    def __strip_owner_wheres(self, original: Statement, compiled):
        new_x, extra = compiled
        if isinstance(original, FunctionStatement) and self.trait_params \
                and isinstance(new_x, FunctionStatement):
            new_x = dataclasses.replace(new_x, trait_params=())
        return new_x, extra

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

        # Fragile-base warning: one subclass method overriding several methods
        # of a single immediate parent (a set of very-similar functions one
        # broad override subsumes). Recompute base/parent (compile discards it).
        parent_classes = [xcls for (xtype, xcls) in resolved_inheritance
                          if isinstance(xcls, ClassStatement)]
        base_slots = c.create_slots_from_members(self)
        fragile_warns = [
            Error.warning(self.line_ref,
                f"`{g.bare_name(slot.name)}` overrides {len(names)} similar "
                f"methods of `{g.bare_name(parent_name)}` at once — a broad "
                f"override silently captures them; give it a narrower signature "
                f"or override each explicitly")
            for slot, parent_name, names in c.fragile_base_captures(
                resolver, base_slots, parent_classes)]

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
        stm_err = [x for stm in self.statements
                   for x in self.__with_owner_wheres(stm).check(resolver, None)]

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

        # `[linear] T` is allowed on an INTERFACE (a trait like Drop<[linear] T>
        # whose parameter may be instantiated with a linear type — the
        # instantiation-kind check in linearity.py reads this) but not on a
        # concrete class: flow analysis cannot trace a linear value stored in a
        # generic class field.
        linear_tp_err = ([] if self.is_interface else
                         [Error(self.line_ref, "[linear] type parameters are only supported on functions")
                          for tp in self.type_params if "linear" in tp.attributes])

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
                len_name = checked_cast(t.ArrayFieldSpec, af.declared_type).length_field
                matches = [f for f in fields if g.name_matches(f.name, len_name)]
                if not matches:
                    array_err.append(Error(af.line_ref,
                        f"array length field '{len_name}' is not a field of this class"))
                elif not (isinstance(matches[0].declared_type, t.BuiltinSpec)
                          and matches[0].declared_type.type_name == "int32"):
                    array_err.append(Error(af.line_ref,
                        f"array length field '{len_name}' must be of type Int32"))

        return prm_err + stm_err + impl_err + cls_type_err + final_err + class_foreign_err + class_linear_err + linear_tp_err + bad_slots_err + empty_slots_err + array_err + fragile_warns


    def global_codegen(self, resolver: g.Resolver) -> tuple[cg_ir.Object, list[cg_ir.Function]]:
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
            af_spec = checked_cast(t.ArrayFieldSpec, array_param.declared_type)
            scalars = [p for p in params if p is not array_param]
            scalar_fields = (tuple((p.name, p.get_type().generate(resolver)) for p in scalars)
                             + (("array", cg_t.Array(af_spec.element.generate(resolver), 0)),))
            length_field = next(p.name for p in scalars if g.name_matches(p.name, af_spec.length_field))

        xobject = cg_ir.Object(
            name=self.name,
            extends=extends,
            functions=functions,
            fields=cg_t.ImmediateStruct((("type", cg_t.DataPointer()),) + scalar_fields),
            length_field=length_field,
            comment=self.name,
            is_foreign="foreign" in self.attributes,
            # [mutable]: fields are written after construction, so the collector
            # must not relocate it — a write can otherwise land in a copy that is
            # then abandoned. Required by any late-initialised ("once") field;
            # see docs/memoize-proposal.md.
            is_mutable="mutable" in self.attributes
        )

        return xobject, gen_functions+thunks
