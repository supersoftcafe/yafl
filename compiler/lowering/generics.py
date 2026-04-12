from __future__ import annotations

import dataclasses
from typing import Callable

import pyast.statement as s
import pyast.expression as e

import pyast.resolver as g
import pyast.typespec as t

from langtools import cast
from pyast.statement import ImportGroup


def __create_unique_name(base_name: str, type_args: tuple[t.TypeSpec, ...]) -> str:
    """Create a unique mangled name for a monomorphized generic."""
    if not type_args:
        return base_name

    # Generate type signature string
    type_sig = "_".join(tp.as_unique_id_str() or "unknown" for tp in type_args)
    return f"{base_name}$generic${type_sig}"


def __is_concrete_type_args(type_args: tuple[t.TypeSpec, ...]) -> bool:
    """Check if all type arguments are concrete (not GenericPlaceholderSpec)."""
    return all(not isinstance(tp, t.GenericPlaceholderSpec) for tp in type_args)


def __find_concrete_instantiations(
    statements: list[s.Statement]
) -> tuple[set[tuple[str, tuple[t.TypeSpec, ...]]], set[tuple[str, tuple[t.TypeSpec, ...]]]]:
    """
    Find all concrete instantiations of generics.
    Returns (data_references, type_references) as sets of (name, type_args).
    Only includes instantiations where type_args are concrete (not GenericPlaceholderSpec).
    """
    data_refs: set[tuple[str, tuple[t.TypeSpec, ...]]] = set()
    type_refs: set[tuple[str, tuple[t.TypeSpec, ...]]] = set()

    def find_instantiations(resolver: g.Resolver, thing):
        # Find NamedExpression with concrete type_params (e.g., doNothing<Int>(x))
        if isinstance(thing, e.NamedExpression) and thing.type_params:
            if __is_concrete_type_args(thing.type_params):
                data_refs.add((thing.name, thing.type_params))

        # Find ClassSpec with concrete type_params (e.g., List<Int>)
        if isinstance(thing, t.ClassSpec) and thing.type_params:
            if __is_concrete_type_args(thing.type_params):
                type_refs.add((thing.name, thing.type_params))

        return thing

    # Scan all statements for concrete generic instantiations
    for stmt in statements:
        stmt.search_and_replace(g.ResolverRoot([]), find_instantiations)

    return data_refs, type_refs


def __substitute_type_params(
    node: s.Statement | e.Expression | t.TypeSpec,
    type_param_map: dict[t.TypeSpec, t.TypeSpec]
) -> s.Statement | e.Expression | t.TypeSpec:
    """Replace generic type parameters with concrete types throughout a node."""

    def substitute(resolver: g.Resolver, thing):
        # Replace GenericPlaceholderSpec with concrete type
        if isinstance(thing, t.GenericPlaceholderSpec):
            return type_param_map.get(thing, thing)
        return thing

    # Use search_and_replace to recursively substitute throughout the tree
    return node.search_and_replace(g.ResolverRoot([]), substitute)


def __create_specialized_version(
    stmt: s.NamedStatement,
    type_args: tuple[t.TypeSpec, ...]
) -> s.NamedStatement:
    """Create a concrete specialized version of a generic statement with specific type arguments."""

    if not stmt.type_params or not type_args:
        return stmt

    # Build mapping from type parameter names to concrete types
    type_param_map: dict[t.TypeSpec, t.TypeSpec] = {}
    for type_param, type_arg in zip(stmt.type_params, type_args):
        type_param_map[type_param.get_type()] = type_arg

    # Create new unique name
    new_name = __create_unique_name(stmt.name, type_args)

    # Substitute type parameters in the statement body
    new_stmt = __substitute_type_params(stmt, type_param_map)

    # Remove type_params from the specialized version and update name
    new_stmt = dataclasses.replace(
        new_stmt,
        name=new_name,
        type_params=()  # Specialized versions have no type params
    )

    return cast(s.NamedStatement, new_stmt)


