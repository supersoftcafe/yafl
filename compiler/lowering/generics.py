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

        # Find NewEnumExpression with concrete type_params (e.g., DictEmpty<Int,Str>())
        if isinstance(thing, e.NewEnumExpression) and thing.type_params:
            if __is_concrete_type_args(thing.type_params):
                data_refs.add((thing.root_spec_name, thing.type_params))

        # Find ClassSpec with concrete type_params (e.g., List<Int>)
        if isinstance(thing, t.ClassSpec) and thing.type_params:
            if __is_concrete_type_args(thing.type_params):
                type_refs.add((thing.name, thing.type_params))

        # Find EnumSpec with concrete type_params (from return type annotations)
        if isinstance(thing, t.EnumSpec) and thing.type_params:
            if __is_concrete_type_args(thing.type_params):
                data_refs.add((thing.root_name, thing.type_params))

        # Find NamedSpec with concrete type_params (e.g., Dict<Int,Str> in type annotations)
        if isinstance(thing, t.NamedSpec) and thing.type_params:
            if __is_concrete_type_args(thing.type_params):
                data_refs.add((thing.name, thing.type_params))

        return thing

    # Scan all statements for concrete generic instantiations
    for stmt in statements:
        stmt.search_and_replace(g.ResolverRoot([]), find_instantiations)

    return data_refs, type_refs


def __substitute_type_params(
    node: s.Statement | e.Expression | t.TypeSpec,
    type_param_map: dict[t.TypeSpec, t.TypeSpec]
) -> s.Statement | e.Expression | t.TypeSpec:
    """Replace generic type parameters with concrete types throughout a node.

    Substitutes GenericPlaceholderSpec entries inside EnumSpec.all_fields too.
    EnumSpec.search_and_replace deliberately skips `all_fields` (to avoid
    infinite loops on self-referential enums), so those GPs aren't reachable
    through normal traversal. We do a bounded recursion here with a per-call
    visited set keyed by root_name. Match by bare placeholder name (before
    `@hash`) because the GP inside an enum's `all_fields` carries the *enum's*
    T scope hash while `type_param_map` is keyed by the *function's* T scope
    hash; both come from the same source-level identifier so a bare-name match
    is correct within a single specialization. Boxing's field-type lookups
    via `EnumSpec.all_fields` need these to be concrete.
    """
    name_map: dict[str, t.TypeSpec] = {}
    for k, v in type_param_map.items():
        if isinstance(k, t.GenericPlaceholderSpec):
            bare = k.name.rpartition("@")[0] or k.name
            name_map[bare] = v

    def _resolve_gp(gp: t.GenericPlaceholderSpec) -> t.TypeSpec:
        direct = type_param_map.get(gp)
        if direct is not None:
            return direct
        bare = gp.name.rpartition("@")[0] or gp.name
        return name_map.get(bare, gp)

    def _fields_changed(new_fields, old_fields) -> bool:
        # EnumSpec.__eq__ excludes all_fields, so a tuple of (name, EnumSpec)
        # compares equal even when all_fields differ. Use identity.
        if len(new_fields) != len(old_fields):
            return True
        return any(nv is not ov for (_, nv), (_, ov) in zip(new_fields, old_fields))

    def _substitute_in_field(ft: t.TypeSpec, visited: frozenset[str]) -> t.TypeSpec:
        if isinstance(ft, t.GenericPlaceholderSpec):
            return _resolve_gp(ft)
        if isinstance(ft, t.NamedSpec) and ft.type_params:
            new_tp = tuple(_substitute_in_field(tp, visited) for tp in ft.type_params)
            if any(n is not o for n, o in zip(new_tp, ft.type_params)):
                if __is_concrete_type_args(new_tp):
                    # Inline the redirect: NamedSpec.search_and_replace doesn't
                    # reach inside an EnumSpec's all_fields, so the redirect
                    # pass would miss this and leave a non-redirected NamedSpec.
                    new_name = __create_unique_name(ft.name, new_tp)
                    return dataclasses.replace(ft, name=new_name, type_params=())
                return dataclasses.replace(ft, type_params=new_tp)
        elif isinstance(ft, t.EnumSpec) and ft.root_name not in visited:
            new_visited = visited | {ft.root_name}
            new_fields = tuple((n, _substitute_in_field(f, new_visited)) for n, f in ft.all_fields)
            if _fields_changed(new_fields, ft.all_fields):
                return dataclasses.replace(ft, all_fields=new_fields)
        return ft

    def substitute(resolver: g.Resolver, thing):
        if isinstance(thing, t.GenericPlaceholderSpec):
            return _resolve_gp(thing)
        if isinstance(thing, t.EnumSpec):
            new_fields = tuple((n, _substitute_in_field(f, frozenset({thing.root_name})))
                               for n, f in thing.all_fields)
            if _fields_changed(new_fields, thing.all_fields):
                return dataclasses.replace(thing, all_fields=new_fields)
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


