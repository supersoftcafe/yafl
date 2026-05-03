from __future__ import annotations

import dataclasses
from abc import abstractmethod
from enum import Enum
from collections.abc import Callable
from dataclasses import dataclass, field

import langtools
import pyast.utils
from parsing.parselib import Error
import pyast.resolver as g
import pyast.statement as s
import pyast.expression as e

import codegen.typedecl as cg_t

from parsing.tokenizer import LineRef


def collect_enum_leaves(stmt: s.EnumStatement) -> list[s.EnumStatement]:
    """Return all leaf EnumStatement nodes in declaration order (same order as all_leaf_names)."""
    if not stmt.variants:
        return [stmt]
    result: list[s.EnumStatement] = []
    for v in stmt.variants:
        result.extend(collect_enum_leaves(v))
    return result


def _collect_leaf_field_sets(
        stmt: s.EnumStatement,
        inherited: list,
) -> list[list]:
    """Return one field list per leaf, including fields inherited from ancestor nodes.

    Fields declared (declared_type is not None) on parent enum nodes are inherited
    by all descendant leaves, matching the behaviour of _collect_data_fields.
    """
    own = [let for let in stmt.parameters.flatten() if let.declared_type is not None]
    combined = inherited + own
    if not stmt.variants:
        return [combined]
    result: list[list] = []
    for v in stmt.variants:
        result.extend(_collect_leaf_field_sets(v, combined))
    return result


def enum_variant_types(stmt: s.EnumStatement, resolver: g.Resolver) -> list[cg_t.Type]:
    """Return one Struct type per leaf variant, with all fields accessible to that leaf."""
    return [
        cg_t.Struct(tuple(
            (let.name, let.declared_type.generate(resolver))
            for let in fields
        ))
        for fields in _collect_leaf_field_sets(stmt, [])
    ]


@dataclass(frozen=True)
class TypeSpec:
    line_ref: LineRef = field(compare=False)

    def is_concrete(self) -> bool:
        return False

    def _compile(self, resolver: g.Resolver) -> tuple[TypeSpec, list[s.Statement]]:
        raise NotImplementedError()

    def compile(self, resolver: g.Resolver) -> tuple[TypeSpec, list[s.Statement]]:
        type, statements = self._compile(resolver)
        if not isinstance(type, TypeSpec):
            raise ValueError("Urggg..  This is here to catch mistakes in the code that the IDE hasn't caught")
        return type, statements

    def check(self, resolver: g.Resolver) -> list[Error]:
        raise NotImplementedError()

    def generate(self, resolver: g.Resolver) -> cg_t.Type:
        raise NotImplementedError()

    def trivially_assignable_from(self, resolver: g.Resolver, right: TypeSpec) -> bool | None:
        raise NotImplementedError()

    def as_unique_id_str(self) -> str|None:
        raise NotImplementedError()

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver, any], any]) -> TypeSpec:
        return langtools.cast(TypeSpec, replace(resolver, self))


def trivially_assignable_equals(resolver: g.Resolver, left: TypeSpec | None, right: TypeSpec | None) -> bool | None:
    if left is None or right is None:
        return None
    # In yafl, a 1-tuple is equivalent to its element (recursively).
    # The unwrap must be symmetric: if either side is a 1-tuple with an
    # unknown entry type, treat the comparison as uncertain (None) rather
    # than unwrapping only the side whose entry type is known — that
    # produces a spurious TupleSpec-vs-singleton mismatch and returns False.
    while isinstance(right, TupleSpec) and len(right.entries) == 1:
        right = right.entries[0].type
        if right is None:
            return None
    while isinstance(left, TupleSpec) and len(left.entries) == 1:
        left = left.entries[0].type
        if left is None:
            return None
    return left.trivially_assignable_from(resolver, right)


