"""Function PARAMETER types, inferred from the BODY.

A parameter that declares no type takes it from what the body DOES with it —
the implementer's "it's obvious, I shouldn't have to write it again". Never
from the callers: a function means the same thing wherever it is called, so
the evidence is the one thing every caller shares.

Uses speak in two directions:

  * UPPER bounds — "x must FIT here": x passed to a call whose overloads narrow
    to one reading, or returned against a declared result type.
  * LOWER bounds — "x must ACCEPT these": the arm types of `match(x)`.

The answer is the generalisation of the lower bounds, checked against every
upper bound; with no lower bounds it is the narrowest upper bound. Variants of
one enum generalise to the ROOT enum, classes to the interface they share —
deliberately unlike `t.join`, which is the honest set union a BRANCH result
needs. A programmer who wanted the narrower reading writes the type out.

Narrowing a call's overloads is ASSIGNABILITY, not arity: the shape is built
with a HOLE where the parameter sits (`(:Int, ?)`), and a candidate only falls
out when some other argument definitively rejects it. `3 * x` leaves exactly
one `*` standing, and x is read off its second parameter.

Everything else is an ambiguity, which is an error: no use that determines the
parameter, several readings that disagree, upper bounds that cannot all hold.
The author's answer to all of them is the same, so they share one diagnostic —
`uninferable_clue` supplies the part that tells them apart.

Evidence is recomputed from scratch on every compile pass. An early pass sees
names that have not resolved yet, says nothing about them, and leaves the
parameter untyped; the answer only ever fills IN, never changes.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field

import pyast.expression as e
import pyast.resolver as g
import pyast.rewrite as rw
import pyast.typespec as t


@dataclass
class _Evidence:
    """What one parameter's uses say about it."""
    # "x must FIT here": a call parameter it is passed to, a declared result it
    # is returned as.
    uppers: list[t.TypeSpec] = field(default_factory=list)
    # "x must ACCEPT these": the arm types of a `match` over it.
    lowers: list[t.TypeSpec] = field(default_factory=list)
    # A use whose reading is not settled YET — a callee that has not resolved,
    # an argument with no type. More evidence may arrive on a later pass, so the
    # parameter stays untyped rather than committing to a partial answer.
    deferred: list[str] = field(default_factory=list)
    # A use with several readings that disagree: settled, and an error.
    clashes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _Verdict:
    # Exactly one of these is set: the inferred type, or why there isn't one.
    type: t.TypeSpec | None = None
    clue: str | None = None


def infer_param_types(fn, body_resolver: g.Resolver) -> dict[str, t.TypeSpec]:
    """{target name: inferred type} for the parameters this body determines.
    Silent about the rest — a parameter with no answer stays untyped and is
    reported once the compile loop has converged (see `uninferable_clue`), by
    which time every name the evidence hangs on has had its chance to resolve."""
    verdicts = ((name, _verdict(ev, body_resolver))
                for name, ev in _collect(fn, body_resolver).items())
    return {name: v.type for name, v in verdicts if v.type is not None}


def uninferable_clue(fn, target, body_resolver: g.Resolver) -> str:
    """Why the body never determined `target`. Every outcome but a type is the
    same kind of failure, so this clue is the only thing that tells them apart."""
    ev = _collect(fn, body_resolver).get(target.name)
    if ev is None:
        return _NO_USE
    return _verdict(ev, body_resolver).clue or _NO_USE


_NO_USE = "no use in its body determines it"


# ── gathering the evidence ──────────────────────────────────────────────────

def _collect(fn, res0: g.Resolver) -> dict[str, _Evidence]:
    from pyast.match import MatchExpression

    params = [p for p in fn.parameters.targets if p.declared_type is None]
    if not params or fn.body is None:
        return {}
    ev = {p.name: _Evidence() for p in params}

    def named_param(res: g.Resolver, expr) -> str | None:
        """The parameter `expr` reads, or None. A name that COULD be one but has
        not resolved yet defers that parameter: a half-read body must not settle
        a type the rest of it would widen."""
        if not isinstance(expr, e.NamedExpression):
            return None
        hit = next((p for p in params if g.match_name(p.name, expr.name)), None)
        if hit is None:
            return None
        datas = res.find_data(expr.name)
        if not datas.complete:
            ev[hit.name].deferred.append("a name in its body has not resolved yet")
            return None
        if len(datas) != 1 or datas[0].statement is not hit:
            return None  # an inner binding of the same name, not the parameter
        return hit.name

    def visit(res: g.Resolver, thing):
        if isinstance(thing, e.CallExpression):
            _call_evidence(res, thing, ev, named_param)
        elif isinstance(thing, MatchExpression):
            _match_evidence(res, thing, ev, named_param)
        return rw.UNCHANGED

    fn.body.search_and_replace(res0, visit)
    _result_evidence(fn, res0, ev, named_param)
    return ev