def __rebuild_enum_spec(stmt: s.EnumStatement) -> s.EnumStatement:
    """Rebuild _enum_spec for a specialized EnumStatement from its (now-concrete) variants."""
    root_name = stmt.name
    tag_field: tuple[str, t.TypeSpec] = ("$tag", t.BuiltinSpec(stmt.line_ref, "int32"))
    all_leaf_names = tuple(stmt._collect_leaf_names())
    data_fields = stmt._collect_data_fields()
    all_fields = (tag_field,) + tuple(data_fields)
    final_variants = [v._assign_specs(root_name, all_leaf_names, all_fields) for v in stmt.variants]
    my_leaves = frozenset(all_leaf_names)
    my_spec = t.EnumSpec(stmt.line_ref, root_name, my_leaves, all_leaf_names, all_fields)
    return dataclasses.replace(stmt, variants=final_variants, _root_name=root_name, _enum_spec=my_spec)


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
    existing_names = {stmt.name for stmt in statements}

    for stmt in statements:
        if isinstance(stmt, s.NamedStatement) and stmt.type_params:
            # Find all concrete instantiations for this generic
            for n, type_args in all_refs:
                if n == stmt.name:
                    new_name = __create_unique_name(stmt.name, type_args)
                    if new_name in existing_names:
                        continue  # already specialized in a prior iteration
                    specialized_stmt = __create_specialized_version(stmt, type_args)
                    # For enum statements, rebuild _enum_spec from the substituted variants
                    # (substitution updates variant parameters but not the cached _enum_spec).
                    if isinstance(specialized_stmt, s.EnumStatement):
                        specialized_stmt = __rebuild_enum_spec(specialized_stmt)
                    specialized.append(specialized_stmt)
                    existing_names.add(new_name)  # prevent duplicate in the same iteration

    return specialized


def __replace_concrete_references(
    statements: list[s.Statement],
    data_refs: set[tuple[str, tuple[t.TypeSpec, ...]]],
    type_refs: set[tuple[str, tuple[t.TypeSpec, ...]]]
) -> list[s.Statement]:
    """Replace all concrete generic references with references to specialized versions.

    The five node kinds that carry `type_params` (NamedExpression, NewEnumExpression,
    ClassSpec, EnumSpec, NamedSpec) all redirect identically: if the (current_name,
    type_params) tuple appears in the right refs set, replace current_name with the
    mangled specialised name and clear type_params. Only EnumSpec also propagates
    the rename into its leaf-name fields. The dispatch table below encodes those
    five rules and the helper applies them uniformly.
    """
    # (matcher class, name attribute, refs source, extra-field rewrites)
    redirect_table: tuple = (
        (e.NamedExpression,    "name",           data_refs, ()),
        (e.NewEnumExpression,  "root_spec_name", data_refs, ()),
        (t.ClassSpec,          "name",           type_refs, ()),
        (t.EnumSpec,           "root_name",      data_refs, (
            ("valid_leaf_names", lambda v, tp: frozenset(__create_unique_name(ln, tp) for ln in v)),
            ("all_leaf_names",   lambda v, tp: tuple(__create_unique_name(ln, tp) for ln in v)),
        )),
        (t.NamedSpec,          "name",           data_refs, ()),
    )

    def maybe_redirect(thing, name_attr, refs, extras):
        if not thing.type_params or not __is_concrete_type_args(thing.type_params):
            return None
        current_name = getattr(thing, name_attr)
        if (current_name, thing.type_params) not in refs:
            return None
        new_name = __create_unique_name(current_name, thing.type_params)
        new_fields = {name_attr: new_name, "type_params": ()}
        for attr, rewrite in extras:
            new_fields[attr] = rewrite(getattr(thing, attr), thing.type_params)
        return dataclasses.replace(thing, **new_fields)

    def redirect_reference(resolver: g.Resolver, thing):
        for cls, name_attr, refs, extras in redirect_table:
            if isinstance(thing, cls):
                replacement = maybe_redirect(thing, name_attr, refs, extras)
                if replacement is not None:
                    return replacement
                break  # matched class but no redirect — no other rule applies
        return thing

    return [stmt.search_and_replace(g.ResolverRoot([]), redirect_reference) for stmt in statements]