@dataclass(frozen=True)
class CallableSpec(TypeSpec):
    parameters: TupleSpec
    result: TypeSpec|None

    def is_concrete(self) -> bool:
        return self.parameters.is_concrete() and (self.result is None or self.result.is_concrete())

    def _compile(self, resolver: g.Resolver) ->  tuple[TypeSpec, list[s.Statement]]:
        p, pglb = self.parameters.compile(resolver)
        r, rglb = self.result.compile(resolver) if self.result else (None, [])
        xtype = dataclasses.replace(self, parameters=p, result=r)
        return xtype, pglb+rglb

    def check(self, resolver: g.Resolver) -> list[Error]:
        return self.parameters.check(resolver) + (self.result.check(resolver) if self.result else [])

    def generate(self, resolver: g.Resolver) -> cg_t.Type:
        return cg_t.FuncPointer()

    def trivially_assignable_from(self, resolver: g.Resolver, right: TypeSpec) -> bool | None:
        if isinstance(right, NamedSpec):
            return None # Not resolved yet

        # Must be callable.
        if not isinstance(right, CallableSpec):
            return False

        # Return types must be equivalent (bidirectionally assignable).
        # Callables do not auto-widen return types — no implicit thunk generation.
        # If either direction is undecided (None), defer the verdict: a generic
        # placeholder expected-type vs T|None candidate is undecided, not False.
        # A definite asymmetry (True/False or False/True) is still False.
        result_fwd = trivially_assignable_equals(resolver, self.result, right.result)
        result_rev = trivially_assignable_equals(resolver, right.result, self.result)
        if result_fwd is None or result_rev is None:
            result_result: bool | None = None
        elif result_fwd is True and result_rev is True:
            result_result = True
        else:
            result_result = False

        # Direction swaps for parameters
        params_result = trivially_assignable_equals(resolver, right.parameters, self.parameters)

        if result_result == False or params_result == False:
            return False

        if result_result and params_result: # None or False
            return True

        return None

    def as_unique_id_str(self) -> str|None:
        p = self.parameters.as_unique_id_str()
        return p and f"f{p}"

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver, any], any]) -> TypeSpec:
        new_self = dataclasses.replace(self,
            parameters=self.parameters.search_and_replace(resolver, replace),
            result=self.result.search_and_replace(resolver, replace) if self.result else None)
        return langtools.cast(TypeSpec, replace(resolver, new_self))


@dataclass(frozen=True)
class BuiltinSpec(TypeSpec):
    type_name: str

    def is_concrete(self) -> bool:
        return True

    def __translate(self) -> cg_t.Type|None:
        match self.type_name:
            case "str":
                return cg_t.Str()
            case "int8":
                return cg_t.Int(8)
            case "int16":
                return cg_t.Int(16)
            case "int32":
                return cg_t.Int(32)
            case "int64":
                return cg_t.Int(64)
            case "bigint":
                return cg_t.Int()
            case "bool":
                return cg_t.Int(8)
            case "float32":
                return cg_t.Float(32)
            case "float64":
                return cg_t.Float(64)
            case _:
                return None

    def _compile(self, resolver: g.Resolver) ->  tuple[TypeSpec, list[s.Statement]]:
        return self, []

    def check(self, resolver: g.Resolver) -> list[Error]:
        xtype = self.__translate()
        if xtype is None:
            return [Error(self.line_ref, f"Unresolved reference to '{self.type_name}'")]
        return []

    def generate(self, resolver: g.Resolver) -> cg_t.Type:
        xtype = self.__translate()
        if xtype is None:
            raise ValueError(f"Unknown type {self.type_name}")
        return xtype

    def trivially_assignable_from(self, resolver: g.Resolver, right: TypeSpec) -> bool | None:
        if isinstance(right, NamedSpec):
            return None # Not resolved yet
        return isinstance(right, BuiltinSpec) and self.type_name == right.type_name

    def as_unique_id_str(self) -> str|None:
        return self.type_name


def Bool() -> BuiltinSpec:
    return BuiltinSpec(LineRef("none", 0, 0), "bool")


