from __future__ import annotations

import dataclasses
import pyast.rewrite as rw
from typing import Callable

import pyast.statement as s
import pyast.expression as e

import pyast.resolver as g
import pyast.typespec as t

from langtools import checked_cast
from pyast.statement import ImportGroup


def __create_unique_name(base_name: str, type_args: tuple[t.TypeSpec, ...]) -> str:
    """Create a unique mangled name for a monomorphized generic."""
    if not type_args:
        return base_name

    # Generate type signature string
    type_sig = "_".join(tp.as_unique_id_str() or "unknown" for tp in type_args)
    return f"{base_name}$generic${type_sig}"


def __deep_id(spec) -> str:
    """A TOTAL recursive spelling of a spec, for the instantiation sort's
    tie-break: as_unique_id_str collapses id-less specs to None/"unknown", so
    structurally DIFFERENT argument lists can share a sort key — and the tie
    then falls to set-iteration order, which the bootstrap port cannot
    reproduce (it is hash-seed order, not structure). Every constructor is
    spelled with its name and children; unions sort their member spellings
    (set semantics). The port mirrors this function byte-for-byte."""
    if spec is None:
        return "_"
    if isinstance(spec, t.BuiltinSpec):
        return f"B({spec.type_name})"
    if isinstance(spec, t.NamedSpec):
        return f"N({spec.name};{','.join(__deep_id(p) for p in spec.type_params)})"
    if isinstance(spec, t.ClassSpec):
        return f"C({spec.name};{','.join(__deep_id(p) for p in spec.type_params)})"
    if isinstance(spec, t.EnumSpec):
        return f"E({spec.root_name};{','.join(__deep_id(p) for p in spec.type_params)})"
    if isinstance(spec, t.TupleSpec):
        return "T(" + ",".join(f"{en.name or ''}:{__deep_id(en.type)}" for en in spec.entries) + ")"
    if isinstance(spec, t.CallableSpec):
        return f"F({__deep_id(spec.parameters)};{__deep_id(spec.result)})"
    if isinstance(spec, t.CombinationSpec):
        return "U(" + "|".join(sorted(__deep_id(m) for m in spec.types)) + ")"
    if isinstance(spec, t.GenericPlaceholderSpec):
        return f"G({spec.name})"
    if isinstance(spec, t.LazyStubSpec):
        return f"L({__deep_id(spec.target_type)})"
    if isinstance(spec, t.ArrayFieldSpec):
        return f"A({__deep_id(spec.element)};{spec.length_field})"
    return f"X({type(spec).__name__})"


def __is_concrete_type_args(type_args: tuple[t.TypeSpec, ...]) -> bool:
    """Check if all type arguments are concrete AND ready to name an
    instantiation. A bare GenericPlaceholderSpec is obviously not; neither is
    a spec still carrying its own type_params (e.g. the EnumSpec for _N<T> —
    or _N<Int> before ITS redirect has landed): its unique-id ignores the
    pending arguments, so using it would name the instantiation after the raw
    template (List$generic$enum(_N) for every _N<...>, colliding them all and
    feeding templates back in as arguments — observed as a runaway
    _N$generic$enum(_N$generic$enum(...)) cascade). Such an argument becomes
    usable on a later iteration, once its own specialisation is redirected
    and its type_params are cleared."""
    return all(not isinstance(tp, t.GenericPlaceholderSpec)
               and not (isinstance(tp, (t.EnumSpec, t.ClassSpec, t.NamedSpec))
                        and tp.type_params)
               # A union with a placeholder member (`E | JsonParseError` while E
               # is still abstract) is NOT concrete — specialising it produces a
               # `…_unknown` instantiation that crashes codegen. The bare-
               # placeholder check above misses it (the arg is a CombinationSpec,
               # not the placeholder itself), and `is_concrete()` is no help
               # because GenericPlaceholderSpec.is_concrete() returns True.
               and not (isinstance(tp, t.CombinationSpec) and __contains_placeholder(tp))
               for tp in type_args)


