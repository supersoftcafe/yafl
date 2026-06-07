from __future__ import annotations

from typing import Callable, Any
import dataclasses
import random
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
from pyast.expression.base import Expression
from pyast.expression.literal import StringExpression
from pyast.expression.tuple_expr import TupleExpression


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



def _substitute_class_type_params(
        resolver: g.Resolver,
        receiver: t.ClassSpec,
        cdecl: s.ClassStatement,
        field_type: t.TypeSpec | None,
) -> t.TypeSpec | None:
    # Map the class's declared placeholders to the receiver's concrete
    # type arguments and rewrite placeholders inside the field's declared
    # type. Mirrors the parent-class substitution in ClassStatement.compile
    # so that e.g. `b: Box<Int>` → `b.value: Int` (not the bare `T`).
    if field_type is None or not cdecl.type_params or not receiver.type_params:
        return field_type
    mapping = {p.name: concrete for p, concrete in zip(cdecl.type_params, receiver.type_params)}
    def replace_fn(_, thing, m=mapping):
        if isinstance(thing, t.GenericPlaceholderSpec) and thing.name in m:
            return m[thing.name]
        return thing
    return field_type.search_and_replace(resolver, replace_fn)



def _reduce_list(resolver: g.Resolver, expected_type: t.TypeSpec | None, list_data: list[g.Resolved[s.DataStatement]]) -> list[g.Resolved[s.DataStatement]]:
    if len(list_data) <= 1:
        return list_data
    # Partition by verdict: definite matches (True) win over undecided ones
    # (None) when both are present. The undecided bucket is only returned
    # when no candidate matches definitively. This gives specific-beats-
    # generic dispatch — e.g. `0 == 1` picks `BasicEquality<Int>::==` over
    # the in-scope-but-unconstrained `BasicEquality<K>::==`.
    truthy: list[g.Resolved[s.DataStatement]] = []
    maybe: list[g.Resolved[s.DataStatement]] = []
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
        if b is True:
            truthy.append(x)
        elif b is None:
            maybe.append(x)
    return truthy if truthy else maybe



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
            case t.ClassSpec() as cspec:
                cdecl = resolver.find_type(cspec.name)
                if not cdecl or len(cdecl) > 1:
                    raise ValueError("A resolved class is later resolving incorrectly. Probably a compiler bug.")
                cdecl = cdecl[0].statement
                if not isinstance(cdecl, s.ClassStatement):
                    raise ValueError("A resolved class is later resolving to a wrong type. Probably a compiler bug.")
                datas = cdecl.find_data(resolver, self.name)
                if datas and len(datas) == 1:
                    return _substitute_class_type_params(
                        resolver, cspec, cdecl, datas[0].statement.get_type())
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
                cdecl = resolver.find_type(cname)
                if not cdecl or len(cdecl) > 1:
                    raise ValueError()
                cdecl = cdecl[0].statement
                if not isinstance(cdecl, s.ClassStatement):
                    raise ValueError()
                datas = _reduce_list(resolver, expected_type, cdecl.find_data(resolver, self.name))
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
                cdecl = resolver.find_type(cname)
                if not cdecl or len(cdecl) > 1:
                    raise ValueError()
                cdecl = cdecl[0].statement
                if not isinstance(cdecl, s.ClassStatement):
                    raise ValueError(self.line_ref, "Does not reference a class")
                datas = cdecl.find_data(resolver, self.name)
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
                cdecl = cast(s.ClassStatement, resolver.find_type(cname)[0].statement)
                data = cdecl.find_data(resolver, self.name)[0].statement
                xtype = data.get_type().generate(resolver)

                if not isinstance(data, s.FunctionStatement):
                    result_var = cg_p.ObjectField(xtype, base_bundle.result_var, cdecl.name, data.name, None)
                elif "final" not in cdecl.attributes:
                    result_var = cg_p.VirtualFunction(data.name, base_bundle.result_var)
                else:
                    result_var = cg_p.GlobalFunction(data.name, base_bundle.result_var, c_symbol=_foreign_symbol(data), impure=_is_impure(data), sync=_is_sync(data))

                return base_bundle + g.OperationBundle(stack_vars=(), operations=(), result_var=result_var)

            case t.EnumSpec() as es:
                stmts = resolver.find_type(es.root_name)
                assert len(stmts) == 1
                root_stmt = cast(s.EnumStatement, stmts[0].statement)
                variant_types = t.enum_variant_types(root_stmt, resolver)
                container, variant_map = cg_t.compute_union_slots(variant_types)
                leaf_field_sets = t._collect_leaf_field_sets(root_stmt, [])
                ptr = base_bundle.result_var

                def read_slot(si: int) -> cg_p.RParam:
                    slot_name, slot_type = container.fields[si]
                    if es.is_complex:
                        return cg_p.ObjectField(slot_type, ptr, es.root_name, slot_name, None)
                    return cg_p.StructField(ptr, slot_name)

                def reconstruct_from_slots(ftype, slot_assigns, off):
                    """Recursively rebuild ftype from union slots; returns (RParam, new_off)."""
                    if isinstance(ftype, cg_t.Struct):
                        fvs = []
                        for fname, ft in ftype.fields:
                            val, off = reconstruct_from_slots(ft, slot_assigns, off)
                            fvs.append((fname, val))
                        return cg_p.NewStruct(tuple(fvs)), off
                    si, _ = slot_assigns[off]
                    return read_slot(si), off + 1

                result_var = None
                for leaf_idx, leaf_fields in enumerate(leaf_field_sets):
                    offset = 0
                    for let in leaf_fields:
                        field_type = let.declared_type.generate(resolver)
                        n_prims = len(cg_t._flatten_primitives(field_type))
                        if let.name == self.name:
                            slots_for_field = [variant_map[leaf_idx][offset + p] for p in range(n_prims)]
                            result_var, _ = reconstruct_from_slots(field_type, slots_for_field, 0)
                            break
                        offset += n_prims
                    else:
                        continue
                    break
                assert result_var is not None, f"Field '{self.name}' not found in enum {es.root_name}"
                return base_bundle + g.OperationBundle((), (), result_var)

        raise ValueError("Could not generate dot expression")



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
        datas = resolver.find_data(self.name)
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
        datas = resolver.find_data(self.name)
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
        datas = resolver.find_data(self.name)
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
                # `name` resolves more than one way — commonly a top-level
                # namespace versus an import-relative one (loading a library can
                # introduce such a clash). There is no precedence rule: the user
                # must qualify. List every candidate's fully-qualified spelling so
                # they know which reading each one selects.
                candidates = ", ".join(sorted({d.unique_name for d in datas}))
                return [Error(self.line_ref,
                    f"Ambiguous reference '{self.name}' — qualify it. Candidates: {candidates}")] + tp_errors

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        if self.name == 'this':
            pass
        x = resolver.find_data(self.name)
        if not x:
            raise ValueError(f"Could not find {self.name}")
        x = x[0]
        match (x.scope, x.statement):
            case (g.ResolvedScope.GLOBAL, stmt) if isinstance(stmt, s.FunctionStatement):
                return g.OperationBundle((), (), cg_p.GlobalFunction(self.name, c_symbol=_foreign_symbol(stmt), impure=_is_impure(stmt), sync=_is_sync(stmt)))
            case (g.ResolvedScope.GLOBAL, stmt) if isinstance(stmt, s.LetStatement):
                xtype = stmt.declared_type
                if not xtype: raise ValueError(f"Failed to resolve {self.name} due to missing type")
                # Deferred-init lets are stored as a DataPointer to their
                # Lazy$<T> stub — not as the user-visible value type.
                # Any NamedExpression that survives lower_lazy_lets
                # (lambdas-pass capture sites, class-field initialisers)
                # needs the stub pointer, not the value.
                storage = cg_t.DataPointer() if stmt.is_deferred_init() else xtype.generate(resolver)
                return g.OperationBundle((), (), cg_p.GlobalVar(storage, self.name))
            case (g.ResolvedScope.LOCAL, stmt) if isinstance(stmt, s.LetStatement):
                xtype = stmt.declared_type
                if not xtype: raise ValueError(f"Failed to resolve {self.name} due to missing type")
                storage = cg_t.DataPointer() if stmt.is_deferred_init() else xtype.generate(resolver)
                return g.OperationBundle((), (), cg_p.StackVar(storage, self.name))
            case (scope, stmt):
                raise ValueError(f"Reference to {scope} / {type(stmt)} for named reference {self.name} not implemented yet")