@dataclass(frozen=True)
class ClassSpec(TypeSpec):
    name: str
    type_params: tuple[TypeSpec, ...] = ()

    def is_concrete(self) -> bool:
        return not self.type_params or all(tp.is_concrete() for tp in self.type_params)

    def _compile(self, resolver: g.Resolver) ->  tuple[TypeSpec, list[s.Statement]]:
        types = resolver.find_type({self.name})
        if len(types) == 1:
            type_params, statements = zip(*[tp.compile(resolver) for tp in self.type_params]) if self.type_params else ([],[])
            return dataclasses.replace(self, name=types[0].unique_name,  type_params=tuple(type_params)), [s for st in statements for s in st]
        return self, []

    def check(self, resolver: g.Resolver) -> list[Error]:
        tp_errors = [te for tp in self.type_params for te in tp.check(resolver)]
        types = resolver.find_type({self.name})
        match types:
            case []:
                return [Error(self.line_ref, f"Failed to resolve class {self.name}")] + tp_errors
            case [resolved]:
                if not isinstance(resolved.statement, s.ClassStatement):
                    return [Error(self.line_ref, f"Not a class {self.name}")] + tp_errors
                return resolved.statement.check_caller_type_params(resolver, self.type_params, self.line_ref) + tp_errors
            case _:
                return [Error(self.line_ref, f"Found too many classes named {self.name}")] + tp_errors

    def generate(self, resolver: g.Resolver) -> cg_t.Type:
        return cg_t.DataPointer()

    def trivially_assignable_from(self, resolver: g.Resolver, right: TypeSpec) -> bool | None:
        def find_class(xtype: TypeSpec) -> s.ClassStatement:
            clstype = langtools.cast(ClassSpec, xtype)
            xstmt = resolver.find_type({clstype.name})[0].statement
            return langtools.cast(s.ClassStatement, xstmt)

        if not '@' in self.name:
            return None # Left is not resolved yet
        if isinstance(right, NamedSpec):
            return None # Right is not resolved yet so Unknown
        if not isinstance(right, ClassSpec):
            return False # Right is resolved to something not a class so definitely False
        if self.name == right.name:
            return True # Exact match
        rcls = find_class(right)
        if rcls._all_parents is None:
            return None # Right parents aren't resolved yet so Unknown
        result = any(x.name == self.name for x in rcls._all_parents)
        return result

    def as_unique_id_str(self) -> str|None:
        return self.name

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver, any], any]) -> TypeSpec:
        new_self = dataclasses.replace(self,
            type_params=tuple(tp.search_and_replace(resolver, replace) for tp in self.type_params))
        return langtools.cast(TypeSpec, replace(resolver, new_self))