def __contains_placeholder(spec: t.TypeSpec) -> bool:
    """True if `spec` holds a GenericPlaceholderSpec anywhere — used to spot a
    not-yet-concrete union member like `E | JsonParseError` and refuse to treat
    it as a concrete type argument.

    `is_concrete()` is no help: GenericPlaceholderSpec.is_concrete() returns True
    (a placeholder is a fully-formed type, just an unbound one). By the time this
    pass runs, name resolution has converged, so every surviving generic
    reference is a GenericPlaceholderSpec — an unresolved NamedSpec would already
    have failed compilation (compiler.py rejects any leftover NamedSpec before
    generics run), which is why there is no NamedSpec case below."""
    if isinstance(spec, t.GenericPlaceholderSpec):
        return True
    if isinstance(spec, t.CombinationSpec):
        return any(__contains_placeholder(m) for m in spec.types)
    if isinstance(spec, t.ClassSpec):
        return any(__contains_placeholder(tp) for tp in spec.type_params)
    if isinstance(spec, t.TupleSpec):
        return any(en.type is not None and __contains_placeholder(en.type) for en in spec.entries)
    if isinstance(spec, t.EnumSpec) and spec.type_params:
        return any(__contains_placeholder(tp) for tp in spec.type_params)
    return False


def __appears_outside_union(spec: t.TypeSpec, name: str, in_union: bool = False) -> bool:
    """True if type parameter `name` is used anywhere in `spec` that is NOT
    inside a union.

    This is how __generic_instance_refs decides what to do with a parameter the
    interface match left unbound:
      - Used ONLY inside unions (E in `E | Bool`): unification genuinely can't
        pin it — once widened, E=Never, E=Bool, ... all give the same union. A
        benign, expected gap; leave the `where` clause to bind it.
      - Used OUTSIDE any union (S in `Grow<S>`): unification SHOULD have pinned
        it. If it didn't, the interface match never really named this instance,
        and where-solving would bind from an unrelated one — so the caller bails
        rather than rescue a bogus match.

    The recursion mirrors the type structure; descending into a union member
    sets in_union, and only a bare placeholder reached with in_union False
    counts. (No NamedSpec case — see __contains_placeholder: none survive here.)"""
    if isinstance(spec, t.GenericPlaceholderSpec):
        return spec.name == name and not in_union
    if isinstance(spec, t.CombinationSpec):
        return any(__appears_outside_union(m, name, True) for m in spec.types)
    if isinstance(spec, t.ClassSpec):
        return any(__appears_outside_union(tp, name, in_union) for tp in spec.type_params)
    if isinstance(spec, t.TupleSpec):
        return any(en.type is not None and __appears_outside_union(en.type, name, in_union)
                   for en in spec.entries)
    if isinstance(spec, t.EnumSpec) and spec.type_params:
        return any(__appears_outside_union(tp, name, in_union) for tp in spec.type_params)
    return False


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

        return rw.UNCHANGED

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

    def _substitute_enum(es: t.EnumSpec, visited: frozenset[str]) -> t.TypeSpec:
        # Substitute the spec's own type_params as well as its all_fields.
        # Without this, an EnumSpec embedded as a type ARGUMENT of another
        # generic (e.g. the _N<T> inside List<_N<T>>) keeps placeholder
        # type_params after T is bound: __find_concrete_instantiations never
        # sees a concrete (root_name, params) pair, no specialisation or
        # redirect happens, and the generic TEMPLATE spec — placeholder
        # fields, self-reference and all — leaks into codegen.
        if es.type_params:
            new_tp = tuple(_substitute_in_field(tp, visited) for tp in es.type_params)
            if any(n is not o for n, o in zip(new_tp, es.type_params)):
                es = dataclasses.replace(es, type_params=new_tp)
        return es.walk_all_fields(_substitute_in_field, visited)

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
        if isinstance(ft, t.EnumSpec):
            return _substitute_enum(ft, visited)
        return ft

    def substitute(resolver: g.Resolver, thing):
        if isinstance(thing, t.GenericPlaceholderSpec):
            return _resolve_gp(thing)
        if isinstance(thing, t.EnumSpec):
            return _substitute_enum(thing, frozenset())
        return rw.UNCHANGED

    # Use search_and_replace to recursively substitute throughout the tree
    return rw.resolved(node.search_and_replace(g.ResolverRoot([]), substitute), node)


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

    # A generic class's concrete methods become top-level C functions named by
    # the method name. Two instantiations (e.g. Array$int32 and Array$str) would
    # otherwise emit the same symbol and collide — the last one wins, silently
    # corrupting calls into the others. Suffix each own method (and its matching
    # vtable slot) with the type signature so every instantiation is distinct.
    # The '@' separator keeps the suffixed name `name_matches`-compatible, so
    # DotExpression member lookup on the specialised class still resolves it by
    # the original query name.
    if isinstance(new_stmt, s.ClassStatement):
        type_sig = "_".join(tp.as_unique_id_str() or "unknown" for tp in type_args)
        renamed: dict[str, str] = {}
        new_members: list[s.Statement] = []
        for m in new_stmt.statements:
            if isinstance(m, s.FunctionStatement) and m.body is not None:
                renamed[m.name] = f"{m.name}@{type_sig}"
                new_members.append(dataclasses.replace(m, name=renamed[m.name]))
            else:
                new_members.append(m)
        if renamed:
            new_slots = None if new_stmt._all_slots is None else [
                dataclasses.replace(slot,
                    name=renamed.get(slot.name, slot.name),
                    provides={renamed.get(p, p) for p in slot.provides})
                for slot in new_stmt._all_slots]
            new_stmt = dataclasses.replace(new_stmt, statements=new_members, _all_slots=new_slots)

    return checked_cast(s.NamedStatement, new_stmt)