def _call_evidence(res: g.Resolver, call, ev: dict, named_param) -> None:
    """`f(x)` — x flows into f's parameter, so it is bounded ABOVE by whatever
    f declares there, once f's overloads narrow to one reading."""
    args = call.parameter
    if not isinstance(args, e.TupleExpression):
        return
    for idx, entry in enumerate(args.expressions):
        name = named_param(res, entry.value)
        if name is not None:
            _argument_upper(res, call, args, idx, ev[name])


def _argument_upper(res: g.Resolver, call, args, idx: int, ev: _Evidence) -> None:
    from pyast.expression.access import NamedExpression, _resolve_overloads

    if not isinstance(call.function, NamedExpression):
        ev.deferred.append("it is passed to a computed callable")
        return
    if any(en.spread for en in args.expressions):
        ev.deferred.append("it is passed in a spread argument list")
        return
    called = g.bare_name(call.function.name)
    candidates = res.find_data(call.function.name)
    if not candidates.complete:
        ev.deferred.append(f"`{called}` has not resolved yet")
        return
    if not candidates:
        ev.deferred.append(f"no function named `{called}` is in scope")
        return
    # The call shape as far as it is known: every OTHER argument's type, and a
    # hole where this parameter sits. Assignability against that hole is
    # Unknown, never a rejection, so a candidate only falls out when one of the
    # known arguments definitively does not fit it.
    entries = tuple(t.TupleEntrySpec(en.name, None if i == idx else en.value.get_type(res))
                    for i, en in enumerate(args.expressions))
    shape = t.CallableSpec(call.line_ref, t.TupleSpec(call.line_ref, entries), None)
    supplied_names = [en.name for en in args.expressions]
    readings: list[t.TypeSpec] = []
    for cand in _resolve_overloads(res, shape, candidates):
        at = _parameter_at(res, cand, idx, supplied_names)
        # A candidate whose own type parameter sits there says nothing about the
        # argument — only an instantiation would, and this is not one.
        if at is not None and not any(at == seen for seen in readings):
            readings.append(at)
    if not readings:
        return  # this use tells us nothing; another may
    if len(readings) > 1:
        # Distinct readings can still SPELL alike; name each spelling once.
        ev.clashes.append(f"`{called}` could take " + " or ".join(sorted(set(map(_shown, readings)))))
        return
    ev.uppers.append(readings[0])


def _parameter_at(res: g.Resolver, cand, idx: int,
                  supplied_names: list[str | None]) -> t.TypeSpec | None:
    """The type this candidate declares for the argument at position `idx`, or
    None when that is no evidence: a generic candidate's own placeholder, an
    unresolved name, or an argument list this candidate cannot bind at all.

    WHICH parameter an argument fills is `bind_tuple_entries`' answer, not the
    argument's index — `f(second = x, first = y)` binds by NAME. Using the
    routine assignability itself binds with keeps the reading and the narrowing
    talking about the same slot, and the candidate is read through the same
    `candidate_signature` the narrowing used, so a trait method answers with
    its scope's arguments applied (`Times<Int>::*` takes an Int, not a TVal)."""
    from pyast.expression.access import candidate_signature
    ctype = candidate_signature(res, cand)
    if not isinstance(ctype, t.CallableSpec):
        return None
    binding = t.bind_tuple_entries(ctype.parameters.entries, supplied_names)
    if binding is None:
        return None
    slot = next((d for d, supplied in enumerate(binding) if supplied == idx), None)
    if slot is None:
        return None
    at = ctype.parameters.entries[slot].type
    if at is None or isinstance(at, t.NamedSpec) or t.placeholder_names_in(at):
        return None
    return at