def __create_specialized_statements(
    statements: list[s.Statement],
    data_refs: set[tuple[str, tuple[t.TypeSpec, ...]]],
    type_refs: set[tuple[str, tuple[t.TypeSpec, ...]]]
) -> list[s.Statement]:
    """
    Create specialized versions for all NamedStatements that match the concrete instantiations.
    Keep original generic statements (they'll be pruned later).
    """
    specialized: list[s.Statement] = []
    all_refs = sorted(data_refs | type_refs, key=lambda item: (item[0], tuple(tp.as_unique_id_str() or "" for tp in item[1])))

    for stmt in statements:
        if isinstance(stmt, s.NamedStatement) and stmt.type_params:
            # Find all concrete instantiations for this generic
            for n, type_args in all_refs:
                if n == stmt.name:
                    specialized_stmt = __create_specialized_version(stmt, type_args)
                    specialized.append(specialized_stmt)

    return specialized


def __replace_concrete_references(
    statements: list[s.Statement],
    data_refs: set[tuple[str, tuple[t.TypeSpec, ...]]],
    type_refs: set[tuple[str, tuple[t.TypeSpec, ...]]]
) -> list[s.Statement]:
    """Replace all concrete generic references with references to specialized versions."""

    def redirect_reference(resolver: g.Resolver, thing):
        # Redirect NamedExpression with concrete type_params to specialized name
        if isinstance(thing, e.NamedExpression) and thing.type_params:
            if __is_concrete_type_args(thing.type_params):
                if (thing.name, thing.type_params) in data_refs:
                    new_name = __create_unique_name(thing.name, thing.type_params)
                    return dataclasses.replace(thing, name=new_name, type_params=())

        # Redirect ClassSpec with concrete type_params to specialized name
        if isinstance(thing, t.ClassSpec) and thing.type_params:
            if __is_concrete_type_args(thing.type_params):
                if (thing.name, thing.type_params) in type_refs:
                    new_name = __create_unique_name(thing.name, thing.type_params)
                    return dataclasses.replace(thing, name=new_name, type_params=())

        return thing

    return [stmt.search_and_replace(g.ResolverRoot([]), redirect_reference) for stmt in statements]


def __prune_unused_generics(statements: list[s.Statement]) -> list[s.Statement]:
    """Remove generic statements that still have type_params (never instantiated with concrete types)."""
    return [stmt for stmt in statements if not (isinstance(stmt, s.NamedStatement) and stmt.type_params)]


def __convert_generics_iterative(statements: list[s.Statement]) -> list[s.Statement]:
    """
    Iteratively convert generics to concrete specialized versions.
    Keeps iterating until no new specialized statements are created.
    """
    while True:
        # Step 1: Find all concrete instantiations
        data_refs, type_refs = __find_concrete_instantiations(statements)

        if not data_refs and not type_refs:
            # No concrete instantiations found - we're done iterating
            break

        # Step 2: Create specialized versions for matching NamedStatements
        specialized = __create_specialized_statements(statements, data_refs, type_refs)

        if not specialized:
            # No new specialized statements created - we're done iterating
            break

        # Step 3: Replace concrete references with specialized names in ALL statements
        # (including newly specialized ones) so that the next iteration doesn't
        # re-discover the same concrete instantiations and create duplicates.
        statements = __replace_concrete_references(statements + specialized, data_refs, type_refs)

    # After iterations are stable, prune unused generics
    statements = __prune_unused_generics(statements)

    return statements