def __rename_variant_tree(stmt: s.EnumStatement, type_args: tuple) -> s.EnumStatement:
    """Suffix every variant statement's name (all nesting depths) with the
    specialisation signature, exactly as __create_unique_name mangles the
    corresponding leaf-name strings inside redirected EnumSpecs."""
    new_variants = [
        dataclasses.replace(__rename_variant_tree(v, type_args),
                            name=__create_unique_name(v.name, type_args))
        for v in stmt.variants]
    return dataclasses.replace(stmt, variants=new_variants)


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
    # Tie-break beyond the uid spelling with the DEEP structural spelling:
    # uid collapses id-less specs, and a hash-order tie is unreproducible in
    # the bootstrap port (the last source of whole-compiler C divergence).
    all_refs = sorted(data_refs | type_refs,
                      key=lambda item: (item[0],
                                        tuple(tp.as_unique_id_str() or "" for tp in item[1]),
                                        tuple(__deep_id(tp) for tp in item[1])))
    # Dedup by (specialised name, statement kind), not name alone: a class and
    # its synthesised constructor share a name, so both want the same specialised
    # name and must each be produced. (Simple classes hide this — they're
    # flattened away later — but an array class is never flattened, so its
    # constructor would otherwise be dropped and the call resolve to nothing.)
    existing_keys = {(stmt.name, type(stmt).__name__) for stmt in statements}

    for stmt in statements:
        if isinstance(stmt, s.NamedStatement) and stmt.type_params:
            # Find all concrete instantiations for this generic
            for n, type_args in all_refs:
                if n == stmt.name:
                    new_name = __create_unique_name(stmt.name, type_args)
                    key = (new_name, type(stmt).__name__)
                    if key in existing_keys:
                        continue  # already specialized in a prior iteration
                    specialized_stmt = __create_specialized_version(stmt, type_args)
                    # For enum statements, rename the cloned VARIANT tree with
                    # the same $generic$ suffix — the redirect pass mangles
                    # leaf names inside every EnumSpec it visits, so the
                    # statements those names refer to must match, and
                    # _collect_leaf_names (which every _enum_spec rebuild
                    # calls) reads the variant statement names. Leaving them
                    # un-mangled baked ORIGINAL leaf names under the MANGLED
                    # root, and that stale spec (served by
                    # NewEnumExpression.get_type) failed assignability against
                    # the correctly-mangled view — a specialised enum value
                    # silently skipped its union boxing at emit.
                    if isinstance(specialized_stmt, s.EnumStatement):
                        specialized_stmt = __rename_variant_tree(specialized_stmt, type_args)
                        specialized_stmt = __rebuild_enum_spec(specialized_stmt)
                    specialized.append(specialized_stmt)
                    existing_keys.add(key)  # prevent duplicate in the same iteration

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
        (e.NewEnumExpression,  "root_spec_name", data_refs, (
            ("leaf_name", lambda v, tp: __create_unique_name(v, tp)),
        )),
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
        return rw.UNCHANGED

    return [rw.resolved(stmt.search_and_replace(g.ResolverRoot([]), redirect_reference), stmt) for stmt in statements]


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


