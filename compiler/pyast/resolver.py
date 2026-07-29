from __future__ import annotations

from enum import Enum
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

import codegen.typedecl as cg_t
import codegen.param as cg_p
import codegen.ops as cg_o

import pyast.statement as s
import pyast.typespec as t


@dataclass(frozen=True)
class Bag[T]:
    """A found set plus whether that set is COMPLETE — whether the search saw
    everything it needed to. Every `find` over a resolver returns one of these,
    and a name is only ever committed to a candidate from a *complete* bag: an
    incomplete one may still be missing the candidate that should win, once the
    thing that blocked the search (an unresolved `[where]` alias, or a NamedSpec
    encountered anywhere along the way) resolves on a later compile pass.

    Combining bags with `+` unions the items and ANDs completeness — a result is
    complete only when every part that fed it was. This is also the value type
    of the `Statements` by-name index. Two shared empties cover the common ends:
    `EMPTY` (nothing found, and that is the whole story) and `INCOMPLETE`
    (nothing found *yet* — the search was blocked, so absence proves nothing)."""
    items: tuple[T, ...] = ()
    complete: bool = True

    def __add__(self, other: "Bag[T] | Iterable[T]") -> "Bag[T]":
        if isinstance(other, Bag):
            return Bag(self.items + other.items, self.complete and other.complete)
        return Bag(self.items + tuple(other), self.complete)

    def __radd__(self, other: "Iterable[T]") -> "Bag[T]":
        return Bag(tuple(other) + self.items, self.complete)

    def __iter__(self): return iter(self.items)
    def __len__(self) -> int: return len(self.items)
    def __getitem__(self, index): return self.items[index]
    def __bool__(self) -> bool: return bool(self.items)


# A Bag is a sequence of its items (with completeness riding alongside), so the
# many `match resolver.find_*(): case [x]:` sites treat it exactly as they did
# the old list. Registering it keeps those sequence patterns working.
Sequence.register(Bag)


# The shared empties (see Bag): found-nothing-and-that's-final vs found-nothing-
# -yet-because-blocked. Everything else is built by `+`-ing bags together.
EMPTY: Bag = Bag((), True)
INCOMPLETE: Bag = Bag((), False)


class FunctionBuilder:
    stack_vars: dict[str, cg_t.Type]
    operations: list[cg_o.Op]

    def __init__(self):
        self.stack_vars = dict()
        self.operations = list()

    def add_op(self, op: cg_o.Op):
        self.operations.append(op)

    def add_var(self, vtype: cg_t.Type) -> str:
        name = f"var_{len(self.stack_vars)}"
        self.stack_vars[name] = vtype
        return name


@dataclass(frozen=True)
class OperationBundle:
    stack_vars: tuple[cg_p.StackVar, ...] = ()
    operations: tuple[cg_o.Op, ...] = ()
    result_var: cg_p.RParam|None = None
    # `[tail]`-loop back-edges produced while generating this subtree: each is
    # `(recur-exit label, per-parameter phi-input vars)`, flowing up to the
    # enclosing LoopExpression which consumes them to build its head Phi. The
    # referenced names embed the mangled ('@'-bearing) function name, so they
    # are path-immune (with_prefix leaves them alone) and need no renaming.
    recur_sources: tuple[tuple[str, tuple[cg_p.RParam, ...]], ...] = ()
    # `return`-statement block exits produced while generating this subtree:
    # each is `(exit label, value)` for one ReturnStatement, flowing up to the
    # enclosing BlockExpression which consumes them into its end Phi. The names
    # embed the block's '@'-bearing tag, so they are path-immune exactly like
    # recur_sources. `value` is None for a `return` in a unit-typed block.
    exit_sources: tuple[tuple[str, cg_p.RParam | None], ...] = ()

    def with_prefix(self, prefix: str|int) -> OperationBundle:
        """Mark this bundle as living at structural path component `prefix`
        relative to the surrounding bundle. Every internal StackVar and
        Label name gets `{prefix}/` prepended; externally-qualified names
        (containing '@') and `this` are left alone.

        The prefix is a *position*, not a counter. The same AST shape
        composed the same way produces the same names — no monotonic
        counter threads through generation. Integer prefixes are accepted
        for backward compatibility with call sites that previously passed
        position-as-int; they are rendered without further decoration.
        """
        if isinstance(prefix, int):
            prefix = str(prefix)
        if not prefix:
            # Empty prefix is a no-op: callers that previously passed "" to
            # collapse path structure into a flat `uvar_N` sequence are now
            # explicitly opting out of any structural mark.
            return self

        def attach(name: str) -> str:
            if "@" in name or name == "this":
                return name
            return f"{prefix}/{name}"

        var_renames = {sv.name: attach(sv.name) for sv in self.stack_vars}
        label_renames = {op.name: attach(op.name) for op in self.operations if isinstance(op, cg_o.Label)}
        renames = var_renames | label_renames
        if not renames:
            return self
        return OperationBundle(
            stack_vars=tuple(sv.rename_vars(renames) for sv in self.stack_vars),
            operations=tuple(op.rename_vars(renames) for op in self.operations),
            result_var=self.result_var and self.result_var.rename_vars(renames),
            recur_sources=self.recur_sources,   # path-immune; carried through
            exit_sources=self.exit_sources)     # path-immune; carried through

    def __add__(self, other: OperationBundle) -> OperationBundle:
        return OperationBundle(
            self.stack_vars + other.stack_vars,
            self.operations + other.operations,
            other.result_var,
            self.recur_sources + other.recur_sources,
            self.exit_sources + other.exit_sources)