@dataclass(frozen=True)
class EnumSpec(TypeSpec):
    root_name: str
    valid_leaf_names: frozenset[str]
    all_leaf_names: tuple[str, ...]
    # all_fields, is_complex, and type_params are excluded from equality:
    # two EnumSpec instances with the same root_name and valid_leaf_names
    # are the same TYPE; the other fields are metadata that converges
    # iteratively (and may legitimately differ between instances during
    # compile-loop iterations without changing the type's identity).
    # Including them in equality breaks compile-loop convergence on
    # recursive enums whose all_fields stabilises a tier at a time.
    all_fields: tuple[tuple[str, TypeSpec], ...] = field(compare=False)
    # Set by lowering/complex_enums.py for enums that should lower to
    # a heap-allocated object instead of a flat by-value struct. An
    # enum is complex when (a) its all_fields graph contains a cycle
    # through this root_name — directly or via mutual recursion through
    # other enums (so the by-value struct would have infinite size),
    # or (b) it has more than eight fields (large by-value pass-by
    # becomes expensive). Both cases use the same heap-pointer codegen.
    is_complex: bool = field(default=False, compare=False)
    # Set when NamedSpec._compile() produces an EnumSpec that still
    # carries the source NamedSpec's type arguments (K, V, etc.).
    # Used by the generics pass to detect and redirect concrete
    # instantiations of generic enums. Excluded from equality so the
    # compile loop can converge regardless of whether type_params are
    # present (two specs with the same root_name are the same type).
    type_params: tuple[TypeSpec, ...] = field(default=(), compare=False)

    def is_concrete(self) -> bool:
        return '@' in self.root_name

    def _compile(self, resolver: g.Resolver) -> tuple[TypeSpec, list[s.Statement]]:
        # Snap all_fields to the latest canonical version stored on the
        # source EnumStatement. Cached EnumSpec instances inside
        # let.declared_type / function-param types thus stay fresh as
        # the iterative compile loop refines field types from
        # NamedSpec → concrete. The line_ref is preserved so error
        # messages still point at the use site. Walking all_fields here
        # would recurse infinitely on self-referential enums.
        types = resolver.find_type({self.root_name})
        if len(types) == 1:
            target = types[0].statement
            if isinstance(target, s.EnumStatement) and target._enum_spec is not None:
                canonical = target._enum_spec
                if canonical.all_fields != self.all_fields:
                    return dataclasses.replace(self, all_fields=canonical.all_fields), []
        return self, []

    def check(self, resolver: g.Resolver) -> list[Error]:
        return [err for _, ftype in self.all_fields for err in ftype.check(resolver)]

    def generate(self, resolver: g.Resolver) -> cg_t.Type:
        if self.is_complex:
            return cg_t.DataPointer()
        types = resolver.find_type({self.root_name})
        if len(types) == 1 and isinstance(types[0].statement, s.EnumStatement):
            stmt = langtools.cast(s.EnumStatement, types[0].statement)
            container, _ = cg_t.compute_union_slots(enum_variant_types(stmt, resolver))
            return container
        return cg_t.Struct(tuple((name, ftype.generate(resolver)) for name, ftype in self.all_fields))

    def as_unique_id_str(self) -> str | None:
        if '@' not in self.root_name:
            return None
        return f"enum({self.root_name})"

    def trivially_assignable_from(self, resolver: g.Resolver, right: TypeSpec) -> bool | None:
        if isinstance(right, NamedSpec):
            return None
        if not isinstance(right, EnumSpec):
            return False
        if '@' not in self.root_name or '@' not in right.root_name:
            return None
        if right.root_name != self.root_name:
            return False
        return right.valid_leaf_names <= self.valid_leaf_names

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver, any], any]) -> TypeSpec:
        # Do NOT recurse into all_fields: a recursive enum's all_fields
        # references the same EnumSpec, which would loop forever. all_fields
        # is maintained by EnumStatement.compile from the variants'
        # parameter lets — the AST-level recursion walks those lets via
        # the EnumStatement, so every type in all_fields is reached
        # through that other path.
        # DO recurse into type_params so that generics substitution can
        # replace GenericPlaceholderSpec(K) → Int, etc., preserving the
        # concrete type arguments for the generics redirect pass.
        new_type_params = tuple(tp.search_and_replace(resolver, replace) for tp in self.type_params)
        new_self = dataclasses.replace(self, type_params=new_type_params) if new_type_params != self.type_params else self
        return langtools.cast(TypeSpec, replace(resolver, new_self))

    def walk_all_fields(self,
                        fix: Callable[[TypeSpec, frozenset[str]], TypeSpec],
                        visited: frozenset[str] = frozenset()) -> EnumSpec:
        """Apply `fix` to each entry in all_fields with cycle detection.

        EnumSpec.search_and_replace deliberately skips all_fields to avoid
        looping on self-referential enums; lowering passes that need to
        rewrite types nested in all_fields (e.g. ClassSpec→TupleSpec,
        GenericPlaceholderSpec→concrete) use this helper instead.

        `fix(field_type, inner_visited)` returns a (possibly substituted)
        TypeSpec. The visited set tracks the recursion path by root_name;
        callbacks can pass it back into walk_all_fields when descending into
        a nested EnumSpec to avoid re-entering the current root.

        Returns the original spec if no field changed (identity-checked).
        """
        if self.root_name in visited:
            return self
        inner_visited = visited | {self.root_name}
        new_fields = tuple((n, fix(ft, inner_visited)) for n, ft in self.all_fields)
        if all(nv is ov for (_, nv), (_, ov) in zip(new_fields, self.all_fields)):
            return self
        return dataclasses.replace(self, all_fields=new_fields)


@dataclass(frozen=True)
class GenericPlaceholderSpec(TypeSpec):
    name: str

    def is_concrete(self) -> bool:
        return True

    def _compile(self, resolver: g.Resolver) -> tuple[TypeSpec, list[s.Statement]]:
        return self, []

    def check(self, resolver: g.Resolver) -> list[Error]:
        return []

    def generate(self, resolver: g.Resolver) -> cg_t.Type:
        raise RuntimeError("GenericPlaceholderSpec should be replaced with a concrete type")

    def trivially_assignable_from(self, resolver: g.Resolver, right: TypeSpec) -> bool | None:
        if not isinstance(right, GenericPlaceholderSpec):
            return False
        if self.name == right.name:
            return True
        # Different-named placeholders: return None (undecided) so that generic
        # function bodies aren't rejected when one placeholder comes from a nested
        # generic definition (e.g. enum field) and another from the calling function.
        # Concrete type safety is enforced at instantiation time.
        return None

    def as_unique_id_str(self) -> str|None:
        return None # This is 'alias', not a concrete type.

    # Base class search_and_replace is sufficient: it calls replace(resolver, self),
    # which is where mappings like GenericPlaceholderSpec -> concrete type are applied.