def __prune_unused_generics(statements: list[s.Statement]) -> list[s.Statement]:
    """Remove generic statements that still have type_params (never instantiated with concrete types)."""
    return [stmt for stmt in statements if not (isinstance(stmt, s.NamedStatement) and stmt.type_params)]


def __finalize_specialized_enum_specs(statements: list[s.Statement], specialized_names: set[str]) -> list[s.Statement]:
    """After the redirect pass, rebuild _enum_spec for specialized enum statements AND
    for non-generic enums that reference generic types.

    The redirect pass updates variant parameter types (via search_and_replace on variants),
    but _enum_spec.all_fields was built before redirect and still has stale references.
    Rebuilding collects all_fields from the now-correct variant parameters.

    Non-generic enums (type_params=()) like JsonValue may contain fields whose types are
    generic (e.g. elements: List<JsonValue>). After __replace_concrete_references, their
    variant parameter declared_types are updated to the concrete specialized form, but
    _enum_spec.all_fields is not (EnumSpec.search_and_replace never recurses into all_fields).
    Rebuilding here ensures their all_fields reflects the redirected types."""
    result = []
    for stmt in statements:
        if isinstance(stmt, s.EnumStatement) and stmt._root_name == stmt.name:
            if stmt.name in specialized_names or not stmt.type_params:
                stmt = __rebuild_enum_spec(stmt)
        result.append(stmt)
    return result


def __convert_generics_iterative(statements: list[s.Statement]) -> list[s.Statement]:
    """
    Iteratively convert generics to concrete specialized versions.
    Keeps iterating until no new specialized statements are created.
    """
    # Track ALL specialized enum names across all iterations so that
    # __finalize_specialized_enum_specs can rebuild their _enum_spec after
    # every redirect pass.  A specialized enum's all_fields may reference
    # another specialized enum (e.g. Dict's DictNode.bucket: _DictBucket<K,V>)
    # that was created in a later iteration; rebuilding on every iteration
    # ensures all_fields stays current as new redirections become available,
    # which is critical for mark_complex_enums to detect recursive cycles.
    all_specialized_enum_names: set[str] = set()

    while True:
        # Step 1: Find all concrete instantiations
        data_refs, type_refs = __find_concrete_instantiations(statements)

        if not data_refs and not type_refs:
            # No concrete instantiations found - we're done iterating
            break

        # Step 2: Create specialized versions for matching NamedStatements
        specialized = __create_specialized_statements(statements, data_refs, type_refs)

        # Step 2b: Scan newly-created specialized statements for extra concrete refs
        # that arose from type substitution.  Example: when get$generic$bigint_bigint is
        # created, substituting K→bigint transforms EnumSpec('Dict@...', type_params=(K,V))
        # in a match arm's type_spec to EnumSpec('Dict@...', type_params=(bigint,bigint)).
        # That concrete ref was NOT in data_refs (all pre-existing stmts had it redirected
        # in an earlier iteration), so __replace_concrete_references would miss it.
        # Fix: collect those refs from `specialized`, but only if their specialized target
        # already exists (created in a prior iteration) to avoid premature creation.
        if specialized:
            extra_data, extra_type = __find_concrete_instantiations(specialized)
            existing_names = {stmt.name for stmt in statements}
            extra_data = {(n, tp) for n, tp in extra_data
                          if __create_unique_name(n, tp) in existing_names}
            extra_type = {(n, tp) for n, tp in extra_type
                          if __create_unique_name(n, tp) in existing_names}
            if extra_data or extra_type:
                data_refs = data_refs | extra_data
                type_refs = type_refs | extra_type

        # Step 3: Replace concrete references with specialized names in ALL statements
        # (including newly specialized ones).  We do this even when `specialized` is
        # empty because a specialized statement created in the *previous* iteration
        # may carry un-redirected refs (e.g. ClassSpec<bigint> in trait_params that
        # only became concrete after K was substituted).  The redirect is cheap;
        # skipping it causes LookupError in __resolve_trait_references.
        statements = __replace_concrete_references(statements + specialized, data_refs, type_refs)

        # Step 4: Rebuild _enum_spec for ALL specialized enum statements now that
        # variant parameter types may have been redirected to concrete names.
        # We rebuild every known specialized enum (not just this iteration's new
        # ones) so that cross-enum field references (e.g. Dict.bucket pointing
        # to _DictBucket$generic$…) get updated as soon as the redirect lands.
        new_enum_names = {stmt.name for stmt in specialized if isinstance(stmt, s.EnumStatement)}
        all_specialized_enum_names |= new_enum_names
        if all_specialized_enum_names:
            statements = __finalize_specialized_enum_specs(statements, all_specialized_enum_names)

        if not specialized:
            # No new specialisations were needed; refs have been redirected.
            break

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


