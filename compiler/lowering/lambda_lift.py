"""Lambda lifting: nested functions that capture only to be CALLED lose the
closure — the captures become parameters, threaded at every call site.

A nested function that references its enclosing function's variables is a
capture, and closure conversion (lowering/lambdas.py) turns a capture into a
heap object built wherever the captured values are known — for a helper
inside a hot loop, that is an allocation per call. But when the nested
function is only ever *called* (its name never travels as a value), the
closure is pure overhead: passing the captured values as arguments is
observationally identical and allocation-free. Simple unoptimised code —
the idiomatic nested helper reading its parent's parameters — then costs
exactly what the hand-threaded version would. (Found the hard way: one
captured `data` in writeAll's loop was 93% of json_pretty's allocations.)

An SCC of sibling functions lifts as a unit (mutual recursion threads the
union of the members' captures through every member and call site — the
same argument works at each hop). Conditions, all conservative:

  - every capture is a PARAMETER of the enclosing function (always in
    scope at every possible call site; captured block-lets would need
    dominance reasoning under whole-block scoping);
  - no captured parameter is `[linear]` (threading one per call changes
    how many times it is consumed — the linearity story for closures and
    for threading differ, so leave those to closure conversion);
  - every reference to every member, anywhere in the enclosing body, is
    the callee of a call — counted, not assumed: total name references
    must equal call-position references.

Runs BEFORE tail_loop: self-calls must still be calls (afterwards they are
`recur`, whose bindings don't include the new parameters). After the lift
the functions are capture-free, so ast_inline's hoist takes its existing
global path and no closure class is ever built.
"""
from __future__ import annotations

import dataclasses

import pyast.statement as s
import pyast.expression as e
import pyast.resolver as g
from langtools import checked_cast
from lowering.ast_inline import _free_refs, _tarjan_sccs


def __call_args(call: e.CallExpression) -> list[e.TupleEntryExpression]:
    p = call.parameter
    if isinstance(p, e.TupleExpression):
        return list(p.expressions)
    if isinstance(p, e.NothingExpression):
        return []
    return [e.TupleEntryExpression(None, p)]


def __reference_counts(body: e.Expression, names: set[str]) -> tuple[dict[str, int], dict[str, int]]:
    """(total NamedExpression references, references in call position)."""
    total: dict[str, int] = {n: 0 for n in names}
    called: dict[str, int] = {n: 0 for n in names}

    def visit(_r, thing):
        if isinstance(thing, e.NamedExpression) and thing.name in names:
            total[thing.name] += 1
        if (isinstance(thing, e.CallExpression)
                and isinstance(thing.function, e.NamedExpression)
                and thing.function.name in names):
            called[thing.function.name] += 1
        return thing

    body.search_and_replace(g.ResolverRoot([]), visit)
    return total, called


def __lift_in_function(fn: s.FunctionStatement) -> s.FunctionStatement:
    """Lift what qualifies inside fn's own body (deepest nesting first)."""
    if not isinstance(fn.body, e.BlockExpression):
        return fn

    # Depth-first: a nested function's own nested helpers lift before it is
    # itself considered (its capture set is then already final).
    body_stmts = [
        __lift_in_function(stmt) if isinstance(stmt, s.FunctionStatement) else stmt
        for stmt in fn.body.statements]
    fn = dataclasses.replace(fn, body=dataclasses.replace(fn.body, statements=body_stmts))

    nested = {stmt.name: stmt for stmt in body_stmts
              if isinstance(stmt, s.FunctionStatement)}
    if not nested:
        return fn

    params_by_name = {p.name: p for p in fn.parameters.flatten()}
    sibling_names = set(nested)
    captures = {name: _free_refs(nf, sibling_names) & set(params_by_name)
                for name, nf in nested.items()}
    calls = {name: _free_refs(nf, set()) & sibling_names
             for name, nf in nested.items()}
    total_refs, call_refs = __reference_counts(fn.body, sibling_names)

    sccs = _tarjan_sccs(list(nested), calls)
    scc_of = {n: i for i, scc in enumerate(sccs) for n in scc}

    # An SCC's threaded set is its members' captures plus whatever its
    # callees (other SCCs, already lifted or about to be) thread — Tarjan
    # yields callees first, so one forward pass settles it.
    threaded: list[set[str]] = [set() for _ in sccs]
    liftable: list[bool] = [True] * len(sccs)
    for i, scc in enumerate(sccs):
        want: set[str] = set()
        for n in scc:
            want |= captures[n]
            for callee in calls[n]:
                j = scc_of[callee]
                if j != i:
                    if not liftable[j]:
                        liftable[i] = False
                    want |= threaded[j]
            if total_refs[n] != call_refs[n]:
                liftable[i] = False       # the name travels as a value
        if any("linear" in params_by_name[c].attributes for c in want):
            liftable[i] = False
        threaded[i] = want

    lift_sets = {n: sorted(threaded[scc_of[n]])
                 for n in nested if liftable[scc_of[n]] and threaded[scc_of[n]]}
    if not lift_sets:
        return fn

    def rewrite(_r, thing):
        if (isinstance(thing, e.CallExpression)
                and isinstance(thing.function, e.NamedExpression)
                and thing.function.name in lift_sets):
            extra = [e.TupleEntryExpression(None, e.NamedExpression(thing.line_ref, name))
                     for name in lift_sets[thing.function.name]]
            args = __call_args(thing) + extra
            return dataclasses.replace(thing, parameter=e.TupleExpression(thing.line_ref, args))
        if isinstance(thing, s.FunctionStatement) and thing.name in lift_sets:
            new_params = [dataclasses.replace(params_by_name[name])
                          for name in lift_sets[thing.name]]
            return dataclasses.replace(thing, parameters=dataclasses.replace(
                thing.parameters, targets=list(thing.parameters.targets) + new_params))
        return thing

    return checked_cast(s.FunctionStatement,
                        fn.search_and_replace(g.ResolverRoot([]), rewrite))


def lift_captured_calls(statements: list[s.Statement]) -> list[s.Statement]:
    return [__lift_in_function(stmt) if isinstance(stmt, s.FunctionStatement) else stmt
            for stmt in statements]
