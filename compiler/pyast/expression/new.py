from __future__ import annotations

from typing import Callable, Any
import dataclasses
import pyast.rewrite as rw
from dataclasses import dataclass, field
from functools import reduce

from langtools import checked_cast
from parsing.tokenizer import LineRef
from parsing.parselib import Error

import codegen.ops as cg_o
import codegen.param as cg_p
import codegen.typedecl as cg_t

import pyast.resolver as g
import pyast.statement as s
import pyast.typespec as t
import pyast.utils as u
from pyast import union_repr
from pyast.expression.base import Expression


@dataclass
class NewExpression(Expression):
    type: t.TypeSpec
    parameter: Expression

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,Any],Any]) -> Expression:
        return rw.rewrite(self, replace, resolver,
            type=self.type.search_and_replace(resolver, replace),
            parameter=self.parameter.search_and_replace(resolver, replace))

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
        xtype = checked_cast(t.TupleSpec, self.parameter.get_type(resolver))
        ctype = checked_cast(t.ClassSpec, self.type)
        found = resolver.find_type(ctype.name)
        if len(found) != 1:
            resolver.find_type(ctype.name)
            raise AssertionError(f"Failed to resolve {ctype.name}")
        classstmt = checked_cast(s.ClassStatement, found[0].statement)

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
               + tuple(cg_o.Move(cg_p.ObjectField(x.get_type().generate(resolver), result_var, cname, x.name, None, fresh=True), cg_p.StructField(params_var, f"_{index}")) for index, x in enumerate(fields))
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
        af_spec = checked_cast(t.ArrayFieldSpec, array_param.declared_type)
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
                cg_p.ObjectField(p.get_type().generate(resolver), result_var, cname, p.name, None, fresh=True),
                cg_p.StructField(params_var, f"_{i}")))

        # Fill loop: i = 0; while i < length { array[i] = init_fn(i); i = i + 1 }.
        # SSA-shaped — the counter is a head Phi over the entry value (0) and the
        # back-edge value (i+1); both labels live in this one bundle so codegen's
        # jump↔label pairing keeps them matched under the caller's prefixing.
        i_var = cg_p.StackVar(cg_t.Int(32), "filli")
        i_next = cg_p.StackVar(cg_t.Int(32), "fillinext")
        elem_var = cg_p.StackVar(elem_ctype, "fillelem")
        entry, head, body, back, end = "fillentry", "fillhead", "fillbody", "fillback", "fillend"
        less = cg_p.RuntimeInvoke("int32_test_lt", cg_p.NewStruct((("a", i_var), ("b", length))), cg_t.Int(8))
        incr = cg_p.RuntimeInvoke("int32_add", cg_p.NewStruct((("a", i_var), ("b", cg_p.Integer(1, 32)))), cg_t.Int(32))
        ops += [
            cg_o.Label(entry),
            cg_o.Label(head),
            cg_o.Phi(target=i_var, sources=((entry, cg_p.Integer(0, 32)), (back, i_next))),
            cg_o.JumpIf(body, less),
            cg_o.Jump(end),
            cg_o.Label(body),
            cg_o.Call(init_fn, cg_p.NewStruct((("_0", i_var),)), elem_var),
            # fresh: each element is written exactly once and its prior value is the
            # allocator's NULL — the SATB deletion barrier is provably a no-op.
            cg_o.Move(cg_p.ObjectField(elem_ctype, result_var, cname, "array", i_var, fresh=True), elem_var),
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
            spec = types[0].statement._enum_spec
            if spec is None:
                return None
            # A construction builds exactly one variant, so its TYPE is the
            # LEAF (USER RULING 2026-08-24). Representation is unchanged —
            # the value carries the root's struct — this is type-system only.
            if self.leaf_name in spec.all_leaf_names:
                return dataclasses.replace(
                    spec, valid_leaf_names=frozenset({self.leaf_name}))
            return spec
        return None

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement]]:
        # Thread each construction argument's declared FIELD type down — the
        # argument node owns any boxing toward it (a union-typed field takes a
        # narrow argument). Mirrors the field lookup construct_enum_value
        # performs when emitting.
        by_name: dict[str, t.TypeSpec | None] = {}
        types = resolver.find_type(self.root_spec_name)
        if len(types) == 1 and isinstance(types[0].statement, s.EnumStatement):
            root_stmt = types[0].statement
            root_spec = root_stmt._enum_spec
            if root_spec is not None and self.leaf_name in root_spec.all_leaf_names:
                leaf_idx = root_spec.all_leaf_names.index(self.leaf_name)
                leaf_fields = t._collect_leaf_field_sets(root_stmt, [])[leaf_idx]
                by_name = {let.name: let.declared_type for let in leaf_fields}
        new_field_args: dict[str, Expression] = {}
        all_stmts: list[s.Statement] = []
        for fname, fexpr in self.field_args.items():
            new_fexpr, stmts = fexpr.compile(resolver, by_name.get(fname))
            new_field_args[fname] = new_fexpr
            all_stmts.extend(stmts)
        expr = dataclasses.replace(self, field_args=new_field_args)
        # The constructed enum value owns its conversion to the receiver — an
        # enum member boxing into a union that contains it (`JsonParseError`
        # into `State | JsonParseError`).
        from pyast.expression.conversion import converted
        return converted(expr, expected_type, resolver), all_stmts

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        errors: list[Error] = []
        for fname, fexpr in self.field_args.items():
            errors += fexpr.check(resolver, None)
        return errors

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver, Any], Any]) -> Expression:
        fa_out, fa_changed = {}, False
        for k, v in self.field_args.items():
            r = v.search_and_replace(resolver, replace)
            fa_out[k] = v if r is rw.UNCHANGED else r
            fa_changed = fa_changed or r is not rw.UNCHANGED
        return rw.rewrite(self, replace, resolver,
            field_args=(fa_out if fa_changed else rw.UNCHANGED),
            type_params=rw.seq(self.type_params, resolver, replace))

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        types = resolver.find_type(self.root_spec_name)
        assert len(types) == 1
        root_stmt = checked_cast(s.EnumStatement, types[0].statement)
        root_spec = root_stmt._enum_spec
        assert root_spec is not None
        # The repr (complex enum -> heap object; flat enum -> tagged struct)
        # owns the construction; it generates the field-arg expressions in its
        # own order, so the emitted C stays byte-identical.
        return union_repr.classify(root_spec, resolver).construct_enum_value(
            self.leaf_name, self.field_args, resolver)