def __generic_instance_providers(
    statements: list[s.Statement]
) -> list[tuple[s.LetStatement, t.ClassSpec]]:
    """Generic trait INSTANCES, each paired with the trait pattern it implements
    expressed over the witness LET's placeholders.

    A generic instance — `let [trait] _w<S,T>: _W<S,T> where Box<S,T>`, whose
    witness class `_W<S,T>` implements `Box<Wrap<S,T>,T>` — is never *referenced*
    with explicit type params, so __find_concrete_instantiations never sees it.
    It is selected by constraint discharge: when some monomorphised `where`-clause
    needs `Box<Wrap<Leaf,Int>,Int>`, unifying it against the pattern recovers
    S=Leaf/T=Int (see __generic_instance_refs)."""
    resolver = g.ResolverRoot(statements)
    providers: list[tuple[s.LetStatement, t.ClassSpec]] = []
    for st in statements:
        if not (isinstance(st, s.LetStatement) and st.type_params and 'trait' in st.attributes):
            continue
        dt = st.declared_type
        if not isinstance(dt, t.ClassSpec):
            continue
        found = resolver.find_type(dt.name)
        if len(found) != 1 or not isinstance(found[0].statement, s.ClassStatement):
            continue
        cls = found[0].statement
        if cls._all_parents is None:
            continue
        # The class declares its parents over its OWN placeholders; the let passes
        # its placeholders as the class's args, so remap class→let placeholders.
        remap = ({p.name: c for p, c in zip(cls.type_params, dt.type_params)}
                 if cls.type_params and len(cls.type_params) == len(dt.type_params) else {})
        for parent in cls._all_parents:
            if not isinstance(parent, t.ClassSpec):
                continue
            pattern = t.substitute_placeholders(parent, remap, resolver) if remap else parent
            if isinstance(pattern, t.ClassSpec):
                providers.append((st, pattern))
    return providers


def __collect_concrete_constraints(statements: list[s.Statement]) -> set[t.ClassSpec]:
    """Every concrete trait constraint appearing in a `where` clause anywhere in
    `statements` (top-level functions and nested method bodies alike). Inner types
    may be in either structural (`Box<Wrap<Leaf,Int>,Int>`) or already-mangled
    (`Box<Wrap$generic$Leaf_Int,Int>`) form depending on how far redirection has
    progressed; __generic_instance_refs re-inflates the latter before unifying."""
    resolver = g.ResolverRoot(statements)
    found: set[t.ClassSpec] = set()
    def collect(_, thing):
        if isinstance(thing, s.NamedStatement):
            for tp in thing.trait_params:
                if isinstance(tp, t.ClassSpec) and tp.is_concrete():
                    found.add(tp)
        return rw.UNCHANGED
    for st in statements:
        st.search_and_replace(resolver, collect)
    return found


def __spec_from_mangled(spec: t.TypeSpec, mono_map: dict[str, tuple[str, tuple[t.TypeSpec, ...]]]) -> t.TypeSpec:
    """Undo monomorphisation name-mangling structurally: a bare `Wrap$generic$Leaf`
    ClassSpec becomes `Wrap<Leaf>` again (recursively). The constraint we must
    discharge only ever exists with its inner types already mangled — the
    concreteness gate specialises `Wrap<Leaf,Int>` to its opaque name *before*
    the wrapping `useBox`/instance is even instantiable — so we rebuild the
    structure the unifier needs from the (name, type_args) of each specialisation."""
    if isinstance(spec, t.ClassSpec):
        if not spec.type_params and spec.name in mono_map:
            base_name, base_args = mono_map[spec.name]
            return dataclasses.replace(
                spec, name=base_name,
                type_params=tuple(__spec_from_mangled(a, mono_map) for a in base_args))
        if spec.type_params:
            return dataclasses.replace(
                spec, type_params=tuple(__spec_from_mangled(a, mono_map) for a in spec.type_params))
    return spec


