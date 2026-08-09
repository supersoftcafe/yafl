"""The type representations: what a YAFL type IS.

One frozen dataclass per kind of type (builtin, class, enum, tuple, callable,
union, placeholder, unresolved name), each carrying its own compile / check /
generate / assignability behaviour. The algorithms OVER these representations —
meet, refine, unification, substitution, trait-constraint solving — live in
pyast/typespec/algebra.py; `import pyast.typespec as t` exposes both halves.
"""
from __future__ import annotations

import dataclasses
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import langtools
import pyast.utils
from parsing.parselib import Error
import pyast.resolver as g
import pyast.statement as s
import pyast.expression as e

import codegen.typedecl as cg_t
import pyast.rewrite as rw

from parsing.tokenizer import LineRef


def collect_enum_leaves(stmt: s.EnumStatement) -> list[s.EnumStatement]:
    """Return all leaf EnumStatement nodes in declaration order (same order as all_leaf_names)."""
    if not stmt.variants:
        return [stmt] if stmt.has_param_list else []  # uninhabited → no leaf
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
        return [combined] if stmt.has_param_list else []  # uninhabited → no leaf
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
    # Provenance only (error messages). Two specs of the same shape are the
    # same type wherever they were written — substitution copies specs across
    # sites freely — so the source position is not part of type identity.
    line_ref: LineRef = field(compare=False)

    def is_concrete(self) -> bool:
        return False

    def _compile(self, resolver: g.Resolver) -> tuple[TypeSpec, list[s.Statement]]:
        raise NotImplementedError()

    def compile(self, resolver: g.Resolver) -> tuple[TypeSpec, list[s.Statement]]:
        type, statements = self._compile(resolver)
        if not isinstance(type, TypeSpec):
            raise ValueError(f"_compile returned a non-TypeSpec ({type(type).__name__}) — bug in the node's _compile")
        return type, statements

    def check(self, resolver: g.Resolver) -> list[Error]:
        raise NotImplementedError()

    def generate(self, resolver: g.Resolver) -> cg_t.Type:
        raise NotImplementedError()

    def trivially_assignable_from(self, resolver: g.Resolver, right: TypeSpec) -> bool | None:
        raise NotImplementedError()

    def as_unique_id_str(self) -> str|None:
        raise NotImplementedError()

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver, Any], Any]) -> TypeSpec:
        return replace(resolver, self)


def _holds_placeholder(spec: "TypeSpec") -> bool:
    """True when `spec` contains a GenericPlaceholderSpec ANYWHERE. The
    invariance checks need this because is_concrete() deliberately counts a
    placeholder as concrete — a template's `ListBuilder<T>` must compare as
    Unknown against `ListBuilder<Int>`, never as a rejection."""
    if isinstance(spec, GenericPlaceholderSpec):
        return True
    if isinstance(spec, (ClassSpec, EnumSpec, NamedSpec)):
        return any(_holds_placeholder(tp) for tp in spec.type_params)
    if isinstance(spec, CombinationSpec):
        return any(_holds_placeholder(m) for m in spec.types)
    if isinstance(spec, TupleSpec):
        return any(en.type is not None and _holds_placeholder(en.type) for en in spec.entries)
    return False