def __refresh_enum_spec_all_fields(statements: list[s.Statement]) -> list[s.Statement]:
    """Sync all embedded EnumSpec.all_fields to the canonical _enum_spec built by
    __rebuild_enum_spec.

    __replace_concrete_references redirects root_name but copies all_fields from the
    original generic EnumSpec, which may contain GenericPlaceholderSpec entries or
    reference un-redirected generic child enums (e.g. _DictBucket@hash instead of
    _DictBucket$generic$bigint_bigint).  This pass looks up the canonical _enum_spec
    from the corresponding EnumStatement (the authoritative source after all
    __rebuild_enum_spec calls) and overwrites all_fields in every embedded copy.

    Runs after __prune_unused_generics so only specialized enums are in the lookup
    table, which means stale copies whose root_name no longer exists (e.g. the
    original generic Dict@hash in a match arm's type_spec) are left untouched —
    those are handled separately by match.py using the subject type instead.
    """
    canonical: dict[str, t.EnumSpec] = {}
    for stmt in statements:
        if (isinstance(stmt, s.EnumStatement)
                and stmt._enum_spec is not None
                and stmt._root_name == stmt.name):   # root only, skip nested variant stmts
            canonical.setdefault(stmt._enum_spec.root_name, stmt._enum_spec)

    if not canonical:
        return statements

    # Fix nested stale EnumSpec copies inside canonical all_fields.
    # EnumSpec.search_and_replace never recurses into all_fields (to prevent
    # infinite loops on recursive enums), so a non-generic enum like JsonValue
    # that was rebuilt by __finalize_specialized_enum_specs may have all_fields
    # entries whose root_name is correct (e.g. List$generic$JsonValue) but whose
    # own all_fields still came from the original redirect (stale GenericPlaceholders
    # or pruned-generic child references).  Each pass propagates one extra level
    # of nesting through the canonical-spec dependency graph.
    #
    # IMPORTANT: identity-perfect convergence is impossible for self-recursive
    # enums (every pass creates a fresh tuple while the spec keeps referencing
    # itself by identity), but the *content* of all_fields stabilises within a
    # few passes. We therefore cap iterations at a generous bound and accept
    # whatever state exists after — downstream passes only inspect content.
    _MAX_REFRESH_ITERS = 16
    for _ in range(_MAX_REFRESH_ITERS):
        changed = False
        new_canonical: dict[str, t.EnumSpec] = {}
        for root_name, es in canonical.items():
            new_fields = list(es.all_fields)
            fields_changed = False
            for i, (fn, ft) in enumerate(new_fields):
                if isinstance(ft, t.EnumSpec):
                    spec = canonical.get(ft.root_name)
                    if spec is not None and ft.all_fields is not spec.all_fields:
                        new_fields[i] = (fn, dataclasses.replace(
                            ft, all_fields=spec.all_fields,
                            all_leaf_names=spec.all_leaf_names))
                        fields_changed = True
            if fields_changed:
                new_canonical[root_name] = dataclasses.replace(
                    es, all_fields=tuple(new_fields))
                changed = True
            else:
                new_canonical[root_name] = es
        canonical = new_canonical
        if not changed:
            break

    def refresh(resolver: g.Resolver, thing):
        if not isinstance(thing, t.EnumSpec):
            return thing
        spec = canonical.get(thing.root_name)
        if spec is None:
            return thing
        # Use identity check, not equality: EnumSpec.__eq__ excludes all_fields
        # and all_leaf_names, so == would falsely match stale copies.
        if spec.all_fields is thing.all_fields and spec.all_leaf_names is thing.all_leaf_names:
            return thing
        return dataclasses.replace(thing,
                                   all_fields=spec.all_fields,
                                   all_leaf_names=spec.all_leaf_names)

    resolver = g.ResolverRoot(statements)
    return [stmt.search_and_replace(resolver, refresh) for stmt in statements]


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
    converted = __refresh_enum_spec_all_fields(converted)
    resolved = __resolve_trait_references(converted)
    return resolved