def __mangled_from_spec(spec: t.TypeSpec) -> t.TypeSpec:
    """Inverse of __spec_from_mangled: a structural `Wrap<Leaf,Int>` recovered by the
    unifier becomes the bare monomorphic name `Wrap$generic$Leaf_Int` (no type
    params). The witness must be specialised against that bare name — the form
    __is_concrete_type_args accepts and the form its already-monomorphised class
    actually has."""
    if isinstance(spec, t.ClassSpec) and spec.type_params:
        args = tuple(__mangled_from_spec(a) for a in spec.type_params)
        return dataclasses.replace(spec, name=__create_unique_name(spec.name, args), type_params=())
    return spec


def __concrete_instance_interfaces(statements: list[s.Statement]) -> list[t.ClassSpec]:
    """The concrete interface(s) implemented by each NON-generic `[trait]`
    instance — e.g. `let [trait] _one: _OneStream` implements
    `Stream<One, Int, Never>`.

    These are the known, fully-concrete facts that __bind_where_params matches a
    generic instance's `where` constraints against, to pin down a type parameter
    the interface match alone left unbound. Only non-generic instances are
    collected; a generic one has nothing concrete to offer yet."""
    resolver = g.ResolverRoot(statements)
    out: list[t.ClassSpec] = []
    for st in statements:
        if not (isinstance(st, s.LetStatement) and 'trait' in st.attributes and not st.type_params):
            continue
        dt = st.declared_type
        if not isinstance(dt, t.ClassSpec):
            continue
        found = resolver.find_type(dt.name)
        if len(found) != 1 or not isinstance(found[0].statement, s.ClassStatement):
            continue
        cls = found[0].statement
        if cls._all_parents is None:
            continue
        remap = ({p.name: c for p, c in zip(cls.type_params, dt.type_params)}
                 if cls.type_params and len(cls.type_params) == len(dt.type_params) else {})
        for parent in cls._all_parents:
            if not isinstance(parent, t.ClassSpec):
                continue
            iface = t.substitute_placeholders(parent, remap, resolver) if remap else parent
            if isinstance(iface, t.ClassSpec) and iface.is_concrete():
                out.append(iface)
    return out


def __bind_where_params(st: s.LetStatement, mapping: dict[str, t.TypeSpec],
                        instance_ifaces: list[t.ClassSpec],
                        mono_map: dict[str, tuple[str, tuple[t.TypeSpec, ...]]]) -> dict[str, t.TypeSpec]:
    """Fill in instance type parameters that the interface match left unbound, by
    solving the instance's own `where` constraints against the concrete instances
    we already know about.

    Worked example — the error-growing combinator

        _Grow<S, E> : Stream<Grow<S>, Int, E | Bool>  where Stream<S, Int, E>

    has E only in its output union `E | Bool`. Matching that against a concrete
    `Bool` is ambiguous (E=Never, E=Bool, ... all widen to the same union), so E
    comes back unbound. But the `where Stream<S, Int, E>` pins it: with S already
    known to be One, `Stream<One, Int, E>` matched against the known concrete
    instance `Stream<One, Int, Never>` gives E = Never. This only fills what the
    interface match left out; error-preserving combinators bind every parameter
    up front, so for them it does nothing.

    The match is strict and positional, deliberately NOT unify_generic.
    unify_generic is lenient — on a mismatched concrete anchor it returns the
    mapping unchanged — which would bind a target parameter from an unrelated
    instance and cascade into runaway Map<Map<...>> instantiation. So here a
    concrete anchor position MUST equal the instance's exactly; a target
    placeholder is bound; anything else (e.g. an anchor that is itself still an
    unbound placeholder) rejects the match.

    This is the MONO-TIME where-discharge; its call-site (pre-monomorphisation)
    counterpart is typespec/algebra.py::solve_trait_constraint. The two are
    deliberately separate — this one consumes `mono_map`, the instantiation
    facts the surrounding worklist loop itself produces, which do not exist at
    the call-site phase — see the design note in docs/compiler-internals.md §3."""
    resolver = g.ResolverRoot([])
    targets = {p.name for p in st.type_params if p.name not in mapping}
    for wc in st.trait_params:
        if not targets:
            break
        wc_sub = t.substitute_placeholders(wc, mapping, resolver)
        if not isinstance(wc_sub, t.ClassSpec):
            continue
        for raw_iface in instance_ifaces:
            # Concrete-instance interfaces come back name-MANGLED (e.g.
            # `Stream$generic$One_bigint_Never`, no structural type params), but
            # the where-constraint is structural — re-inflate to compare.
            iface = __spec_from_mangled(raw_iface, mono_map)
            if not isinstance(iface, t.ClassSpec):
                continue
            binding = t.bind_from_constraint_match(wc_sub, iface, targets)
            if binding:
                mapping = {**mapping, **binding}
                targets = {p.name for p in st.type_params if p.name not in mapping}
                break
    return mapping