def trivially_assignable_equals(resolver: g.Resolver, left: TypeSpec | None, right: TypeSpec | None) -> bool | None:
    if left is None or right is None:
        return None
    # The empty type (a leafless enum like `Never`) is the bottom type: it has no
    # values, so a `Never`-typed expression — only ever reachable in dead code,
    # e.g. the `Error<_, Never>` arm of a match over a stream that cannot fail —
    # is assignable to any target.
    if isinstance(right, EnumSpec) and not right.valid_leaf_names:
        return True
    # Tuple-against-tuple goes straight to the tuple rule: arity may legally
    # differ when the uncovered fields carry defaults, so unwrapping a 1-tuple
    # first (below) would turn `(x = 5)` against `(x: Int, y: Int = 10)` into
    # a spurious element-vs-tuple mismatch.
    if isinstance(left, TupleSpec) and isinstance(right, TupleSpec):
        return left.trivially_assignable_from(resolver, right)
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
    # Set semantics of a union VALUE: it is one of its members, so a union on
    # the right is assignable iff EVERY member is. Needed since a branch's type
    # is the honest set union of its arms — `(T,C) | ((),C)` flowing into a
    # declared `(T|None, C)` decomposes memberwise (each arm's value is boxed
    # toward the declared type individually; the union never exists at runtime).
    # A union LEFT keeps its own memberwise rule (CombinationSpec handles it).
    if isinstance(right, CombinationSpec) and not isinstance(left, CombinationSpec):
        results = [trivially_assignable_equals(resolver, left, member)
                   for member in right.repr_members()]
        if any(r is False for r in results):
            return False
        return None if any(r is None for r in results) else True
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

        # Direction swaps for parameters. Compare the parameter lists DIRECTLY
        # (not via trivially_assignable_equals, which unwraps a 1-tuple to its
        # element): a parameter list's arity is significant, so a 1-parameter
        # callable must stay a length-1 TupleSpec, not collapse to its bare
        # element. Without this, an N-vs-1 arity mismatch whose lone parameter is
        # an as-yet-unresolved NamedSpec comes back undecided (None) instead of
        # False, so overload resolution can't reject the wrong-arity candidate on
        # its arguments alone and stalls waiting on the (here unknowable) result.
        params_result = right.parameters.trivially_assignable_from(resolver, self.parameters)

        if result_result == False or params_result == False:
            return False

        if result_result and params_result: # None or False
            return True

        return None

    def as_unique_id_str(self) -> str|None:
        p = self.parameters.as_unique_id_str()
        return p and f"f{p}"

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver, Any], Any]) -> TypeSpec:
        return rw.rewrite(self, replace, resolver,
            parameters=self.parameters.search_and_replace(resolver, replace),
            result=rw.opt(self.result, resolver, replace))


@dataclass(frozen=True)
class BuiltinSpec(TypeSpec):
    type_name: str

    def is_concrete(self) -> bool:
        return True

    def __translate(self) -> cg_t.Type|None:
        match self.type_name:
            case "str":
                return cg_t.DataPointer()
            case "int8":
                return cg_t.Int(8)
            case "int16":
                return cg_t.Int(16)
            case "int32":
                return cg_t.Int(32)
            case "int64":
                return cg_t.Int(64)
            case "bigint":
                return cg_t.DataPointer()
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
class LazyStubSpec(TypeSpec):
    """Type of a captured `[lazy]` stub pointer.  Used by the lambdas pass
    to type the closure-class field holding a captured stub reference.
    No source-level equivalent — emitted purely as a marker so the field
    generates to DataPointer regardless of the let's user-visible type
    (a `let [lazy] x: Int32` is stored as a stub pointer, not as int32_t).

    `target_type` is the user-visible value type so two distinct
    captures (e.g. `[lazy] x: Int` vs `[lazy] y: Int32`) participate in
    distinct symbol mangles via `as_unique_id_str` — even though their
    storage shape collapses to DataPointer at C level.
    """
    target_type: TypeSpec | None = None

    def is_concrete(self) -> bool:
        return self.target_type is None or self.target_type.is_concrete()

    def _compile(self, resolver: g.Resolver) -> tuple[TypeSpec, list[s.Statement]]:
        return self, []

    def check(self, resolver: g.Resolver) -> list[Error]:
        return self.target_type.check(resolver) if self.target_type else []

    def generate(self, resolver: g.Resolver) -> cg_t.Type:
        return cg_t.DataPointer()

    def trivially_assignable_from(self, resolver: g.Resolver, right: TypeSpec) -> bool | None:
        return isinstance(right, LazyStubSpec)

    def as_unique_id_str(self) -> str | None:
        inner = self.target_type.as_unique_id_str() if self.target_type else None
        return f"$lazystubptr${inner}" if inner else "$lazystubptr"

    def search_and_replace(self, resolver: g.Resolver, replace) -> TypeSpec:
        return rw.rewrite(self, replace, resolver,
            target_type=rw.opt(self.target_type, resolver, replace))