@dataclass
class ArrayReadExpression(Expression):
    """Read element `index` of an array class's trailing storage, aborting if the
    index is out of range. This is the "function out" half of an array: the
    generated accessor method `(Int32): Elem` (created alongside the constructor)
    has this as its body. `object` is the array instance; `index` is the Int32
    offset. Lowers to a single `cg_p.ArrayElement` — the bounds check lives in
    the `array_bounds_check` runtime helper."""
    object: Expression
    index: Expression

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver, Any], Any]) -> Expression:
        return cast(Expression, replace(resolver, dataclasses.replace(self,
            object=self.object.search_and_replace(resolver, replace),
            index=self.index.search_and_replace(resolver, replace))))

    def __array_info(self, resolver: g.Resolver):
        """(class_name, element_spec, length_field_name) for `object`'s array
        class, or None if its type isn't resolved/an array class yet."""
        otype = self.object.get_type(resolver)
        if not isinstance(otype, t.ClassSpec):
            return None
        found = resolver.find_type(otype.name)
        if len(found) != 1 or not isinstance(found[0].statement, s.ClassStatement):
            return None
        classstmt = cast(s.ClassStatement, found[0].statement)
        af = classstmt.array_field(resolver)
        if af is None:
            return None
        af_spec = cast(t.ArrayFieldSpec, af.declared_type)
        len_name = next((f.name for f in classstmt.get_fields(resolver)
                         if g.name_matches(f.name, af_spec.length_field)), None)
        if len_name is None:
            return None
        return otype.name, af_spec.element, len_name

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        info = self.__array_info(resolver)
        return info[1] if info is not None else None

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement]]:
        obj, oglb = self.object.compile(resolver, None)
        idx, iglb = self.index.compile(resolver, t.BuiltinSpec(self.line_ref, "int32"))
        return dataclasses.replace(self, object=obj, index=idx), oglb + iglb

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        return self.object.check(resolver, None) + self.index.check(resolver, None)

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        info = self.__array_info(resolver)
        assert info is not None, "ArrayReadExpression on a non-array-class object"
        cname, elem_spec, len_name = info

        obj_b = self.object.generate(resolver).with_prefix("arr")
        idx_b = self.index.generate(resolver).with_prefix("idx")

        # Materialise object and index into single-assignment vars so the
        # ArrayElement param can name each once (it reads the base, the length,
        # and the index from them).
        obj_var = cg_p.StackVar(cg_t.DataPointer(), "aobj")
        idx_var = cg_p.StackVar(cg_t.Int(32), "aidx")
        elem = cg_p.ArrayElement(elem_spec.generate(resolver), obj_var, cname, "array", len_name, idx_var)

        return obj_b + idx_b + g.OperationBundle(
            stack_vars=(obj_var, idx_var),
            operations=(cg_o.Move(obj_var, obj_b.result_var), cg_o.Move(idx_var, idx_b.result_var)),
            result_var=elem)