def unify_generic(generic: "TypeSpec", concrete: "TypeSpec",
                  placeholder_names: set[str],
                  mapping: dict[str, "TypeSpec"] | None = None) -> dict[str, "TypeSpec"] | None:
    """Match a generic type tree against a concrete type tree; return a
    {placeholder_name: concrete_type} mapping, or None if they don't unify.

    Only recognises placeholders whose name appears in `placeholder_names`.
    Unknown / unresolved branches are skipped (return the current mapping
    unchanged) — the caller should treat a partial mapping as a failure if
    every placeholder must be resolved.
    """
    if mapping is None:
        mapping = {}

    if isinstance(generic, GenericPlaceholderSpec) and generic.name in placeholder_names:
        # Don't let a placeholder bind to itself (or to any other placeholder):
        # the concrete side is not concrete enough to pin down.
        if isinstance(concrete, GenericPlaceholderSpec):
            return mapping
        existing = mapping.get(generic.name)
        if existing is None:
            mapping[generic.name] = concrete
            return mapping
        if existing == concrete:
            return mapping
        return None  # conflicting bindings

    # Same concrete leaf types — nothing to infer, but compatible.
    if isinstance(generic, BuiltinSpec) and isinstance(concrete, BuiltinSpec):
        return mapping if generic.type_name == concrete.type_name else None

    if isinstance(generic, ClassSpec) and isinstance(concrete, ClassSpec):
        if generic.name != concrete.name:
            return mapping  # can't unify further, accept what we have
        if len(generic.type_params) != len(concrete.type_params):
            return mapping
        m: dict[str, TypeSpec] | None = mapping
        for gp, cp in zip(generic.type_params, concrete.type_params):
            m = unify_generic(gp, cp, placeholder_names, m)
            if m is None:
                return None
        return m

    if isinstance(generic, TupleSpec) and isinstance(concrete, TupleSpec):
        if len(generic.entries) != len(concrete.entries):
            return mapping
        m = mapping
        for ge, ce in zip(generic.entries, concrete.entries):
            if ge.type is None or ce.type is None:
                continue
            m = unify_generic(ge.type, ce.type, placeholder_names, m)
            if m is None:
                return None
        return m

    if isinstance(generic, CombinationSpec) and isinstance(concrete, CombinationSpec):
        # Align by position; this is a weak match but works for the common
        # case where the union variants appear in the same order.
        if len(generic.types) != len(concrete.types):
            return mapping
        m = mapping
        for gv, cv in zip(generic.types, concrete.types):
            m = unify_generic(gv, cv, placeholder_names, m)
            if m is None:
                return None
        return m

    if isinstance(generic, CallableSpec) and isinstance(concrete, CallableSpec):
        m = unify_generic(generic.parameters, concrete.parameters, placeholder_names, mapping)
        if m is None:
            return None
        if generic.result is not None and concrete.result is not None:
            m = unify_generic(generic.result, concrete.result, placeholder_names, m)
            if m is None:
                return None
        return m

    # Unknown / mismatched shapes — return current mapping unchanged rather
    # than failing hard; the caller decides whether it's complete enough.
    return mapping


@dataclass(frozen=True)
class NamedSpec(TypeSpec):
    name: str
    type_params: tuple[TypeSpec, ...] = ()

    def is_concrete(self) -> bool:
        return False

    def _compile(self, resolver: g.Resolver) ->  tuple[TypeSpec, list[s.Statement]]:
        types = resolver.find_type({self.name})
        if len(types) == 1:
            xtype = types[0].statement
            if isinstance(xtype, s.TypeAliasStatement):
                if xtype.type.is_concrete():
                    return xtype.type, []
                return self, [] # No change because target isn't a concrete type yet
            elif isinstance(xtype, s.ClassStatement):
                compiled_type_params = tuple(tp.compile(resolver)[0] for tp in self.type_params)
                return ClassSpec(self.line_ref, xtype.name, compiled_type_params), []
            elif isinstance(xtype, s.EnumStatement):
                if xtype._enum_spec is not None:
                    # If this NamedSpec carries type_params (e.g. Dict<K,V>), propagate
                    # them into the returned EnumSpec so the generics pass can detect
                    # and redirect concrete instantiations like Dict<Int,Str>.
                    if self.type_params:
                        compiled_tps = tuple(tp.compile(resolver)[0] for tp in self.type_params)
                        return dataclasses.replace(xtype._enum_spec, type_params=compiled_tps), []
                    return xtype._enum_spec, []
                return self, []
        return self, []

    def check(self, resolver: g.Resolver) -> list[Error]:
        types = resolver.find_type({self.name})
        if len(types) > 1:
            return [Error(self.line_ref, f"Ambiguous reference to '{self.name}'")]
        if len(types) == 1:
            return []
        return [Error(self.line_ref, f"Unresolved reference to '{self.name}'")]

    def generate(self, resolver: g.Resolver) -> cg_t.Type:
        raise RuntimeError("NamedSpec should be replaced with a concrete type")

    def trivially_assignable_from(self, resolver: g.Resolver, right: TypeSpec) -> bool | None:
        return None # Not resolved yet

    def as_unique_id_str(self) -> str|None:
        return None # This is 'alias', not a concrete type.


