"""Hints: what compile learned about untyped names.

A load of an untyped let records the type its receiver expected; a match over
one records its arm types. Hints flow up out of compile, keyed by unique name,
and the function or lambda that owns a parameter reads its type off them.
"""
from __future__ import annotations

from dataclasses import dataclass

import pyast.resolver as g
import pyast.typespec as t


@dataclass(frozen=True)
class Hint:
    spec: t.TypeSpec
    # True: "must accept this" (a match arm). False: "must fit here".
    lower: bool = False


Hints = dict[str, tuple[Hint, ...]]

# A name that has not resolved yet: its uses may still say something.
UNSETTLED = "$unsettled"


def unsettled() -> Hints:
    return {UNSETTLED: ()}


def of(name: str, spec: t.TypeSpec, lower: bool = False) -> Hints:
    return {name: (Hint(spec, lower),)}


def merge(*parts: Hints) -> Hints:
    out: Hints = {}
    for part in parts:
        for name, hs in part.items():
            out[name] = out.get(name, ()) + hs
    return out


def without(hints: Hints, names: set[str], placeholders: set[str] = frozenset()) -> Hints:
    """Drop `names`, and any hint mentioning one of `placeholders`."""
    out: Hints = {}
    for name, hs in hints.items():
        kept = tuple(h for h in hs if not t.placeholder_names_in(h.spec) & placeholders)
        if name not in names and (kept or not hs):
            out[name] = kept
    return out


def registers(data: g.Resolved, expected: t.TypeSpec | None) -> bool:
    """Does a load of `data`, expecting `expected`, leave a hint?"""
    return (expected is not None
            and data.scope == g.ResolvedScope.LOCAL
            and is_untyped_let(data.statement))


def load_hint(resolver: g.Resolver, expr, expected: t.TypeSpec | None) -> Hints:
    """The hint a load of `expr` leaves when its receiver expects `expected`."""
    from pyast.expression.access import NamedExpression
    if not isinstance(expr, NamedExpression):
        return {}
    datas = resolver.find_data(expr.name)
    if len(datas) != 1 or not registers(datas[0], expected):
        return {}
    return of(datas[0].unique_name, expected)


def is_untyped_let(stmt) -> bool:
    import pyast.statement as s
    return (isinstance(stmt, s.LetStatement)
            and (stmt.declared_type is None or stmt.type_inferred))


def untyped_param_errors(fn, scope: g.Resolver) -> list:
    """An error for each parameter of `fn` its body never typed, with the clue
    its hints give. `scope` is the scope the body sees."""
    from parsing.parselib import Error
    untyped = [tgt for tgt in fn.parameters.targets if tgt.get_type() is None]
    if not untyped:
        return []
    found = fn.body.compile(scope, fn.return_type)[2] if fn.body is not None else {}

    def clue(tgt) -> str:
        if UNSETTLED in found:
            return UNRESOLVED
        return verdict(found.get(tgt.name, ()), scope).clue

    return [Error(tgt.line_ref,
                  f"Parameter '{g.simple_name(tgt.name)}' of '{g.simple_name(fn.name)}' "
                  f"has no type and could not be inferred — {clue(tgt)}")
            for tgt in untyped]


# ── the verdict ─────────────────────────────────────────────────────────────

NO_USE = "no use in its body determines it"
UNRESOLVED = "a name in its body has not resolved yet"


@dataclass(frozen=True)
class Verdict:
    # Exactly one is set.
    type: t.TypeSpec | None = None
    clue: str | None = None


def verdict(hints: tuple[Hint, ...], resolver: g.Resolver) -> Verdict:
    usable = [h for h in hints if _complete(h.spec, resolver)]
    if not usable:
        if not hints:
            return Verdict(clue=NO_USE)
        return Verdict(clue="its uses leave it incomplete — " + _listed(h.spec for h in hints))
    uppers = [h.spec for h in usable if not h.lower]
    lowers = [h.spec for h in usable if h.lower]
    upper = (_narrowest(uppers, resolver) or t.converge(uppers, resolver)) if uppers else None
    if uppers and upper is None:
        return Verdict(clue="its uses require " + _listed(uppers, " and "))
    lower = t.converge(lowers, resolver) if lowers else None
    if lowers and lower is None:
        return Verdict(clue="its match arms share no type — " + _listed(lowers))
    if lower is None or upper is None:
        answer = upper if lower is None else lower
    elif lower == upper or t.trivially_assignable_equals(resolver, upper, lower) is True:
        answer = lower
    else:
        # The upper bound RECEIVES the lower one: merge them (List spelled
        # without arguments below, `List<Int>` above, is `List<Int>`). Until
        # the remaining callers move to merge, a contradiction still falls
        # back to the common parent.
        merged, _bindings, errors = t.merge(upper, lower, {}, resolver)
        answer = merged if merged is not None and not errors else t.converge([lower, upper], resolver)
    if answer is None:
        return Verdict(clue="its uses require " + _listed(uppers, " and "))
    return Verdict(type=answer)


def _complete(spec: t.TypeSpec, resolver: g.Resolver) -> bool:
    open_result = isinstance(spec, t.CallableSpec) and spec.result is None
    return spec.is_concrete() and not open_result and not t.has_free_placeholders(spec, resolver)


def _narrowest(uppers: list[t.TypeSpec], resolver: g.Resolver) -> t.TypeSpec | None:
    for cand in uppers:
        if all(x == cand or t.trivially_assignable_equals(resolver, x, cand) is True for x in uppers):
            return cand
    return None


def _listed(specs, sep: str = ", ") -> str:
    from pyast.expression.call import _type_str
    return sep.join(sorted(set(map(_type_str, specs))))