@dataclass
class LazyExpression(Expression):
    """Auto-forced reference to a `[lazy]` let.

    Three modes, selected by where the reference textually appears:

    * **Local-scope** (default): the stub lives in a `StackVar` named
      `stub_name` in the enclosing function.  Emitted by
      `lower_lazy_lets` for every reference to a `[lazy]` local.
    * **Global-scope**: the stub is a static `Lazy$<T>` instance
      accessed as a `GlobalVar`.  Selected at `generate` time when
      `resolver.find_data` reports `ResolvedScope.GLOBAL`.
    * **Captured** (`captured_class` set): the reference is inside a
      lifted lambda body and the stub is held in `this.<stub_name>`
      on the closure class.  Set by `lambdas.__redirect_references_to_class`
      after the lambdas pass discovers the lazy reference as a free
      variable inside the body.
    """
    stub_name: str
    target_type: t.TypeSpec
    captured_class: str | None = None

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        return self.target_type

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement]]:
        # lower_lazy_lets runs after the compile loop has converged, so
        # there's nothing left for LazyExpression to compile.
        return self, []

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        return []

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,Any],Any]) -> Expression:
        return cast(Expression, replace(resolver, dataclasses.replace(self,
            target_type=self.target_type.search_and_replace(resolver, replace))))

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        import lowering.lazy_thunks as lt
        ir_t = self.target_type.generate(resolver)
        # `_ir_mangle` raises NotImplementedError for unsupported IR types.
        lt._ir_mangle(ir_t)

        stub_ref: cg_p.RParam
        if self.captured_class is not None:
            # Inside a lifted lambda — the stub was captured as a field
            # on the closure class.  `this` is the closure instance.
            this_var = cg_p.StackVar(cg_t.DataPointer(), "this")
            stub_ref = cg_p.ObjectField(cg_t.DataPointer(), this_var,
                                        self.captured_class, self.stub_name, None)
        else:
            # Pick GlobalVar vs StackVar based on the resolved scope so
            # the same LazyExpression node works for both `[lazy]` locals
            # and `[lazy]` globals.
            found = resolver.find_data(self.stub_name)
            if found and len(found) == 1 and found[0].scope == g.ResolvedScope.GLOBAL:
                stub_ref = cg_p.GlobalVar(cg_t.DataPointer(), self.stub_name)
            else:
                stub_ref = cg_p.StackVar(cg_t.DataPointer(), self.stub_name)

        sv_result = cg_p.StackVar(ir_t, "$force_result")
        # The fetch function takes `this` as its single parameter, which —
        # under the YAFL ABI — comes from the GlobalFunction's `.object`
        # field (the implicit self).  No additional struct args.
        # async_lower wraps the register to wrap_return_type(ir_t) and
        # inserts the IS_TASK + unwrap dance automatically.
        call = cg_o.Call(
            function=cg_p.GlobalFunction(lt.fetch_function_name(ir_t), stub_ref),
            parameters=cg_p.NewStruct(()),
            register=sv_result,
        )
        return g.OperationBundle(
            stack_vars=(sv_result,),
            operations=(call,),
            result_var=sv_result,
        )



