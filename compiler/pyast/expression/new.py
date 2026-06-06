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

        types = resolver.find_type(ctype.name)
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
        found = resolver.find_type(ctype.name)
        if len(found) != 1:
            resolver.find_type(ctype.name)
            raise AssertionError(f"Failed to resolve {ctype.name}")
        classstmt = cast(s.ClassStatement, found[0].statement)

        params_bundle = self.parameter.generate(resolver).with_prefix("args")
        params_var = cg_p.StackVar(xtype.generate(resolver), "params")
        result_var = cg_p.StackVar(ctype.generate(resolver), "result")
        cname = ctype.name

        array_param = classstmt.array_field(resolver)
        if array_param is not None:
            return params_bundle + self.__generate_array(
                resolver, classstmt, array_param, cname, params_var, params_bundle.result_var, result_var)

        fields = classstmt.get_fields(resolver)
        ops = ( ( cg_o.Move(params_var, params_bundle.result_var),
                  cg_o.NewObject(cname, result_var) )
               + tuple(cg_o.Move(cg_p.ObjectField(x.get_type().generate(resolver), result_var, cname, x.name, None), cg_p.StructField(params_var, f"_{index}")) for index, x in enumerate(fields))
        )

        constructor_bundle = g.OperationBundle(
            stack_vars=(params_var,result_var,),
            operations=ops,
            result_var=result_var,
        )

        return params_bundle + constructor_bundle

    def __generate_array(self, resolver: g.Resolver, classstmt: "s.ClassStatement",
                         array_param: "s.LetStatement", cname: str,
                         params_var: cg_p.StackVar, params_value: cg_p.RParam,
                         result_var: cg_p.StackVar) -> g.OperationBundle:
        """Construct an array class: allocate the trailing storage with
        `array_create(vtable, length)`, write the scalar fields, then tabulate the
        array by calling the init function `(Int32): Elem` for each index and
        storing the result. The fill loop is an SSA counter loop (entry edge →
        head Phi → back-edge). The argument tuple is positional in constructor-
        parameter order, so `params._i` matches `parameters.flatten()[i]`."""
        params = classstmt.parameters.flatten()
        af_spec = cast(t.ArrayFieldSpec, array_param.declared_type)
        elem_ctype = af_spec.element.generate(resolver)

        arr_idx = next(i for i, p in enumerate(params) if isinstance(p.declared_type, t.ArrayFieldSpec))
        len_idx = next(i for i, p in enumerate(params) if g.name_matches(p.name, af_spec.length_field))
        length = cg_p.StructField(params_var, f"_{len_idx}")
        init_fn = cg_p.StructField(params_var, f"_{arr_idx}")

        ops: list[cg_o.Op] = [
            cg_o.Move(params_var, params_value),
            cg_o.NewObject(cname, result_var, size=length),   # array_create(vtable, length)
        ]
        # Scalar fields (everything except the array field itself).
        for i, p in enumerate(params):
            if i == arr_idx:
                continue
            ops.append(cg_o.Move(
                cg_p.ObjectField(p.get_type().generate(resolver), result_var, cname, p.name, None),
                cg_p.StructField(params_var, f"_{i}")))

        # Fill loop: i = 0; while i < length { array[i] = init_fn(i); i = i + 1 }.
        # SSA-shaped — the counter is a head Phi over the entry value (0) and the
        # back-edge value (i+1); both labels live in this one bundle so codegen's
        # jump↔label pairing keeps them matched under the caller's prefixing.
        i_var = cg_p.StackVar(cg_t.Int(32), "filli")
        i_next = cg_p.StackVar(cg_t.Int(32), "fillinext")
        elem_var = cg_p.StackVar(elem_ctype, "fillelem")
        entry, head, body, back, end = "fillentry", "fillhead", "fillbody", "fillback", "fillend"
        less = cg_p.Invoke("int32_test_lt", cg_p.NewStruct((("a", i_var), ("b", length))), cg_t.Int(8))
        incr = cg_p.Invoke("int32_add", cg_p.NewStruct((("a", i_var), ("b", cg_p.Integer(1, 32)))), cg_t.Int(32))
        ops += [
            cg_o.Label(entry),
            cg_o.Label(head),
            cg_o.Phi(target=i_var, sources=((entry, cg_p.Integer(0, 32)), (back, i_next))),
            cg_o.JumpIf(body, less),
            cg_o.Jump(end),
            cg_o.Label(body),
            cg_o.Call(init_fn, cg_p.NewStruct((("_0", i_var),)), elem_var),
            cg_o.Move(cg_p.ObjectField(elem_ctype, result_var, cname, "array", i_var), elem_var),
            cg_o.Move(i_next, incr),
            cg_o.Label(back),
            cg_o.Jump(head),
            cg_o.Label(end),
        ]
        return g.OperationBundle(
            stack_vars=(params_var, result_var, i_var, i_next, elem_var),
            operations=tuple(ops),
            result_var=result_var)