class ResolvedScope(Enum):
    GLOBAL = 1
    MEMBER = 2
    LOCAL  = 3
    TRAIT  = 4   # Found an interface member that must be treated as a trait reference during lowering


@dataclass(frozen=True)
class Resolved[T]:
    unique_name: str
    statement: T
    scope: ResolvedScope
    trait_scope: t.TypeSpec|None = None     # We need this for mapping local types to target class types
    owner_class: s.ClassStatement|None = None    # We need this for the generic type declarations
    # Placeholder names owned by the GENERIC `[ambient]` instance whose
    # interface pattern produced this candidate (the instance's T in
    # Sized<List<T>>). The use site may bind them, from the argument or the
    # expected type — the same rule as a generic function candidate's own
    # type params. Empty for every other provenance; caller placeholders
    # reaching a candidate through trait_scope stay strict.
    instance_params: tuple[str, ...] = ()


class Resolver:
    def find_type(self, name: str) -> "Bag[Resolved[s.TypeStatement]]":
        return EMPTY

    def find_data(self, name: str) -> "Bag[Resolved[s.DataStatement]]":
        return EMPTY

    def get_traits(self) -> list[s.LetStatement]:
        return []

    # The suggested parameter shape for the function `name` (its unique `@`-name),
    # gathered from the previous pass's call sites — a TupleSpec whose entries may
    # be partial (a hole where no call site pinned that parameter, or where call
    # sites disagreed). None when nothing was suggested. Read-only: a declared
    # parameter type always overrides, so this only fills holes. See
    # compiler.__collect_param_suggestions (path 3 of the inference model).
    def get_param_suggestion(self, name: str) -> "t.TupleSpec | None":
        return None

    def get_implicit_where_specs(self, scopes: set[str] | None = None) -> list[t.TypeSpec]:
        return []

    # Every in-scope `instance [ambient]` record (the desugared
    # `[trait,ambient]` let): its members join name resolution as pure
    # AVAILABILITY — no constraint on anything of the caller's. Same
    # import-scope filtering as get_implicit_where_specs.
    def get_ambient_traits(self, scopes: set[str] | None = None) -> "list[s.LetStatement]":
        return []

    def get_discriminators(self) -> dict[str, int]:
        return {}

    def get_optimization_level(self) -> int:
        return 0

    # The innermost in-progress [tail] loop's frame (read-only context for a
    # nested RecurExpression), or None outside any loop. Opaque here — only the
    # loop/recur expression nodes interpret it.
    def get_loop_frame(self) -> object | None:
        return None

    # The innermost in-progress BlockExpression's frame (read-only context for
    # a nested ReturnStatement, which branches to the block's end), or None
    # outside any block. Opaque here — only block/return nodes interpret it.
    def get_block_frame(self) -> object | None:
        return None