@dataclass(frozen=True)
class ArrayFieldSpec(TypeSpec):
    """Declared type of a `[final]` class's trailing variable-length array field:
    `array: ElemType[lengthField]`. `element` is the element type; `length_field`
    names the sibling `Int32` field giving the element count.

    It is never a free-standing value: the array lives as the object's inline
    trailing storage, described by the class's vtable (`array_el_size`,
    `array_len_offset`, `array_el_pointer_locations`). The field is *presented* as
    a function `(Int32): ElemType` — constructed by handing in such a function
    (whose results are tabulated into the storage) and read through a generated
    accessor method that lowers to a bounds-checked `ArrayReadExpression`. So this
    spec only ever appears as a class field's declared type; the class codegen
    handles its layout and the accessor/constructor handle its value side."""
    element: TypeSpec
    length_field: str

    def is_concrete(self) -> bool:
        return self.element.is_concrete()

    def _compile(self, resolver: g.Resolver) -> tuple[TypeSpec, list[s.Statement]]:
        element, statements = self.element.compile(resolver)
        return dataclasses.replace(self, element=element), statements

    def check(self, resolver: g.Resolver) -> list[Error]:
        return self.element.check(resolver)

    def generate(self, resolver: g.Resolver) -> cg_t.Type:
        # The class codegen lays out the trailing array storage; this returns the
        # *element* C type, which is what that layout (and the vtable's
        # array_el_size) is computed from.
        return self.element.generate(resolver)

    def trivially_assignable_from(self, resolver: g.Resolver, right: TypeSpec) -> bool | None:
        if not isinstance(right, ArrayFieldSpec) or self.length_field != right.length_field:
            return False
        return self.element.trivially_assignable_from(resolver, right.element)

    def as_unique_id_str(self) -> str | None:
        inner = self.element.as_unique_id_str()
        return f"$array${self.length_field}${inner}" if inner is not None else None

    def search_and_replace(self, resolver: g.Resolver, replace) -> TypeSpec:
        return rw.rewrite(self, replace, resolver,
            element=self.element.search_and_replace(resolver, replace))