def _is_pointer_union_distinguishable(variant_types: list[cg_t.Type]) -> bool:
    """True if all variants are pointer-representable AND each variant is runtime-
    distinguishable by pointer tag bits, null check, or vtable identity.

    Rules per variant:
      * Unit (empty Struct): null pointer.
      * Int (bigint, precision 0): PTR_IS_INTEGER or vtable == INTEGER_VTABLE.
      * Str: PTR_IS_STRING or vtable == STRING_VTABLE.
      * Class (DataPointer / class object pointer): unique vtable.
      * Anything else (scalars, composite structs): not pointer-representable.

    Classes are disambiguated by their own vtable, so multiple class variants
    are allowed — the dispatch generates a vtable-identity test per class.
    """
    for vt in variant_types:
        if isinstance(vt, cg_t.Struct) and not vt.fields:
            continue  # unit / None — null sentinel
        if isinstance(vt, cg_t.Int) and vt.precision == 0:
            continue  # bigint — PTR_IS_INTEGER or INTEGER_VTABLE
        if isinstance(vt, cg_t.Str):
            continue  # str — PTR_IS_STRING or STRING_VTABLE
        if isinstance(vt, cg_t.DataPointer):
            continue  # class object — unique vtable identifies it
        return False  # scalar or composite struct — needs tagged-union Struct
    non_unit = [vt for vt in variant_types
                if not (isinstance(vt, cg_t.Struct) and not vt.fields)]
    return len(non_unit) >= 1


@dataclass(frozen=True)
class CombinationSpec(TypeSpec):
    types: tuple[TypeSpec, ...]

    def __post_init__(self):
        object.__setattr__(self, 'types', tuple(self.types))

    def is_concrete(self) -> bool:
        return all(x.is_concrete() for x in self.types)

    def _compile(self, resolver: g.Resolver) ->  tuple[CombinationSpec, list[s.Statement]]:
        new_types, new_errors = zip(*[x.compile(resolver) for x in self.types])
        return dataclasses.replace(self, types = new_types), [x for stm in new_errors for x in stm]

    def check(self, resolver: g.Resolver) -> list[Error]:
        return [y for x in self.types for y in x.check(resolver)]

    def generate(self, resolver: g.Resolver) -> cg_t.Type:
        variant_types = [v.generate(resolver) for v in self.types]
        unit = cg_t.Struct(())
        non_unit = [vt for vt in variant_types if vt != unit]
        if len(non_unit) == 1 and non_unit[0].get_pointer_paths("x") == ["x"]:
            return cg_t.DataPointer()  # null sentinel for unit (None) variant(s)
        if _is_pointer_union_distinguishable(variant_types):
            return cg_t.DataPointer()  # dispatch via pointer tag bits at runtime
        container, _ = cg_t.compute_union_slots(variant_types)
        return container

    def as_unique_id_str(self) -> str|None:
        ids = [x.as_unique_id_str() for x in self.types]
        if not all(ids):
            return None
        return f"union({','.join(sorted(ids))})"

    def trivially_assignable_from(self, resolver: g.Resolver, right: TypeSpec) -> bool | None:
        if isinstance(right, NamedSpec):
            return None  # Not resolved yet
        right_types = right.types if isinstance(right, CombinationSpec) else [right]
        # Every type in right must be assignable to some type in self
        outer: list[bool | None] = []
        for right_t in right_types:
            inner = [trivially_assignable_equals(resolver, left_t, right_t) for left_t in self.types]
            if any(r is True for r in inner):
                outer.append(True)
            elif all(r is False for r in inner):
                outer.append(False)
            else:
                outer.append(None)
        if all(r is True for r in outer): return True
        if any(r is False for r in outer): return False
        return None

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver, any], any]) -> TypeSpec:
        new_self = dataclasses.replace(self, types=[tp.search_and_replace(resolver, replace) for tp in self.types])
        return langtools.cast(TypeSpec, replace(resolver, new_self))