class DelegatingResolver(Resolver):
    """A resolver layered over a `parent`, forwarding every query to it by
    default. Each scope a compilation enters (a set of imports, a function's
    type params, a block's locals, the active loop/block frame) adds one such
    layer that overrides only the single aspect it changes — see the subclasses
    below. Centralising the pass-through here keeps each layer's intent visible:
    what it declares is exactly what it does."""
    _parent: Resolver

    def __init__(self, parent: Resolver):
        self._parent = parent

    def find_type(self, name: str) -> list[Resolved[s.TypeStatement]]:
        return self._parent.find_type(name)

    def find_data(self, name: str) -> list[Resolved[s.DataStatement]]:
        return self._parent.find_data(name)

    def get_traits(self) -> list[s.LetStatement]:
        return self._parent.get_traits()

    def get_param_suggestion(self, name: str) -> "t.TypeSpec | None":
        return self._parent.get_param_suggestion(name)

    def get_implicit_where_specs(self, scopes: set[str] | None = None) -> list[t.TypeSpec]:
        return self._parent.get_implicit_where_specs(scopes)

    def get_ambient_traits(self, scopes: set[str] | None = None) -> "list[s.LetStatement]":
        return self._parent.get_ambient_traits(scopes)

    def get_discriminators(self) -> dict[str, int]:
        return self._parent.get_discriminators()

    def get_optimization_level(self) -> int:
        return self._parent.get_optimization_level()

    def get_loop_frame(self) -> object | None:
        return self._parent.get_loop_frame()

    def get_block_frame(self) -> object | None:
        return self._parent.get_block_frame()


def simple_name(name: str) -> str:
    return name.rpartition('@')[0] or name

def bare_name(name: str) -> str:
    """The unqualified simple name: `@`-hash suffix and namespace path both
    stripped. What diagnostics print and `_`-prefix conventions test against."""
    return simple_name(name).rpartition("::")[2]

def match_name(left: str, right: str) -> bool:
    return simple_name(left) == simple_name(right)

# Match a candidate statement name (`candidate`) against a single lookup
# `query` — true if they're identical, or if `candidate` is a fully-qualified
# variant of `query` (i.e. starts with `query@`).
def name_matches(candidate: str, query: str) -> bool:
    return candidate == query or candidate.startswith(query + '@')


def _name_prefixes(name: str) -> list[str]:
    parts = name.split('@')
    return ['@'.join(parts[:i+1]) for i in range(len(parts))]






class Statements:
    """An ordered collection of top-level statements that carries its own
    by-name lookup index, built once at construction.

    Iterates like a list of statements (top-level, in order); subscripts and
    `.get()` like a dict of name -> tuple of statements sharing that name. The
    index is keyed by every name PREFIX (`_name_prefixes`), so a resolver's
    prefix-match lookup is a plain dict hit — the index that `ResolverRoot`
    used to rebuild on every construction lives here and is built once per
    collection. Nested enum variants are indexed too (so a variant name
    resolves) but are not part of iteration. `traits` and `where_aliases` —
    the two other collection-wide scans the resolver needs — are precomputed.

    A changed statement set is a *new* `Statements` built from the new
    contents, so there is never a stale index to reason about across passes.
    """
    __slots__ = ("_ordered", "_index", "traits", "where_aliases")

    def __init__(self, statements: "Iterable[s.Statement]") -> None:
        ordered = tuple(statements)
        index: dict[str, list[s.Statement]] = {}
        traits: list[s.LetStatement] = []
        where_aliases: list[s.TypeAliasStatement] = []
        for st in ordered:
            # Only named statements are indexed; structural statements (imports,
            # namespace markers) carry no name — matching the old ResolverRoot,
            # which indexed only Type/Data statements.
            if not isinstance(st, s.NamedStatement):
                continue
            for key in _name_prefixes(st.name):
                index.setdefault(key, []).append(st)
            if isinstance(st, s.EnumStatement):
                Statements.__index_variants(st.variants, index)
            elif isinstance(st, s.LetStatement) and 'trait' in st.attributes:
                traits.append(st)
            elif isinstance(st, s.TypeAliasStatement) and 'where' in st.attributes:
                where_aliases.append(st)
        self._ordered: tuple[s.Statement, ...] = ordered
        self._index: dict[str, tuple[s.Statement, ...]] = {k: tuple(v) for k, v in index.items()}
        self.traits: tuple[s.LetStatement, ...] = tuple(traits)
        self.where_aliases: tuple[s.TypeAliasStatement, ...] = tuple(where_aliases)

    @staticmethod
    def __index_variants(variants: "list[s.EnumStatement]", index: dict) -> None:
        for v in variants:
            for key in _name_prefixes(v.name):
                index.setdefault(key, []).append(v)
            Statements.__index_variants(v.variants, index)

    def __iter__(self): return iter(self._ordered)
    def __len__(self) -> int: return len(self._ordered)
    def __bool__(self) -> bool: return bool(self._ordered)
    # The by-name index is exhaustive over this collection, so a lookup is
    # always a COMPLETE bag — incompleteness only ever enters via the trait
    # finder meeting an unresolved alias, never from a plain name miss here.
    def __getitem__(self, name: str) -> "Bag[s.Statement]": return Bag(self._index.get(name, ()))
    def get(self, name: str) -> "Bag[s.Statement]": return Bag(self._index.get(name, ()))

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Statements):
            return self._ordered == other._ordered
        return NotImplemented

    __hash__ = None  # ordered contents are the identity; not hashable

    def __add__(self, other: "Iterable[s.Statement]") -> "Statements":
        return Statements(self._ordered + tuple(other))