@dataclass(frozen=True)
class ClassSpec(TypeSpec):
    name: str
    type_params: tuple[TypeSpec, ...] = ()

    def is_concrete(self) -> bool:
        return not self.type_params or all(tp.is_concrete() for tp in self.type_params)

    def _compile(self, resolver: g.Resolver) ->  tuple[TypeSpec, list[s.Statement]]:
        types = resolver.find_type(self.name)
        if len(types) == 1:
            type_params, statements = zip(*[tp.compile(resolver) for tp in self.type_params]) if self.type_params else ([],[])
            return dataclasses.replace(self, name=types[0].unique_name,  type_params=tuple(type_params)), [s for st in statements for s in st]
        return self, []

    def check(self, resolver: g.Resolver) -> list[Error]:
        tp_errors = [te for tp in self.type_params for te in tp.check(resolver)]
        types = resolver.find_type(self.name)
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
            clstype = langtools.checked_cast(ClassSpec, xtype)
            xstmt = resolver.find_type(clstype.name)[0].statement
            return langtools.checked_cast(s.ClassStatement, xstmt)

        if not '@' in self.name:
            return None # Left is not resolved yet
        if isinstance(right, NamedSpec):
            return None # Right is not resolved yet so Unknown
        if not isinstance(right, ClassSpec):
            return False # Right is resolved to something not a class so definitely False
        if self.name == right.name:
            # Same class — but generic type arguments are INVARIANT, so they
            # must match too. Comparing the NAME alone let List<B> pass where
            # List<A> was declared (both mangle to the same System::List@…),
            # and the first symptom was a codegen crash far from the fault.
            # Three-valued, as the contract requires: a placeholder or an
            # unresolved argument is Unknown, never a rejection — template
            # bodies are checked before monomorphisation grounds them.
            if len(self.type_params) != len(right.type_params):
                return False
            result: bool | None = True
            for lp, rp in zip(self.type_params, right.type_params):
                if lp == rp:
                    continue
                if (isinstance(lp, NamedSpec) or isinstance(rp, NamedSpec)
                        or _holds_placeholder(lp) or _holds_placeholder(rp)
                        or not lp.is_concrete() or not rp.is_concrete()):
                    result = None
                    continue
                # Not spec-EQUAL — but invariance means type EQUIVALENCE, which the
                # existing rules define with their deliberate leniencies (callable
                # parameter NAMES do not distinguish types). Mutually assignable
                # arguments are equivalent; anything else rejects.
                fwd = lp.trivially_assignable_from(resolver, rp)
                bwd = rp.trivially_assignable_from(resolver, lp)
                if fwd is True and bwd is True:
                    continue
                if fwd is None or bwd is None:
                    result = None
                    continue
                return False
            return result
        rcls = find_class(right)
        if rcls._all_parents is None:
            return None # Right parents aren't resolved yet so Unknown
        result = any(x.name == self.name for x in rcls._all_parents)
        return result

    def as_unique_id_str(self) -> str|None:
        return self.name

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver, Any], Any]) -> TypeSpec:
        return rw.rewrite(self, replace, resolver,
            type_params=rw.seq(self.type_params, resolver, replace))


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
        types = resolver.find_type(self.root_name)
        if len(types) == 1:
            target = types[0].statement
            if isinstance(target, s.EnumStatement) and target._enum_spec is not None:
                canonical = target._enum_spec
        return self, []

    def check(self, resolver: g.Resolver) -> list[Error]:
        # Field types are checked at their DECLARATION (the enum
        # statement's own check); a reference has nothing to recurse into.
        # The old stored-field recursion terminated only because frozen
        # copies bottomed out at snapshot depth — accidental, not designed.
        return []

    def generate(self, resolver: g.Resolver) -> cg_t.Type:
        from pyast import union_repr  # lazy: union_repr imports this module
        return union_repr.classify(self, resolver).ctype()

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
        if right.valid_leaf_names > self.valid_leaf_names or not (right.valid_leaf_names <= self.valid_leaf_names):
            return False
        # Same root — but generic type arguments are INVARIANT, and EnumSpec
        # EQUALITY deliberately excludes type_params (convergence metadata),
        # so assignability must compare them itself: pre-monomorphisation,
        # List<A> and List<B> share root and leaves and differ ONLY here.
        # Comparing the root alone let a List<B> pass where List<A> was
        # declared, and the first symptom was a codegen crash far from the
        # fault. Three-valued: placeholders and unresolved arguments are
        # Unknown, never a rejection — template bodies are checked before
        # monomorphisation grounds them.
        if len(self.type_params) != len(right.type_params):
            return None    # arity mismatch here is convergence noise, not proof
        result: bool | None = True
        for lp, rp in zip(self.type_params, right.type_params):
            if lp == rp:
                continue
            if (isinstance(lp, NamedSpec) or isinstance(rp, NamedSpec)
                    or _holds_placeholder(lp) or _holds_placeholder(rp)
                    or not lp.is_concrete() or not rp.is_concrete()):
                result = None
                continue
            # Not spec-EQUAL — but invariance means type EQUIVALENCE, which the
            # existing rules define with their deliberate leniencies (callable
            # parameter NAMES do not distinguish types). Mutually assignable
            # arguments are equivalent; anything else rejects.
            fwd = lp.trivially_assignable_from(resolver, rp)
            bwd = rp.trivially_assignable_from(resolver, lp)
            if fwd is True and bwd is True:
                continue
            if fwd is None or bwd is None:
                result = None
                continue
            return False
        return result

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver, Any], Any]) -> TypeSpec:
        # Do NOT recurse into all_fields: a recursive enum's all_fields
        # references the same EnumSpec, which would loop forever. all_fields
        # is maintained by EnumStatement.compile from the variants'
        # parameter lets — the AST-level recursion walks those lets via
        # the EnumStatement, so every type in all_fields is reached
        # through that other path.
        # DO recurse into type_params so that generics substitution can
        # replace GenericPlaceholderSpec(K) → Int, etc., preserving the
        # concrete type arguments for the generics redirect pass.
        # Change detection must be by IDENTITY: TypeSpec equality is
        # deliberately shallow (EnumSpec ignores type_params/all_fields), so
        # `!=` judged a substituted nested spec "unchanged" and kept the stale
        # one — the placeholder inside List<_N<T>>'s inner _N spec survived
        # call-site substitution exactly that way.
        # all_fields is deliberately NOT recursed (recursive enums self-reference
        # it); the AST walk reaches those types via EnumStatement's variant lets.
        # seq() reports change by the UNCHANGED signal, not by shallow ==/is.
        return rw.rewrite(self, replace, resolver,
            type_params=rw.seq(self.type_params, resolver, replace))