def _match_evidence(res: g.Resolver, match, ev: dict, named_param) -> None:
    """`match(x)` arms are LOWER bounds — x must accept every one of them.

    An ELSE arm stops the match determining anything. It PROVES the subject has
    at least one member the named arms do not cover, and which members those
    are is written nowhere: `match(o) (s: Spec) => … ; () => "-"` says o is a
    Spec or something else, and that something is exactly what the author's
    `Spec|None` was carrying. Taking the named arms alone would infer `Spec`
    and then reject the author's own else arm as unreachable. So the match
    contributes NOTHING and other evidence — or the ambiguity error — decides."""
    name = named_param(res, match.subject)
    if name is None:
        return
    if any(arm.type_spec is None and not arm.literals for arm in match.arms):
        return
    # A GENERIC enum arm written WITHOUT its type arguments determines nothing
    # either (see _usable_lower). One such arm spoils the whole match: a
    # partial set of lower bounds would generalise to the wrong type. An arm
    # whose enum root is not settled yet DEFERS the parameter, as any unresolved
    # arm type does — a half-read body must not settle a type the rest of it
    # would change — and that takes precedence over a bare arm.
    usable = [_usable_lower(res, arm.type_spec)
              for arm in match.arms if arm.type_spec is not None]
    if any(u is None for u in usable):
        ev[name].deferred.append("a match arm's type has not resolved yet")
        return
    if not all(usable):
        return
    for arm in match.arms:
        if isinstance(arm.type_spec, t.NamedSpec):
            ev[name].deferred.append("a match arm's type has not resolved yet")
        elif arm.type_spec is not None:
            ev[name].lowers.append(arm.type_spec)
        else:
            for lit in arm.literals:
                lit_type = lit.get_type(res)
                if lit_type is None:
                    ev[name].deferred.append("a literal match arm has no type yet")
                else:
                    ev[name].lowers.append(lit_type)


def _usable_lower(res: g.Resolver, spec: t.TypeSpec) -> bool | None:
    """Is this arm type usable as a LOWER bound? None while its enum root has
    not resolved — not known yet, which the caller DEFERS on rather than
    deciding.

    A generic enum written without its type arguments is not. `match(ps)` with
    arms `(nil: ChainEnd)` / `(l: ChainLink)` over a `Chain<Spec>` subject has
    BARE arms — arms receive the subject's type arguments only once the
    subject's type is known, and here the subject IS the parameter being
    inferred. Generalising bare arms yields a bare `Chain`, which
    monomorphisation cannot specialise; codegen then looks up a root that no
    longer exists and dies with no source location (union_repr.read_field).
    Keep the author's annotation instead — it is carrying the type argument."""
    if not isinstance(spec, t.EnumSpec) or spec.type_params:
        return True
    found = res.find_type(spec.root_name)
    if not found.complete or len(found) != 1:
        return None
    return not (getattr(found[0].statement, "type_params", ()) or ())


def _result_evidence(fn, res0: g.Resolver, ev: dict, named_param) -> None:
    """A declared result is an UPPER bound on whatever the body returns: `ret x`
    says x fits it, and `ret c(3)` says c is a callable WITH that result — the
    only thing that can complete a callable parameter, which is why a function
    taking one must declare either the parameter or its own result."""
    if fn.return_type is None or fn.return_inferred:
        return
    for expr, res in _result_positions(fn.body, res0):
        name = named_param(res, expr)
        if name is not None:
            ev[name].uppers.append(fn.return_type)
        elif isinstance(expr, e.CallExpression):
            name = named_param(res, expr.function)
            if name is not None:
                _callable_upper(res, expr, fn.return_type, ev[name])


def _callable_upper(res: g.Resolver, call, result: t.TypeSpec, ev: _Evidence) -> None:
    args = call.parameter
    if not isinstance(args, e.TupleExpression) or any(en.spread for en in args.expressions):
        ev.deferred.append("its argument list is not a plain positional tuple")
        return
    entries = []
    for en in args.expressions:
        at = en.value.get_type(res)
        if at is None:
            ev.deferred.append("an argument it is called with has no type yet")
            return
        entries.append(t.TupleEntrySpec(en.name, at))
    ev.uppers.append(t.CallableSpec(call.line_ref,
                                    t.TupleSpec(call.line_ref, tuple(entries)), result))


def _result_positions(expr, res: g.Resolver) -> list[tuple]:
    """Every expression whose value IS the function's result, each with the
    resolver its own scope provides: a block's trailing value (the parser folds
    a final `ret` into it), and through a match or a ternary, each branch's."""
    from pyast.expression.block import BlockExpression
    from pyast.expression.ternary import TernaryExpression
    from pyast.match import MatchExpression

    if isinstance(expr, BlockExpression):
        return _result_positions(expr.value, g.ResolverData(res, expr._find_locals()))
    if isinstance(expr, MatchExpression):
        return [pos for arm in expr.arms
                for pos in _result_positions(arm.body, arm.body_resolver(res))]
    if isinstance(expr, TernaryExpression):
        return (_result_positions(expr.trueResult, res)
                + _result_positions(expr.falseResult, res))
    return [(expr, res)]


