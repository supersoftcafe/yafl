"""Type declarations: `typealias` (also the compiler-internal type-param
declaration) and `enum`.
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

import pyast.resolver as g
import pyast.expression as e
import pyast.typespec as t

import pyast.utils as u

from pyast.statement.base import Statement, NamedStatement, TypeStatement, ImportGroup
from pyast.statement.lets import LetStatement, DestructureStatement


@dataclass
class TypeAliasStatement(TypeStatement):
    type: t.TypeSpec

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,Any],Any]) -> Statement:
        return rw.rewrite(self, replace, resolver,
            type=self.type.search_and_replace(resolver, replace))

    def get_type(self) -> t.TypeSpec|None:
        return self.type if self.type.is_concrete() else None

    def compile(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> tuple[Statement | None, list[Statement]]:
        # A generic `where`-alias (`typealias [where] _W<S,T> : Box<Wrap<S,T>,T>
        # where Box<S,T>`) binds S/T over both its body and its constraints.
        trts: list[t.TypeSpec] = list(self.trait_params)
        trts_glb: list[Statement] = []
        if self.type_params or self.trait_params:
            resolver = g.ResolverType(resolver, self._find_generic_types)
            trts, trts_glb = u.flatten_lists(tp.compile(resolver) for tp in self.trait_params)
        new_type, new_statements = self.type.compile(resolver)
        return dataclasses.replace(self, type=new_type, trait_params=tuple(trts)), new_statements + trts_glb

    def check(self, resolver: g.Resolver, func_ret_type: t.TypeSpec | None) -> list[Error]:
        if self.type_params or self.trait_params:
            resolver = g.ResolverType(resolver, self._find_generic_types)
        return self.type.check(resolver) + [e for x in self.trait_params for e in x.check(resolver)]


@dataclass
class EnumStatement(TypeStatement):
    parameters: DestructureStatement
    variants: list[EnumStatement]
    # Whether the declaration carried a constructor parameter list `(...)` (even
    # an empty `()`). A node with no variants and no parameter list is the empty
    # type: no constructor, no leaf — uninhabited (e.g. `enum Never`). The `()`
    # form is a constructible unit and keeps `has_param_list=True`.
    has_param_list: bool = True
    # Both derived during compile (the root's name threaded down to variants;
    # the computed EnumSpec cache) — metadata that settles iteratively, not
    # program identity, so excluded from the loop's convergence comparison.
    _root_name: str | None = field(default=None, compare=False)
    _enum_spec: t.EnumSpec | None = field(default=None, compare=False)

    def get_type(self) -> t.EnumSpec | None:
        return self._enum_spec

    def add_namespace(self, path: str):
        new_variants = [v.add_namespace(path) for v in self.variants]
        return dataclasses.replace(self, name=f"{path}{self.name}", variants=new_variants)

    def _collect_leaf_names(self) -> list[str]:
        if not self.variants:
            return [self.name] if self.has_param_list else []  # uninhabited → no leaf
        return [ln for v in self.variants for ln in v._collect_leaf_names()]

    def covering_fields(self, valid: frozenset[str]) -> list[tuple[str, t.TypeSpec]]:
        """The (unique-name, type) field pairs a value narrowed to the leaf set
        `valid` is GUARANTEED to carry: fields declared at nodes whose own leaf
        set covers every valid leaf. A field declared on one variant does not
        cover a sibling, so a read through it would be reading another
        variant's slot — the field-aliasing bug this method exists to close."""
        out: list[tuple[str, t.TypeSpec]] = []
        def walk(node: EnumStatement):
            if valid <= frozenset(node._collect_leaf_names()):
                for let in node.parameters.flatten():
                    if let.declared_type is not None:
                        out.append((let.name, let.declared_type))
            for v in node.variants:
                walk(v)
        walk(self)
        return out

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

    def global_codegen(self, resolver: g.Resolver) -> list[cg_ir.Object]:
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
        # EVERY boxed enum carries a hidden Int32 hash-cache slot DIRECTLY
        # AFTER the vtable pointer, in every leaf (and the never-instantiated
        # marker, documenting the shared prefix). The fixed offset —
        # sizeof(vtable_t*) — is what lets yafl_hash_peek/store exist once,
        # not per type; with GC_ALLOC_GRANULE at 32 the word is usually
        # absorbed by existing padding. A scalar: absent from pointer masks,
        # no barrier, and deliberately NOT [mutable] — a store lost to a
        # compaction move is a benign recompute, as string_t's lazy hash.
        prefix: tuple = (("type", cg_t.DataPointer()), ("$hash", cg_t.Int(32)))
        marker = cg_ir.Object(
            name=self.name,
            extends=(),
            functions=(),
            fields=cg_t.ImmediateStruct(prefix),
            comment=f"{self.name} — enum root marker (never instantiated)")
        objects = [marker]
        leaf_field_sets = t._collect_leaf_field_sets(self, [])
        for leaf_name, leaf_fields in zip(self._enum_spec.all_leaf_names, leaf_field_sets):
            obj_name = t.enum_leaf_object_name(self.name, leaf_name)
            fields = prefix + tuple(
                (let.name, let.declared_type.generate(resolver)) for let in leaf_fields)
            objects.append(cg_ir.Object(
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
        new_spec = rw.opt(self._enum_spec, resolver, replace)
        return rw.rewrite(self, replace, resolver,
            parameters=self.parameters.search_and_replace(variant_resolver, replace),
            variants=rw.seq(self.variants, variant_resolver, replace),
            _enum_spec=(new_spec if new_spec is rw.UNCHANGED or isinstance(new_spec, t.EnumSpec) else None))