def enum_leaf_object_name(root_name: str, leaf_name: str) -> str:
    """The per-variant Object/vtable name for a complex-enum leaf.

    Specialised enum STATEMENTS keep their nested variant names (and the
    spec's all_leaf_names) unsuffixed, while redirected spec INSTANCES carry
    `__create_unique_name`-suffixed leaves. Per-variant codegen needs one
    canonical spelling: qualify the leaf with the root's `$generic$` suffix
    (the root was renamed by the same `__create_unique_name` with the same
    type args, so the suffix strings agree), leaving already-suffixed names
    untouched. Without this, every instantiation's variants collide on the
    bare leaf name — one struct layout overwriting another."""
    if '$generic$' in leaf_name or '$generic$' not in root_name:
        return leaf_name
    return leaf_name + '$generic$' + root_name.split('$generic$', 1)[1]


@dataclass(frozen=True)
class GenericPlaceholderSpec(TypeSpec):
    name: str
    is_linear: bool = False     # declared as `<[linear] T>` — body checked linearly

    def is_concrete(self) -> bool:
        return True

    def _compile(self, resolver: g.Resolver) -> tuple[TypeSpec, list[s.Statement]]:
        return self, []

    def check(self, resolver: g.Resolver) -> list[Error]:
        return []

    def generate(self, resolver: g.Resolver) -> cg_t.Type:
        raise RuntimeError("GenericPlaceholderSpec should be replaced with a concrete type")

    def trivially_assignable_from(self, resolver: g.Resolver, right: TypeSpec) -> bool | None:
        if isinstance(right, GenericPlaceholderSpec):
            return True if self.name == right.name else None
        # Self is a candidate-side placeholder being asked to accept a concrete
        # right-side. The placeholder hasn't been bound yet, so it *might*
        # accept it after substitution — return undecided rather than a
        # blanket False that would prematurely filter out a valid generic
        # candidate during overload resolution.
        return None

    def as_unique_id_str(self) -> str|None:
        return None # This is 'alias', not a concrete type.

    # Base class search_and_replace is sufficient: it calls replace(resolver, self),
    # which is where mappings like GenericPlaceholderSpec -> concrete type are applied.

