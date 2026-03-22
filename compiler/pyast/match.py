"""MatchArm and MatchExpression — pattern matching on union types."""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from functools import reduce
from typing import Callable

from langtools import cast
from parsing.tokenizer import LineRef
from parsing.parselib import Error

import codegen.ops as cg_o
import codegen.param as cg_p
import codegen.typedecl as cg_t

import pyast.expression as e
import pyast.resolver as g
import pyast.statement as s
import pyast.typespec as t


@dataclass
class MatchArm:
    """One arm of a match expression."""
    line_ref: LineRef
    name: str | None         # Bound variable name; None for else arm, "_" to discard
    type_spec: t.TypeSpec | None  # Variant type; None for else arm
    body: e.Expression

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver, any], any]) -> MatchArm:
        nested_resolver = g.ResolverData(resolver, self.__find_bound) if self.name and self.name != "_" else resolver
        new_body = self.body.search_and_replace(nested_resolver, replace)
        new_type = self.type_spec.search_and_replace(resolver, replace) if self.type_spec else None
        return dataclasses.replace(self, type_spec=new_type, body=new_body)

    def __find_bound(self, names: set[str]) -> list[g.Resolved[s.DataStatement]]:
        if self.name and self.name != "_" and self.type_spec and g.match_names(self.name, names):
            let = s.LetStatement(self.line_ref, self.name, None, {}, (), None, self.type_spec)
            return [g.Resolved(self.name, let, g.ResolvedScope.LOCAL)]
        return []

    def compile(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> MatchArm:
        nested_resolver = g.ResolverData(resolver, self.__find_bound) if self.name and self.name != "_" else resolver
        new_body, _ = self.body.compile(nested_resolver, func_ret_type)
        new_type, _ = self.type_spec.compile(resolver) if self.type_spec else (None, [])
        return dataclasses.replace(self, type_spec=new_type, body=new_body)

    def check(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> list:
        nested_resolver = g.ResolverData(resolver, self.__find_bound) if self.name and self.name != "_" else resolver
        type_err = self.type_spec.check(resolver) if self.type_spec else []
        body_err = self.body.check(nested_resolver, func_ret_type)
        return type_err + body_err


@dataclass
class MatchExpression(e.Expression):
    """match subject\n    arm*"""
    subject: e.Expression
    arms: list[MatchArm]

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver, any], any]) -> e.Expression:
        return cast(e.Expression, replace(resolver, dataclasses.replace(self,
            subject=self.subject.search_and_replace(resolver, replace),
            arms=[arm.search_and_replace(resolver, replace) for arm in self.arms])))

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        for arm in self.arms:
            t_arm = arm.body.get_type(resolver)
            if t_arm is not None:
                return t_arm
        return None

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[e.Expression, list[s.Statement]]:
        new_subject, subj_stmts = self.subject.compile(resolver, None)
        new_arms = [arm.compile(resolver, expected_type) for arm in self.arms]
        return dataclasses.replace(self, subject=new_subject, arms=new_arms), subj_stmts

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list:
        subj_type = self.subject.get_type(resolver)
        if subj_type is None:
            return []  # Not ready
        if not isinstance(subj_type, t.CombinationSpec):
            return [Error(self.line_ref, "match subject must be a union type")]
        errors = []
        for arm in self.arms:
            errors += arm.check(resolver, expected_type)
        return errors

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        subj_bundle = self.subject.generate(resolver).rename_vars("s")
        subj_type = self.subject.get_type(resolver)
        assert isinstance(subj_type, t.CombinationSpec)
        target_ctype = subj_type.generate()
        result_type = self.get_type(resolver)
        result_var = cg_p.StackVar(result_type.generate(), "result") if result_type else None

        discriminators = resolver.get_discriminators()

        # DataPointer union: null check for unit variant, pass through for pointer
        if isinstance(target_ctype, cg_t.DataPointer):
            return self.__gen_pointer_match(resolver, subj_bundle, subj_type, result_var, discriminators)

        # UnionContainer: tag comparison
        assert isinstance(target_ctype, cg_t.UnionContainer)
        return self.__gen_tagged_match(resolver, subj_bundle, subj_type, target_ctype, result_var, discriminators)

    def __emit_arm_body(self, arm: MatchArm, arm_resolver: g.Resolver, suffix: str,
                        result_var: cg_p.StackVar | None, bundles: list) -> None:
        """Generate arm body, append it to bundles, and store its result into result_var if present."""
        body_bundle = arm.body.generate(arm_resolver).rename_vars(suffix)
        bundles.append(body_bundle)
        if result_var:
            bundles.append(g.OperationBundle(operations=(cg_o.Move(result_var, body_bundle.result_var),)))

    def __bind_arm_var(self, arm: MatchArm, arm_ctype, slot_assignments, slot_fields,
                       sv: cg_p.RParam, resolver: g.Resolver, bundles: list) -> g.Resolver:
        """Emit ops to bind arm.name to the matched variant value; return the extended resolver.

        slot_assignments is variant_map[var_idx]: a list of (slot_index, orig_type) pairs,
        one per primitive in this variant.  For a single-primitive variant the bound variable
        is loaded from its one union slot.  For a multi-primitive (struct) variant each field
        is loaded from its corresponding slot and the struct is reconstructed with NewStruct.
        """
        def make_resolver(arm_=arm):
            def find(names):
                if g.match_names(arm_.name, names):
                    let = s.LetStatement(arm_.line_ref, arm_.name, None, {}, (), None, arm_.type_spec)
                    return [g.Resolved(arm_.name, let, g.ResolvedScope.LOCAL)]
                return []
            return g.ResolverData(resolver, find)

        prims = cg_t._flatten_primitives(arm_ctype)
        arm_sv = cg_p.StackVar(arm_ctype, arm.name)

        if len(prims) == 1:
            si, _ = slot_assignments[0]
            slot_value = cg_p.StructField(sv, slot_fields[si][0])
            if isinstance(arm_ctype, cg_t.Struct):
                field_name = arm_ctype.fields[0][0]
                arm_value = cg_p.NewStruct(((field_name, slot_value),))
            else:
                arm_value = slot_value
            bundles.append(g.OperationBundle(stack_vars=(arm_sv,),
                                             operations=(cg_o.Move(arm_sv, arm_value),)))
        else:
            assert isinstance(arm_ctype, cg_t.Struct), f"Multi-primitive non-struct arm type {arm_ctype}"
            field_values: list[tuple[str, cg_p.RParam]] = []
            for prim_idx, (field_name, field_type) in enumerate(arm_ctype.fields):
                assert len(cg_t._flatten_primitives(field_type)) == 1, \
                    f"Nested multi-primitive field in match arm not yet supported"
                si, _ = slot_assignments[prim_idx]
                field_values.append((field_name, cg_p.StructField(sv, slot_fields[si][0])))
            bundles.append(g.OperationBundle(stack_vars=(arm_sv,),
                                             operations=(cg_o.Move(arm_sv, cg_p.NewStruct(tuple(field_values))),)))
        return make_resolver()

    def __gen_pointer_match(self, resolver, subj_bundle, subj_type, result_var, discriminators):
        """DataPointer union: null = unit variant, non-null = pointer variant."""
        unit_type = cg_t.Struct(())
        else_arm = next((arm for arm in self.arms if arm.type_spec is None), None)
        null_arms = [arm for arm in self.arms if arm.type_spec is not None and arm.type_spec.generate() == unit_type]
        ptr_arms  = [arm for arm in self.arms if arm.type_spec is not None and arm.type_spec.generate() != unit_type]

        sv         = subj_bundle.result_var
        null_arm   = null_arms[0] if null_arms else else_arm
        ptr_arm    = ptr_arms[0]  if ptr_arms  else else_arm
        stack_vars = (result_var,) if result_var else ()
        null_label = "match_null"
        end_label  = "match_end"

        bundles = [subj_bundle,
                   g.OperationBundle(operations=(cg_o.JumpIf(null_label, cg_p.IntEqConst(sv, 0)),))]

        # Non-null (pointer) arm
        if ptr_arm:
            arm_resolver = resolver
            if ptr_arm.name and ptr_arm.name != "_":
                bound_sv = cg_p.StackVar(cg_t.DataPointer(), ptr_arm.name)
                def find_ptr(names, arm=ptr_arm):
                    if g.match_names(arm.name, names):
                        let = s.LetStatement(arm.line_ref, arm.name, None, {}, (), None, arm.type_spec)
                        return [g.Resolved(arm.name, let, g.ResolvedScope.LOCAL)]
                    return []
                arm_resolver = g.ResolverData(resolver, find_ptr)
                bundles.append(g.OperationBundle(stack_vars=(bound_sv,),
                                                 operations=(cg_o.Move(bound_sv, sv),)))
            self.__emit_arm_body(ptr_arm, arm_resolver, "pt", result_var, bundles)

        bundles.append(g.OperationBundle(operations=(cg_o.Jump(end_label), cg_o.Label(null_label))))

        # Null (unit) arm
        if null_arm:
            self.__emit_arm_body(null_arm, resolver, "nu", result_var, bundles)

        bundles.append(g.OperationBundle(stack_vars=stack_vars,
                                         operations=(cg_o.Label(end_label),), result_var=result_var))
        return reduce(lambda a, b: a + b, bundles).rename_vars("")

    def __gen_tagged_match(self, resolver, subj_bundle, subj_type, container, result_var, discriminators):
        """UnionContainer union: compare $tag for each arm."""
        sv         = subj_bundle.result_var
        tag_field  = cg_p.StructField(sv, "$tag")
        stack_vars = (result_var,) if result_var else ()
        end_label  = "match_end"

        variant_types = [v.generate() for v in subj_type.types]
        _, variant_map = cg_t.UnionContainer.compute(variant_types)
        slot_fields = container.slots

        bundles  = [subj_bundle]
        else_arm = next((arm for arm in self.arms if arm.type_spec is None), None)

        for i, arm in enumerate([arm for arm in self.arms if arm.type_spec is not None]):
            arm_ctype  = arm.type_spec.generate()
            tag_value  = discriminators.get(arm.type_spec.as_unique_id_str(), 0)
            arm_label  = f"match_arm_{i}"
            next_label = f"match_next_{i}"

            bundles.append(g.OperationBundle(operations=(cg_o.JumpIf(arm_label, cg_p.IntEqConst(tag_field, tag_value)),)))
            bundles.append(g.OperationBundle(operations=(cg_o.Jump(next_label),)))
            bundles.append(g.OperationBundle(operations=(cg_o.Label(arm_label),)))

            arm_local = []
            arm_resolver = resolver
            if arm.name and arm.name != "_":
                var_idx = next((idx for idx, vt in enumerate(variant_types) if vt == arm_ctype), None)
                if var_idx is not None:
                    arm_resolver = self.__bind_arm_var(
                        arm, arm_ctype, variant_map[var_idx], slot_fields, sv, resolver, arm_local)

            self.__emit_arm_body(arm, arm_resolver, f"a{i}", result_var, arm_local)
            if arm_local:
                bundles.append(reduce(lambda a, b: a + b, arm_local).rename_vars(f"arm{i}_"))
            bundles.append(g.OperationBundle(operations=(cg_o.Jump(end_label),)))
            bundles.append(g.OperationBundle(operations=(cg_o.Label(next_label),)))

        if else_arm:
            self.__emit_arm_body(else_arm, resolver, "el", result_var, bundles)

        bundles.append(g.OperationBundle(stack_vars=stack_vars,
                                         operations=(cg_o.Label(end_label),), result_var=result_var))
        return reduce(lambda a, b: a + b, bundles).rename_vars("")