def as_statements(statements: "Iterable[s.Statement] | Statements") -> Statements:
    """Wrap a plain iterable in `Statements`, or pass a `Statements` through —
    so a collection is indexed at most once as it flows through the pipeline."""
    return statements if isinstance(statements, Statements) else Statements(statements)


class ResolverRoot(Resolver):
    def __init__(self, statements: "Iterable[s.Statement] | Statements",
                 param_suggestions: "dict[str, t.TupleSpec] | None" = None) -> None:
        # The collection carries its own index; wrapping a `Statements` reuses
        # it, wrapping a list builds it once here.
        self.__statements = as_statements(statements)
        # {function unique-name: suggested param TupleSpec}, computed once per
        # compile pass from the previous pass's call sites (path 3).
        self.__param_suggestions = param_suggestions or {}

    def find_type(self, name: str) -> "Bag[Resolved[s.TypeStatement]]":
        return Bag(tuple(Resolved(st.name, st, ResolvedScope.GLOBAL)
                for st in self.__statements[name] if isinstance(st, s.TypeStatement)))

    def find_data(self, name: str) -> "Bag[Resolved[s.DataStatement]]":
        return Bag(tuple(Resolved(st.name, st, ResolvedScope.GLOBAL)
                for st in self.__statements[name] if isinstance(st, s.DataStatement)))

    def get_traits(self) -> list[s.LetStatement]:
        return list(self.__statements.traits)

    def get_param_suggestion(self, name: str) -> "t.TupleSpec | None":
        return self.__param_suggestions.get(name)

    def get_implicit_where_specs(self, scopes: set[str] | None = None) -> list[t.TypeSpec]:
        if not scopes:
            return []
        # Every in-scope [where] alias type, resolved or not: the trait finder
        # must see an unresolved one (still a NamedSpec) to register its trait
        # set as not-yet-complete, rather than treat it as absent and commit a
        # name against a search that was actually blocked.
        return [st.type for st in self.__statements.where_aliases
                if st.name.rpartition('::')[0] in scopes]

    def get_ambient_traits(self, scopes: set[str] | None = None) -> "list[s.LetStatement]":
        if not scopes:
            return []
        return [st for st in self.__statements.traits
                if 'ambient' in st.attributes
                and st.name.rpartition('::')[0] in scopes]


class AddScopeResolution(DelegatingResolver):
    __scopes: tuple[str, ...]
    # Result caches — short-lived (this resolver lives for one statement-scope
    # walk) but a single walk does ~1k–10k lookups, most of them repeats.
    __type_cache: dict[str, list[Resolved[s.TypeStatement]]]
    __data_cache: dict[str, list[Resolved[s.DataStatement]]]

    def __init__(self, parent: Resolver, scopes: set[str] | s.ImportGroup | None):
        super().__init__(parent)
        if scopes is None:
            self.__scopes = ()
        elif isinstance(scopes, s.ImportGroup):
            self.__scopes = tuple(x.path for x in scopes.imports)
        else:
            self.__scopes = tuple(scopes)
        self.__type_cache = {}
        self.__data_cache = {}

    def find_type(self, name: str) -> list[Resolved[s.TypeStatement]]:
        cached = self.__type_cache.get(name)
        if cached is not None:
            return cached
        result = self._parent.find_type(name)
        if "::" not in name and "@" not in name:
            for scope in self.__scopes:
                result = result + self._parent.find_type(f"{scope}::{name}")
        self.__type_cache[name] = result
        return result

    def find_data(self, name: str) -> list[Resolved[s.DataStatement]]:
        cached = self.__data_cache.get(name)
        if cached is not None:
            return cached
        result = self._parent.find_data(name)
        if "::" not in name and "@" not in name:
            for scope in self.__scopes:
                result = result + self._parent.find_data(f"{scope}::{name}")
        self.__data_cache[name] = result
        return result

    def get_implicit_where_specs(self, scopes: set[str] | None = None) -> list[t.TypeSpec]:
        own = set(self.__scopes)
        merged = own if scopes is None else (own | scopes)
        return self._parent.get_implicit_where_specs(merged)

    def get_ambient_traits(self, scopes: set[str] | None = None) -> "list[s.LetStatement]":
        own = set(self.__scopes)
        merged = own if scopes is None else (own | scopes)
        return self._parent.get_ambient_traits(merged)