@dataclass(frozen=True)
class NamedSpec(TypeSpec):
    name: str
    type_params: tuple[TypeSpec, ...] = ()

    def is_concrete(self) -> bool:
        return False

    def _compile(self, resolver: g.Resolver) ->  tuple[TypeSpec, list[s.Statement]]:
        types = resolver.find_type(self.name)
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
        types = resolver.find_type(self.name)
        if len(types) > 1:
            return [Error(self.line_ref, f"Ambiguous reference to '{self.name}'")]
        if len(types) == 1:
            return []
        return [Error(self.line_ref, f"Unresolved reference to '{self.name}'")]

    def generate(self, resolver: g.Resolver) -> cg_t.Type:
        raise RuntimeError("NamedSpec should be replaced with a concrete type")

    def trivially_assignable_from(self, resolver: g.Resolver, right: TypeSpec) -> bool | None:
        # When the right side is itself unresolved (NamedSpec) or a generic
        # placeholder, stay undecided — we don't have enough information yet.
        # When the right side is structurally concrete (BuiltinSpec, or a
        # ClassSpec/EnumSpec with an `@`-mangled name), resolve our own name
        # and delegate to the resolved kind's assignability rule. This lets
        # overload resolution narrow `add(1, 2)` definitively: a candidate
        # whose parameter is `NamedSpec("Set", ...)` can never accept a
        # `BuiltinSpec("bigint")` — no knowledge of T required.
        if isinstance(right, NamedSpec):
            return None
        types = resolver.find_type(self.name)
        if len(types) != 1:
            return None
        stmt = types[0].statement
        if isinstance(stmt, s.TypeAliasStatement):
            if stmt.type is not None and stmt.type.is_concrete():
                return stmt.type.trivially_assignable_from(resolver, right)
            return None
        if isinstance(stmt, s.ClassStatement):
            cls_spec = ClassSpec(self.line_ref, stmt.name, self.type_params)
            return cls_spec.trivially_assignable_from(resolver, right)
        if isinstance(stmt, s.EnumStatement) and stmt._enum_spec is not None:
            enum_spec = stmt._enum_spec
            if self.type_params:
                enum_spec = dataclasses.replace(enum_spec, type_params=self.type_params)
            return enum_spec.trivially_assignable_from(resolver, right)
        return None

    def as_unique_id_str(self) -> str|None:
        return None # This is 'alias', not a concrete type.


def _flatten_union_members(types) -> tuple[TypeSpec, ...]:
    """Associativity AND set semantics of `|`, applied structurally: a member
    that is itself a union contributes its members directly — `(Word|None)|E`
    IS `Word|None|E` — and a GROUND duplicate is the SAME member and is
    dropped, so `X|X` collapses (via the callers' singleton rule) to bare `X`.
    A duplicate must not survive as spelling: `union(X)` and `X` would carry
    the same set identity but different mangled names and exact-equality
    forms, splitting one type into two spellings (a phantom `E` pinned to a
    chain's own error is exactly how `E|JsonParseError` becomes `X|X`).
    Members whose identity is not yet ground (holes mid-fixpoint) are kept —
    the fixpoint re-flattens once they ground.
    """
    flat: list[TypeSpec] = []
    seen: set[str] = set()
    for tp in types:
        members = _flatten_union_members(tp.types) if isinstance(tp, CombinationSpec) else (tp,)
        for m in members:
            uid = m.as_unique_id_str()
            if uid is not None:
                if uid in seen:
                    continue
                seen.add(uid)
            flat.append(m)
    # An enum member SUBSUMED by another member of the same enum is the same
    # set of values: `E3 | EU` where EU narrows E3 IS `E3` (a match arm
    # returning a bare variant unioned with an arm returning the enum must
    # not mint a third member — downstream exhaustiveness and codegen index
    # the layout by member and would see a phantom). Only ground (resolved)
    # enums fold; the wider-or-equal member is kept.
    def subsumed(m: TypeSpec) -> bool:
        if not (isinstance(m, EnumSpec) and '@' in m.root_name):
            return False
        # Strict subset only: equal leaf sets share a uid and were deduped above.
        return any(o is not m
                   and isinstance(o, EnumSpec) and o.root_name == m.root_name
                   and m.valid_leaf_names < o.valid_leaf_names
                   for o in flat)
    folded = [m for m in flat if not subsumed(m)]
    return tuple(folded)