# ── reading the verdict off the evidence ────────────────────────────────────

def _verdict(ev: _Evidence, resolver: g.Resolver) -> _Verdict:
    if ev.clashes:
        return _Verdict(clue="; ".join(dict.fromkeys(ev.clashes)))
    answer = None
    if ev.lowers:
        answer = _generalise(ev.lowers, resolver, ev)
        # "Not known yet" is not "share nothing": only a SETTLED absence is an
        # error, so a deferral falls through to be reported as one below.
        if answer is None and not ev.deferred:
            # Two matches over one parameter often repeat an arm type; name
            # each type once.
            return _Verdict(clue="its match arms share no type — "
                                 + ", ".join(sorted(set(map(_shown, ev.lowers)))))
    elif ev.uppers:
        answer = _narrowest(ev.uppers, resolver)
    if answer is not None and any(t.trivially_assignable_equals(resolver, up, answer) is False
                                  for up in ev.uppers):
        answer = None
    if answer is not None and not ev.deferred:
        return _Verdict(type=answer)
    if ev.deferred:
        return _Verdict(clue="; ".join(dict.fromkeys(ev.deferred)))
    if ev.uppers:
        return _Verdict(clue="its uses require "
                             + " and ".join(sorted(set(map(_shown, ev.uppers)))))
    return _Verdict(clue=_NO_USE)


def _generalise(lowers: list[t.TypeSpec], resolver: g.Resolver,
                ev: _Evidence) -> t.TypeSpec | None:
    """The one type that accepts every lower bound. Variants of an enum
    generalise to the ROOT — a parameter matched as Circle and as Square takes
    any Shape — and classes to the interface they share, a class being allowed
    to inherit only from pure interfaces. None when they share nothing, which
    is an ambiguity like any other."""
    first = lowers[0]
    if all(x == first for x in lowers[1:]):
        return first
    if all(isinstance(x, t.EnumSpec) for x in lowers):
        if len({x.root_name for x in lowers}) != 1:
            return None
        return dataclasses.replace(first, valid_leaf_names=frozenset(first.all_leaf_names))
    if all(isinstance(x, t.ClassSpec) for x in lowers):
        shared = _shared_interfaces(lowers, resolver)
        if shared is None:
            ev.deferred.append("an inheritance graph it reads is not built yet")
            return None
        return shared[0] if len(shared) == 1 else None
    return None


def _shared_interfaces(specs: list[t.ClassSpec],
                       resolver: g.Resolver) -> "list[t.ClassSpec] | None":
    """The interfaces every one of these classes implements, in name order, or
    None while the inheritance graph is still being built — "not known yet" is
    a different answer from "none shared", and only the latter is an error.
    Zero or several shared is an ambiguity: picking one would be choosing for
    the author, and they can say which by writing the type out."""
    import pyast.statement as s
    common: set[str] | None = None
    by_name: dict[str, t.ClassSpec] = {}
    for spec in specs:
        found = resolver.find_type(spec.name)
        if (not found.complete or len(found) != 1
                or not isinstance(found[0].statement, s.ClassStatement)):
            return None  # the class has not resolved yet
        parents = found[0].statement._all_parents
        if parents is None:
            return None  # the inheritance graph is not built yet
        names = set()
        for parent in parents:
            name = getattr(parent, "name", None)
            if name is not None and name != spec.name:
                names.add(name)
                by_name[name] = parent
        common = names if common is None else common & names
    return [by_name[name] for name in sorted(common or ())]


def _narrowest(uppers: list[t.TypeSpec], resolver: g.Resolver) -> t.TypeSpec | None:
    """The one upper bound that satisfies all the others — a parameter used as a
    Circle and as a Shape is a Circle. None when no single bound fits inside the
    rest: they contradict, and the parameter has no type."""
    for cand in uppers:
        if all(other == cand or t.trivially_assignable_equals(resolver, other, cand) is True
               for other in uppers):
            return cand
    return None


def _shown(spec: t.TypeSpec) -> str:
    """A type as the author would write it (the call node's own renderer, so
    diagnostics from both places read alike)."""
    from pyast.expression.call import _type_str
    return _type_str(spec)