class ResolverType(DelegatingResolver):
    __find: Callable[[str], list[Resolved[s.TypeStatement]]]
    __cache: dict[str, list[Resolved[s.TypeStatement]]]

    def __init__(self, parent: Resolver, find: Callable[[str], list[Resolved[s.TypeStatement]]]):
        super().__init__(parent)
        self.__find = find
        self.__cache = {}

    def find_type(self, name: str) -> "Bag[Resolved[s.TypeStatement]]":
        cached = self.__cache.get(name)
        if cached is not None:
            return cached
        found = self.__find(name)
        result = self._parent.find_type(name) + (found if isinstance(found, Bag) else Bag(tuple(found)))
        self.__cache[name] = result
        return result


class ResolverData(DelegatingResolver):
    __find: Callable[[str], list[Resolved[s.DataStatement]]]
    __cache: dict[str, list[Resolved[s.DataStatement]]]

    def __init__(self, parent: Resolver, find: Callable[[str], list[Resolved[s.DataStatement]]]):
        super().__init__(parent)
        self.__find = find
        self.__cache = {}

    def find_data(self, name: str) -> list[Resolved[s.DataStatement]]:
        cached = self.__cache.get(name)
        if cached is not None:
            return cached
        # Lexical shadowing: a name bound at this scope hides the same name
        # in any enclosing scope. Without this, a lambda parameter named `io`
        # inside a function with a parameter also named `io` triggers an
        # ambiguity error ("Resolved too many io") instead of shadowing.
        own = self.__find(name)
        own = own if isinstance(own, Bag) else Bag(tuple(own))
        result = own if own else self._parent.find_data(name)
        self.__cache[name] = result
        return result


class ResolverTraitData(DelegatingResolver):
    """Adds the in-scope trait / interface operators as ADDITIONAL data
    candidates — they JOIN the enclosing scope, never shadow it (only a local
    binding shadows), so a free `+` and the built-in `+` resolve together and
    are told apart by argument type. Established once, at a top-level function
    or let (see _initialiser_resolver); an inner function carries no `where` and
    never adds its own, inheriting this scope lexically from its owner, so a name
    resolves to the same operators whether used at top level or nested."""
    __find_trait: Callable[[Resolver, str], "Bag[Resolved[s.DataStatement]]"]
    __cache: dict[str, "Bag[Resolved[s.DataStatement]]"]

    def __init__(self, parent: Resolver, find_trait: Callable[[Resolver, str], "Bag[Resolved[s.DataStatement]]"]):
        super().__init__(parent)
        self.__find_trait = find_trait
        self.__cache = {}

    def find_data(self, name: str) -> "Bag[Resolved[s.DataStatement]]":
        cached = self.__cache.get(name)
        if cached is not None:
            return cached
        result = self._parent.find_data(name) + self.__find_trait(self._parent, name)
        self.__cache[name] = result
        return result


class ResolverDiscriminators(DelegatingResolver):
    __discriminators: dict[str, int]
    __optimization_level: int

    def __init__(self, parent: Resolver, discriminators: dict[str, int], optimization_level: int = 0):
        super().__init__(parent)
        self.__discriminators = discriminators
        self.__optimization_level = optimization_level

    def get_discriminators(self) -> dict[str, int]:
        return self.__discriminators

    def get_optimization_level(self) -> int:
        return self.__optimization_level


class ResolverLoop(DelegatingResolver):
    """Carries the innermost in-progress `[tail]` loop's (immutable) frame so a
    nested RecurExpression can find its loop head and parameter ctypes. Replaces
    a former module-level generation stack — no mutable cross-call state."""
    __frame: object

    def __init__(self, parent: Resolver, frame: object):
        super().__init__(parent)
        self.__frame = frame

    def get_loop_frame(self) -> object | None:
        return self.__frame


class ResolverBlock(DelegatingResolver):
    """Carries the innermost in-progress BlockExpression's (immutable) frame so a
    nested ReturnStatement can find the block's end label and result type and
    branch there. The block-exit analogue of ResolverLoop: the frame flows
    *down* (read-only), the exit phi-sources flow *up* via
    OperationBundle.exit_sources, so no mutable state crosses calls. A nested
    block shadows an outer one, so `return` always targets the nearest block."""
    __frame: object

    def __init__(self, parent: Resolver, frame: object):
        super().__init__(parent)
        self.__frame = frame

    def get_block_frame(self) -> object | None:
        return self.__frame