@dataclass(frozen=True)
class CombinationSpec(TypeSpec):
    types: tuple[TypeSpec, ...]

    def __post_init__(self):
        # The parser hands a list (parser.py __to_tagged_spec_or_simple_type);
        # a frozen dataclass hashes its fields, so a surviving list member
        # makes the whole spec unhashable — first seen as a TypeError from
        # generics' ref sets on files whose unions never recompile (unresolved
        # single-file runs). Same guard as TupleSpec.entries.
        object.__setattr__(self, 'types', tuple(self.types))

    def is_concrete(self) -> bool:
        return all(x.is_concrete() for x in self.types)

    def _compile(self, resolver: g.Resolver) ->  tuple[TypeSpec, list[s.Statement]]:
        new_types, new_errors = zip(*[x.compile(resolver) for x in self.types])
        flat = _flatten_union_members(new_types)
        errors = [x for stm in new_errors for x in stm]
        # A union keeps every distinct member, an uninhabited one included
        # (`Never | X` is not `X`; narrowing it still needs a match). Only a
        # genuine single-member union is just that bare member.
        if len(flat) == 1:
            return flat[0], errors
        return dataclasses.replace(self, types=flat), errors

    def check(self, resolver: g.Resolver) -> list[Error]:
        # A union is a set: a repeated member is not an error, it is the same
        # member (`String | String | Bool` is `String | Bool`). Identity folds
        # duplicates, so no duplicate-member diagnostic is needed here.
        return [y for x in self.types for y in x.check(resolver)]

    def generate(self, resolver: g.Resolver) -> cg_t.Type:
        from pyast import union_repr  # lazy: union_repr imports this module
        return union_repr.classify(self, resolver).ctype()

    def as_unique_id_str(self) -> str|None:
        # Flatten nested unions first (an inferred `A | (A|None)` is the set
        # `A | None`), so identity agrees with repr_members and a nested union
        # shares one id — and one representation — with its flat form.
        ids = [x.as_unique_id_str() for x in _flatten_union_members(self.types)]
        if not all(ids):
            return None
        # Set identity: order and repetition carry no meaning, so dedupe and
        # sort. `String|Bool`, `Bool|String` and `String|String|Bool` then share
        # one id, hence one representation.
        return f"union({','.join(sorted(set(ids)))})"

    def repr_members(self) -> tuple[TypeSpec, ...]:
        """The canonical member list for this union's in-memory representation:
        nested unions flattened and members deduped by structural id, first
        occurrence kept (unresolved members, with no id yet, are never folded).

        A union is a set, so a member repeated by substitution — `E | IOError`
        with `E = IOError` — must lay out as ONE slot and ONE tag, not two;
        otherwise boxing a value of that type cannot say which duplicate slot it
        belongs to. And a member that is ITSELF a union must contribute its
        members directly: an inferred type may nest (`A | (A|None)` from a match
        whose arms are a member and the union), and that must share one layout
        with the flat `A | None`. `types` is left exactly as written/substituted;
        every representation site (classify, match dispatch, widen, box) reads
        members through here, so the layout is built AND indexed from the same
        list. `as_unique_id_str` flattens the same way, so a laid-out union and
        the type's id always agree."""
        return _flatten_union_members(self.types)

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

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver, Any], Any]) -> TypeSpec:
        # Re-flatten after rebuilding: replacement can substitute a union for a
        # member (generics instantiating `T|E` with a union T), and lowering
        # passes assume flat member lists. Members are neither deduped nor
        # dropped here — a union keeps every member it is given; set identity and
        # the tag-by-uid representation handle repeats and uninhabited members.
        members, changed = [], False
        for tp in self.types:
            r = tp.search_and_replace(resolver, replace)
            members.append(tp if r is rw.UNCHANGED else r)
            changed = changed or r is not rw.UNCHANGED
        flat = _flatten_union_members(members)
        if len(flat) == 1:
            return flat[0]  # collapsed to a single member, already rewritten
        # A nested union expanding on substitution changes the member count even
        # when no single member "changed" in place.
        if not changed and len(flat) == len(self.types):
            return replace(resolver, self)
        rebuilt = dataclasses.replace(self, types=flat)
        res = replace(resolver, rebuilt)
        return rebuilt if res is rw.UNCHANGED else res