def __generic_instance_refs(
    providers: list[tuple[s.LetStatement, t.ClassSpec]],
    constraints: set[t.ClassSpec],
    mono_refs: set[tuple[str, tuple[t.TypeSpec, ...]]],
    instance_ifaces: list[t.ClassSpec],
) -> set[tuple[str, tuple[t.TypeSpec, ...]]]:
    """Witness-let instantiations (name, type_args) needed to satisfy `constraints`
    via the generic `providers`. The witness's own `where` becomes a fresh, more
    concrete constraint that a later loop iteration discharges — so nested wrappers
    resolve by recursion."""
    mono_map = {__create_unique_name(n, ta): (n, ta) for n, ta in mono_refs if ta}
    extra: set[tuple[str, tuple[t.TypeSpec, ...]]] = set()
    for st, pattern in providers:
        names = {p.name for p in st.type_params}
        for constraint in constraints:
            if pattern.name != constraint.name:
                continue
            inflated = __spec_from_mangled(constraint, mono_map)
            mapping = t.unify_generic(pattern, inflated, names)
            if mapping is None:
                continue
            # Interface unification can leave a param undetermined when it only
            # appears in an output union (error-growing combinators); solve the
            # let's `where` constraints to bind it — but ONLY when the interface
            # match genuinely named this instance: it bound something, and every
            # still-unbound param lives solely in a union position (otherwise the
            # constraint isn't really for this instance and where-solving would
            # cascade across unrelated instances).
            unbound = [p for p in st.type_params if p.name not in mapping]
            if (unbound and mapping
                    and all(not __appears_outside_union(pattern, p.name) for p in unbound)):
                mapping = __bind_where_params(st, mapping, instance_ifaces, mono_map)
            if not all(p.name in mapping for p in st.type_params):
                continue
            type_args = tuple(__mangled_from_spec(mapping[p.name]) for p in st.type_params)
            if __is_concrete_type_args(type_args):
                extra.add((st.name, type_args))
    return extra


# Monomorphisation-round bound: legitimate transitive instantiation chains
# stabilise in a handful of rounds; a loop still minting new instantiations
# after this many is deepening without bound (mutual polymorphic recursion —
# the direct case is caught structurally, see the detector in the loop).
_MAX_MONO_ROUNDS = 64