@dataclass(frozen=True)
class TupleEntrySpec:
    name: str|None
    type: TypeSpec|None
    default: e.Expression|None = None

    def compile(self, resolver: g.Resolver) ->  tuple[TupleEntrySpec, list[s.Statement]]:
        new_type, new_statements1 = self.type.compile(resolver) if self.type else (None, [])
        new_default, new_statements2 = self.default.compile(resolver, new_type) if self.default else None, []
        return dataclasses.replace(self, type=new_type, default=new_default), new_statements1 + new_statements2

    def check(self, resolver: g.Resolver) -> list[Error]:
        err1 = self.type.check(resolver) if self.type else []
        err2 = self.default.check(resolver, self.type) if self.default else []
        return err1 + err2

    def generate(self, resolver: g.Resolver) -> cg_t.Type:
        return self.type.generate(resolver)

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver, any], any]) -> TupleEntrySpec:
        return dataclasses.replace(self,
            type=self.type.search_and_replace(resolver, replace) if self.type else None,
            default=self.default.search_and_replace(resolver, replace) if self.default else None)


@dataclass(frozen=True)
class TupleSpec(TypeSpec):
    entries: tuple[TupleEntrySpec, ...]

    def __post_init__(self):
        object.__setattr__(self, 'entries', tuple(self.entries))

    def is_concrete(self) -> bool:
        return all(x.type and x.type.is_concrete() for x in self.entries)

    def _compile(self, resolver: g.Resolver) ->  tuple[TupleSpec, list[s.Statement]]:
        new_entries, new_statements = pyast.utils.flatten_lists(x.compile(resolver) for x in self.entries)
        return dataclasses.replace(self, entries = new_entries), new_statements

    def check(self, resolver: g.Resolver) -> list[Error]:
        # All named parameters must come after all positional parameters
        max_unnamed_index = max((i for i, entry in enumerate(self.entries) if entry.name is None), default=0)
        min_named_index = min((i for i, entry in enumerate(self.entries) if entry.name is not None), default=len(self.entries))
        if max_unnamed_index > min_named_index:
            return [Error(self.line_ref, "Named parameters are not allowed before positional parameters")]
        return [y for x in self.entries for y in x.check(resolver)]

    def generate(self, resolver: g.Resolver) -> cg_t.Type:
        return cg_t.Struct(tuple((f"_{idx}", ent.type.generate(resolver)) for idx, ent in enumerate(self.entries)))

    def as_unique_id_str(self) -> str|None:
        ids = [x.type and x.type.as_unique_id_str() for x in self.entries]
        if not all(ids):
            return None
        else:
            return f"({','.join(ids)})"

    def trivially_assignable_from(self, resolver: g.Resolver, right: TypeSpec) -> bool | None:
        if isinstance(right, NamedSpec):
            return None # Not resolved yet
        if not isinstance(right, TupleSpec):
            return False
        if not len(self.entries) == len(right.entries):
            return False
        raw = [(trivially_assignable_equals(resolver, l.type, r.type), l.type)
               for l, r in zip(self.entries, right.entries)]
        # Structural False: a concrete (non-placeholder) left type that definitively doesn't fit.
        if any(res is False and not isinstance(ltype, GenericPlaceholderSpec) for res, ltype in raw):
            return False
        # All-placeholder-False: every element failed and none offered structural grounding.
        if raw and all(res is False for res, _ in raw):
            return False
        # Promote remaining placeholder-Falses to None (they may match after instantiation)
        # then apply the standard None/True rule.
        results = {None if (res is False and isinstance(ltype, GenericPlaceholderSpec)) else res
                   for res, ltype in raw}
        if None in results:
            return None
        return True

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver, any], any]) -> TypeSpec:
        new_self = dataclasses.replace(self,
            entries=[ent.search_and_replace(resolver, replace) for ent in self.entries])
        return langtools.cast(TypeSpec, replace(resolver, new_self))