def __resolve_trait_references(statements: list[s.Statement]) -> list[s.Statement]:
    """
    After monomorphization, replace TRAIT-scope function references with DotExpressions
    on the concrete [trait] provider instance.

    When a specialized function like testIt$generic$Int has a `where Add<Int>` clause,
    calls to `+` inside the body resolve to TRAIT scope via _find_trait_data.  This
    pass finds the [trait] let statement whose declared type is assignment-compatible
    with the required trait spec (e.g. AddInt implements Add<Int>) and rewrites the
    NamedExpression as DotExpression(provider, method), so codegen sees a normal
    method call.  discover_global_function_calls then optimises the vtable dispatch to
    a direct call where only one implementation exists.
    """
    resolver = g.ResolverRoot(statements)
    traits = resolver.get_traits()

    def implements_trait(tr: s.LetStatement, trait_spec: t.ClassSpec) -> bool:
        if not isinstance(tr.declared_type, t.ClassSpec):
            return False
        classes = resolver.find_type({tr.declared_type.name})
        if len(classes) != 1 or not isinstance(classes[0].statement, s.ClassStatement):
            return False
        cls = classes[0].statement
        if cls._all_parents is None:
            return False
        return any(isinstance(p, t.ClassSpec) and p.name == trait_spec.name
                   and (not trait_spec.type_params or p.type_params == trait_spec.type_params)
                   for p in cls._all_parents)

    def redirect(r: g.Resolver, thing):
        if not isinstance(thing, e.NamedExpression):
            return thing

        # Use the trait_scope recorded during compilation if available, otherwise derive it.
        if thing.resolved_trait_scope is not None:
            trait_spec = thing.resolved_trait_scope
        else:
            datas = r.find_data({thing.name})
            if len(datas) != 1 or datas[0].scope != g.ResolvedScope.TRAIT:
                return thing
            trait_spec = datas[0].trait_scope
            if not isinstance(trait_spec, t.ClassSpec):
                return thing

        providers = [tr for tr in traits if implements_trait(tr, trait_spec)]
        if len(providers) != 1:
            return thing

        provider = providers[0]
        provider_type = provider.declared_type
        if not isinstance(provider_type, t.ClassSpec):
            return thing

        provider_classes = r.find_type({provider_type.name})
        if len(provider_classes) != 1:
            return thing
        provider_class = provider_classes[0].statement
        if not isinstance(provider_class, s.ClassStatement):
            return thing

        # Find the concrete method on the provider class by simple name
        simple = g.simple_name(thing.name)
        method_datas = provider_class.find_data(r, {simple})
        if not method_datas:
            return thing

        if len(method_datas) > 1:
            # Multiple overloads — disambiguate by comparing the concrete type of
            # the interface method (looked up by exact hash) against class methods.
            iface_classes = r.find_type({trait_spec.name})
            if len(iface_classes) == 1 and isinstance(iface_classes[0].statement, s.ClassStatement):
                iface_cls = iface_classes[0].statement
                iface_mds = iface_cls.find_data(r, {thing.name})
                if len(iface_mds) == 1 and isinstance(iface_mds[0].statement, s.FunctionStatement):
                    iface_type = iface_mds[0].statement.get_type()
                    if iface_type is not None:
                        if iface_cls.type_params and trait_spec.type_params:
                            mapping = {p.name: c for p, c in zip(iface_cls.type_params, trait_spec.type_params)}
                            def sub(_, node, m=mapping):
                                if isinstance(node, t.GenericPlaceholderSpec) and node.name in m:
                                    return m[node.name]
                                return node
                            iface_type = iface_type.search_and_replace(r, sub)
                        matching = [md for md in method_datas
                                    if t.trivially_assignable_equals(r, iface_type, md.statement.get_type())]
                        if len(matching) == 1:
                            method_datas = matching

        if len(method_datas) != 1:
            return thing

        provider_expr = e.NamedExpression(thing.line_ref, provider.name)
        return e.DotExpression(thing.line_ref, provider_expr, method_datas[0].unique_name)

    return [stmt.search_and_replace(resolver, redirect) for stmt in statements]


def convert_generic_to_concrete(statements: list[s.Statement]) -> list[s.Statement]:
    """
    Monomorphization pass: Convert generic statements to concrete specialized versions.

    This lowering pass:
    1. Finds all concrete instantiations of generic functions/classes (where type_params are not GenericPlaceholderSpec)
    2. Creates specialized versions of generic statements for each unique concrete type argument combination
    3. Replaces all concrete references to generics with references to specialized versions
    4. Iterates until stable (handles nested/transitive generic instantiations)
    5. Prunes unused generic definitions after iteration completes

    Example:
        fun doNothing<T>(x: T): T = x
        let a = doNothing<Int>(42)
        let b = doNothing<String>("hi")

    Becomes:
        fun doNothing$generic$int32(x: int32): int32 = x
        fun doNothing$generic$str(x: str): str = x
        let a = doNothing$generic$int32(42)
        let b = doNothing$generic$str("hi")

    Handles transitive generics:
        fun wrapper<T>(x: T): T = helper<T>(x)
        fun helper<T>(x: T): T = x
        let a = wrapper<Int>(42)

    First iteration finds wrapper<Int>, creates wrapper$generic$int32.
    Inside wrapper$generic$int32, helper<Int> is now concrete (T was replaced with Int).
    Second iteration finds helper<Int>, creates helper$generic$int32.
    Third iteration finds no new instantiations, prunes original generics.
    """
    converted = __convert_generics_iterative(statements)
    resolved = __resolve_trait_references(converted)
    return resolved