def __convert_generics_iterative(statements: list[s.Statement]) -> "tuple[list[s.Statement], list]":
    """
    Iteratively convert generics to concrete specialized versions.
    Keeps iterating until no new specialized statements are created — or until
    an instantiation's type arguments exceed _MAX_TYPE_ARG_DEPTH, which means
    polymorphic recursion is minting ever-deeper instantiations (returned as
    compile errors, second element).
    """
    from parsing.parselib import Error
    from parsing.tokenizer import LineRef
    # Track ALL specialized enum names across all iterations so that
    # __finalize_specialized_enum_specs can rebuild their _enum_spec after
    # every redirect pass.  A specialized enum's all_fields may reference
    # another specialized enum (e.g. Dict's DictNode.bucket: _DictBucket<K,V>)
    # that was created in a later iteration; rebuilding on every iteration
    # ensures all_fields stays current as new redirections become available,
    # which is critical for mark_complex_enums to detect recursive cycles.
    all_specialized_enum_names: set[str] = set()
    # Concrete `where` constraints seen so far, accumulated across iterations so a
    # generic instance can be discharged once its constraint first appears.
    seen_constraints: set[t.ClassSpec] = set()
    # Every (generic-name, concrete type_args) ever specialised, so a mangled
    # name in a constraint can be re-inflated to the structure the unifier needs.
    seen_mono_refs: set[tuple[str, tuple[t.TypeSpec, ...]]] = set()

    for _round in range(_MAX_MONO_ROUNDS):
        # Step 1: Find all concrete instantiations
        data_refs, type_refs = __find_concrete_instantiations(statements)
        seen_mono_refs |= data_refs | type_refs

        # Step 1b: Generic trait instances are selected by constraint discharge,
        # not by an explicit type-param reference. Discharge the constraints seen
        # so far against the generic instances, seeding witness-let refs.
        seen_constraints |= __collect_concrete_constraints(statements)
        data_refs = data_refs | __generic_instance_refs(
            __generic_instance_providers(statements), seen_constraints, seen_mono_refs,
            __concrete_instance_interfaces(statements))

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

    else:
        # Still minting new instantiations after every allowed round: the
        # instantiation graph is deepening without bound — polymorphic
        # recursion (`depth<T>` calling `depth<Wrap<T>>` needs a fresh
        # `depth<Wrap<Wrap<...>>>` per round, so its per-generic instantiation
        # count is about the round cap; legitimate generics sit far below).
        # Blame the generics with runaway counts, at their declarations.
        from collections import Counter
        counts = Counter(n for n, _ in seen_mono_refs)
        offenders = sorted(n for n, cnt in counts.items() if cnt >= _MAX_MONO_ROUNDS // 2)
        by_name = {stmt.name: stmt for stmt in statements}
        if offenders:
            return statements, [Error(
                by_name[n].line_ref if n in by_name else LineRef("$generics", 1, 1),
                f"polymorphic recursion: `{g.simple_name(g.bare_name(n))}` is "
                f"instantiated at ever-deeper type arguments ({counts[n]} distinct "
                f"instantiations without stabilising) — a recursive call must use "
                f"the function's own type parameters, not a compound of them "
                f"(e.g. Wrap<T>)") for n in offenders]
        return statements, [Error(LineRef("$generics", 1, 1),
            f"generic instantiation did not stabilise after {_MAX_MONO_ROUNDS} "
            f"rounds — likely polymorphic recursion through mutually recursive "
            f"generics; recursive calls must use the functions' own type "
            f"parameters")]

    # After iterations are stable, prune unused generics
    statements = __prune_unused_generics(statements)

    return statements, []


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
        classes = resolver.find_type(tr.declared_type.name)
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
            return rw.UNCHANGED

        # Use the trait_scope recorded during compilation if available, otherwise derive it.
        if thing.resolved_trait_scope is not None:
            trait_spec = thing.resolved_trait_scope
        else:
            datas = r.find_data(thing.name)
            if len(datas) != 1 or datas[0].scope != g.ResolvedScope.TRAIT:
                return rw.UNCHANGED
            trait_spec = datas[0].trait_scope
            if not isinstance(trait_spec, t.ClassSpec):
                return rw.UNCHANGED

        providers = [tr for tr in traits if implements_trait(tr, trait_spec)]
        if len(providers) != 1:
            return rw.UNCHANGED

        provider = providers[0]
        provider_type = provider.declared_type
        if not isinstance(provider_type, t.ClassSpec):
            return rw.UNCHANGED

        provider_classes = r.find_type(provider_type.name)
        if len(provider_classes) != 1:
            return rw.UNCHANGED
        provider_class = provider_classes[0].statement
        if not isinstance(provider_class, s.ClassStatement):
            return rw.UNCHANGED

        # Find the concrete method on the provider class by simple name
        simple = g.simple_name(thing.name)
        method_datas = provider_class.find_data(r, simple)
        if not method_datas:
            return rw.UNCHANGED

        if len(method_datas) > 1:
            # Multiple overloads — disambiguate by comparing the concrete type of
            # the interface method (looked up by exact hash) against class methods.
            iface_classes = r.find_type(trait_spec.name)
            if len(iface_classes) == 1 and isinstance(iface_classes[0].statement, s.ClassStatement):
                iface_cls = iface_classes[0].statement
                iface_mds = iface_cls.find_data(r, thing.name)
                if len(iface_mds) == 1 and isinstance(iface_mds[0].statement, s.FunctionStatement):
                    iface_type = iface_mds[0].statement.get_type()
                    if iface_type is not None:
                        if iface_cls.type_params and trait_spec.type_params:
                            mapping = {p.name: c for p, c in zip(iface_cls.type_params, trait_spec.type_params)}
                            def sub(_, node, m=mapping):
                                if isinstance(node, t.GenericPlaceholderSpec) and node.name in m:
                                    return m[node.name]
                                return rw.UNCHANGED
                            iface_type = rw.resolved(iface_type.search_and_replace(r, sub), iface_type)
                        matching = [md for md in method_datas
                                    if t.trivially_assignable_equals(r, iface_type, md.statement.get_type())]
                        if len(matching) == 1:
                            method_datas = matching

        if len(method_datas) != 1:
            return rw.UNCHANGED

        provider_expr = e.NamedExpression(thing.line_ref, provider.name)
        return e.DotExpression(thing.line_ref, provider_expr, method_datas[0].unique_name)

    return [rw.resolved(stmt.search_and_replace(resolver, redirect), stmt) for stmt in statements]


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
            return rw.UNCHANGED
        spec = canonical.get(thing.root_name)
        if spec is None:
            return rw.UNCHANGED
        # Use identity check, not equality: EnumSpec.__eq__ excludes all_fields
        # and all_leaf_names, so == would falsely match stale copies.
        if spec.all_fields is thing.all_fields and spec.all_leaf_names is thing.all_leaf_names:
            return rw.UNCHANGED
        return dataclasses.replace(thing,
                                   all_fields=spec.all_fields,
                                   all_leaf_names=spec.all_leaf_names)

    resolver = g.ResolverRoot(statements)
    return [rw.resolved(stmt.search_and_replace(resolver, refresh), stmt) for stmt in statements]


def report_unresolved_generic_calls(statements: list[s.Statement]) -> "list":
    """Post-monomorphisation guard: a reference from NON-generic code to a
    still-generic function means call-site inference could not ground its type
    arguments (nothing in the arguments or the expected type mentioned them).
    Report that at the use site as a compile error — the alternative is a
    checked_cast crash deep inside codegen once the pruned template's type
    comes back None."""
    from parsing.parselib import Error
    from pyast.expression.access import NamedExpression
    errors: list[Error] = []
    resolver = g.ResolverRoot(statements)

    def scan(res: g.Resolver, thing):
        if not isinstance(thing, NamedExpression):
            return rw.UNCHANGED
        datas = res.find_data(thing.name)
        unresolved = False
        if (len(datas) == 1
                and isinstance(datas[0].statement, s.FunctionStatement)
                and (datas[0].statement.type_params or ())):
            # The template survived pruning: the use is fine only when it
            # carries a full, ground set of type arguments.
            tps = thing.type_params or ()
            unresolved = (len(tps) != len(datas[0].statement.type_params)
                          or any(t.has_free_placeholders(tp, res) for tp in tps))
        elif (not datas and '@' in thing.name and thing.type_params
                and any(t.has_free_placeholders(tp, res) for tp in thing.type_params)):
            # Dangling reference: the name WAS resolved (it carries the @-hash)
            # but its generic template has been pruned, and the use still holds
            # unbound placeholders — inference never grounded this call.
            unresolved = True
        if unresolved:
            name = g.simple_name(g.bare_name(thing.name))
            errors.append(Error(thing.line_ref,
                f"cannot infer the type arguments of generic function "
                f"`{name}` here — write them explicitly: {name}<...>(...)"))
        return rw.UNCHANGED

    for stmt in statements:
        if getattr(stmt, "type_params", None):
            continue  # a surviving generic template: its body is legitimately generic
        stmt.search_and_replace(resolver, scan)
    return errors


def convert_generic_to_concrete(statements: list[s.Statement]) -> "tuple[list[s.Statement], list]":
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
    converted, errors = __convert_generics_iterative(statements)
    if errors:
        return statements, errors
    converted = __refresh_enum_spec_all_fields(converted)
    resolved = __resolve_trait_references(converted)
    return resolved, []