@dataclass
class NewEnumExpression(Expression):
    root_spec_name: str
    leaf_name: str
    field_args: dict[str, Expression]
    type_params: tuple[t.TypeSpec, ...] = field(default_factory=tuple)

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        types = resolver.find_type(self.root_spec_name)
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
        new_type_params = tuple(tp.search_and_replace(resolver, replace) for tp in self.type_params)
        return cast(Expression, replace(resolver, dataclasses.replace(self, field_args=new_field_args, type_params=new_type_params)))

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        types = resolver.find_type(self.root_spec_name)
        assert len(types) == 1
        root_stmt = cast(s.EnumStatement, types[0].statement)
        root_spec = root_stmt._enum_spec
        assert root_spec is not None
        leaf_idx = root_spec.all_leaf_names.index(self.leaf_name)

        variant_types = t.enum_variant_types(root_stmt, resolver)
        container, variant_map = cg_t.compute_union_slots(variant_types)
        leaf_field_sets = t._collect_leaf_field_sets(root_stmt, [])
        leaf_fields = leaf_field_sets[leaf_idx]
        this_vm = variant_map[leaf_idx]
        tag_slot_name, tag_slot_type = container.fields[-1]  # $tag is always last
        tag_const = cg_p.Integer(leaf_idx, tag_slot_type.precision)

        if root_spec.is_complex:
            # Heap-allocated path: NewObject, write $tag and shared slots.
            result_var = cg_p.StackVar(cg_t.DataPointer(), "result")
            ops: list[cg_o.Op] = [
                cg_o.NewObject(root_spec.root_name, result_var),
                cg_o.Move(
                    cg_p.ObjectField(tag_slot_type, result_var, root_spec.root_name, tag_slot_name, None),
                    tag_const),
            ]
            # Zero-fill all non-$tag slots so unused pointer slots are null.
            for slot_name, slot_type in container.fields[:-1]:
                ops.append(cg_o.Move(
                    cg_p.ObjectField(slot_type, result_var, root_spec.root_name, slot_name, None),
                    cg_p.ZeroOf(slot_type)))
            def emit_heap(param, ftype, off):
                """Recursively write ftype primitives from param to heap object slots."""
                if isinstance(ftype, cg_t.Struct):
                    for fname, ft in ftype.fields:
                        off = emit_heap(cg_p.StructField(param, fname), ft, off)
                    return off
                si, _ = this_vm[off]
                slot_name, slot_type = container.fields[si]
                ops.append(cg_o.Move(
                    cg_p.ObjectField(slot_type, result_var, root_spec.root_name, slot_name, None),
                    param))
                return off + 1

            bundles: list[g.OperationBundle] = []
            prim_off = 0
            for let in leaf_fields:
                field_name = let.name
                field_type = let.declared_type.generate(resolver)
                n_prims = len(cg_t._flatten_primitives(field_type))
                if field_name in self.field_args:
                    arg_bundle = self.field_args[field_name].generate(resolver).with_prefix(f"arg_{field_name.split('@')[0]}")
                    bundles.append(arg_bundle)
                    emit_heap(arg_bundle.result_var, field_type, prim_off)
                prim_off += n_prims
            ctor_bundle = g.OperationBundle(
                stack_vars=(result_var,),
                operations=tuple(ops),
                result_var=result_var)
            if bundles:
                return reduce(lambda a, b: a + b, bundles + [ctor_bundle])
            return ctor_bundle

        # Non-recursive: flat by-value struct using the shared slot layout.
        # Map each field name to its starting primitive index within this leaf's flattened type.
        prim_start: dict[str, int] = {}
        offset = 0
        for let in leaf_fields:
            prim_start[let.name] = offset
            offset += len(cg_t._flatten_primitives(let.declared_type.generate(resolver)))

        # Start with zero for every slot, then fill $tag and each provided field.
        slot_values: list[tuple[str, cg_p.RParam]] = [
            (sname, cg_p.ZeroOf(stype)) for sname, stype in container.fields
        ]
        tag_slot_idx = next(i for i, (n, _) in enumerate(container.fields) if n == "$tag")
        slot_values[tag_slot_idx] = ("$tag", tag_const)

        bundles2: list[g.OperationBundle] = []
        for field_name, arg_expr in self.field_args.items():
            pi = prim_start[field_name]
            let = next(l for l in leaf_fields if l.name == field_name)
            field_type = let.declared_type.generate(resolver)
            n_prims = len(cg_t._flatten_primitives(field_type))
            arg_bundle = arg_expr.generate(resolver).with_prefix(f"arg_{field_name.split('@')[0]}")
            bundles2.append(arg_bundle)
            def emit_flat(param, ftype, off):
                """Recursively write ftype primitives from param to flat slot_values."""
                if isinstance(ftype, cg_t.Struct):
                    for fname, ft in ftype.fields:
                        off = emit_flat(cg_p.StructField(param, fname), ft, off)
                    return off
                si, _ = variant_map[leaf_idx][off]
                sname, _ = container.fields[si]
                slot_values[si] = (sname, param)
                return off + 1

            emit_flat(arg_bundle.result_var, field_type, pi)

        result_param = cg_p.union_struct(container, dict(slot_values))
        final_bundle = g.OperationBundle((), (), result_param)
        if bundles2:
            return reduce(lambda a, b: a + b, bundles2 + [final_bundle])
        return final_bundle