def bind_tuple_entries(declared, supplied_names: list[str | None]) -> list[int | None] | None:
    """How a supplied tuple's entries map onto a declared tuple's fields — the
    ONE spelling of named-field/default binding, shared by assignability,
    generic inference, the conversion engine and TupleExpression's field-wise
    convergence.

    Returns one value per DECLARED field: the index of the supplied entry that
    binds it, or None meaning "fill from this field's default". Returns None
    (no binding at all) when the tuples don't correspond: more entries than
    fields, a bare entry after a name-bound one, a doubly-bound field, or an
    unbound field with no default.

    Declared names match bare (a parameter's internal name carries an @hash
    suffix); supplied names are used as written. A supplied name binds only
    when it matches a declared field. Tuples whose names don't overlap the
    declared names at all keep the structural semantics — same length binds
    positionally, names ignored — so a `(dir, entries)` value still pipes into
    `(d, acc)` parameters, and a function value's parameter names never
    participate."""
    declared = list(declared)
    if len(supplied_names) > len(declared):
        return None
    bare = [g.bare_name(en.name) if en.name is not None else None for en in declared]
    if (len(supplied_names) == len(declared)
            and not any(sn is not None and sn in bare for sn in supplied_names)):
        return list(range(len(declared)))
    slots: list[int | None] = [None] * len(declared)
    bound = [False] * len(declared)
    seen_matched_name = False
    for i, sname in enumerate(supplied_names):
        if sname is not None and sname in bare:
            j = bare.index(sname)
            if bound[j]:
                return None
            slots[j] = i
            bound[j] = True
            seen_matched_name = True
        else:
            # Positional. An entry whose name matches nothing is treated
            # positionally too (an incidental name on a value's field, or an
            # unknown keyword — the latter is reported by TupleExpression.check).
            if sname is None and seen_matched_name:
                return None  # bare positional after a name-bound entry
            if i >= len(declared) or bound[i]:
                return None
            slots[i] = i
            bound[i] = True
    if any(not b and en.default is None for b, en in zip(bound, declared)):
        return None
    return slots


def default_value_errors(default: "e.Expression | None", resolver: g.Resolver,
                         line_ref: LineRef, what: str) -> list[Error]:
    """A tuple-field/parameter default must be a literal or a `[const]` value:
    nothing with captures, effects, or an evaluation order — a default is
    cloned into every site that omits the field."""
    if default is None:
        return []
    if e.is_literal_value(default):
        return []
    default = e.strip_conversions(default)
    if isinstance(default, e.NamedExpression):
        datas = resolver.find_data(default.name)
        if (len(datas) == 1
                and "const" in getattr(datas[0].statement, "attributes", {})):
            return []
    return [Error(line_ref, f"a {what} default must be a literal or a [const] value")]


@dataclass(frozen=True)
class TupleEntrySpec:
    name: str|None
    type: TypeSpec|None
    default: e.Expression|None = None

    def compile(self, resolver: g.Resolver) ->  tuple[TupleEntrySpec, list[s.Statement]]:
        new_type, new_statements1 = self.type.compile(resolver) if self.type else (None, [])
        new_default, new_statements2 = self.default.compile(resolver, new_type) if self.default else (None, [])
        return dataclasses.replace(self, type=new_type, default=new_default), new_statements1 + new_statements2

    def check(self, resolver: g.Resolver) -> list[Error]:
        err1 = self.type.check(resolver) if self.type else []
        err2 = self.default.check(resolver, self.type) if self.default else []
        err3 = default_value_errors(self.default, resolver,
                                    self.type.line_ref if self.type else LineRef("", 0, 0),
                                    "tuple field")
        return err1 + err2 + err3

    def generate(self, resolver: g.Resolver) -> cg_t.Type:
        return self.type.generate(resolver)

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver, Any], Any]) -> TupleEntrySpec:
        return rw.rebuild(self,
            type=rw.opt(self.type, resolver, replace),
            default=rw.opt(self.default, resolver, replace))


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
        # Fields correspond via the shared binding: positional, then by name,
        # unbound fields covered by their defaults. Only the bound pairs are
        # type-compared — a default's type was checked at declaration.
        binding = bind_tuple_entries(self.entries, [en.name for en in right.entries])
        if binding is None:
            return False
        raw = [(trivially_assignable_equals(resolver, l.type, right.entries[b].type), l.type)
               for l, b in zip(self.entries, binding) if b is not None]
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

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver, Any], Any]) -> TypeSpec:
        return rw.rewrite(self, replace, resolver,
            entries=rw.seq(self.entries, resolver, replace))
