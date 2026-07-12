from __future__ import annotations

from typing import Callable, Any
import dataclasses
import pyast.rewrite as rw
import random
from dataclasses import dataclass, field
from functools import reduce

from langtools import checked_cast
from parsing.tokenizer import LineRef
from parsing.parselib import Error

import codegen.ops as cg_o
import codegen.param as cg_p
import codegen.typedecl as cg_t

import pyast.resolver as g
import pyast.statement as s
import pyast.typespec as t
import pyast.utils as u
from pyast.expression.base import Expression


def _unwrap_one_tuple(expr: "Expression") -> "Expression":
    """A bracketed expression `(x)` parses to a 1-element TupleExpression.
    YAFL treats a 1-tuple as equivalent to its sole value, so in value
    positions we collapse the wrap. Only unnamed entries are unwrapped —
    `(name = value)` is a named 1-tuple and may be load-bearing for
    destructuring/type checks elsewhere.
    """
    while (isinstance(expr, TupleExpression)
            and len(expr.expressions) == 1
            and expr.expressions[0].name is None):
        expr = expr.expressions[0].value
    return expr



@dataclass
class TupleEntryExpression:
    name: str|None
    value: Expression
    # `*value` — splice the tuple value's fields into the enclosing tuple,
    # positionally (names never travel through a spread). Expanded away by
    # TupleExpression.compile once the value's tuple arity is known.
    spread: bool = False

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,Any],Any]) -> TupleEntryExpression:
        v = self.value.search_and_replace(resolver, replace)
        return rw.UNCHANGED if v is rw.UNCHANGED else dataclasses.replace(self, value=v)

    def get_type(self, resolver: g.Resolver) -> t.TupleSpec | None:
        return self.value.get_type(resolver)

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[TupleEntryExpression, list[s.Statement]]:
        new_value, new_statements = self.value.compile(resolver, expected_type)
        new_value = _unwrap_one_tuple(new_value)
        return dataclasses.replace(self, value=new_value), new_statements

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        return self.value.check(resolver, expected_type)

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        return self.value.generate(resolver)



@dataclass
class TupleExpression(Expression):
    expressions: list[TupleEntryExpression]

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,Any],Any]) -> Expression:
        return rw.rewrite(self, replace, resolver,
            expressions=rw.seq(self.expressions, resolver, replace))

    def get_type(self, resolver: g.Resolver) -> t.TupleSpec | None:
        entries: list[t.TupleEntrySpec] = []
        for x in self.expressions:
            if x.spread:
                stype = x.value.get_type(resolver)
                if not isinstance(stype, t.TupleSpec):
                    return None  # unresolved yet (or not a tuple — check reports it)
                entries.extend(t.TupleEntrySpec(None, en.type) for en in stype.entries)
            else:
                entries.append(t.TupleEntrySpec(x.name, x.get_type(resolver)))
        return t.TupleSpec(self.line_ref, entries = entries)

    def __expand_spreads(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement]]:
        """Rewrite a tuple literal containing `*spread` entries into a block:
        each spread's value binds once via a destructure, and the rebuilt
        literal splices the bound fields in place (positionally — names never
        travel through a spread). Deferred (returned as-is) until every
        spread's tuple arity is known; the fixpoint loop retries."""
        from pyast.expression.access import NamedExpression
        from pyast.expression.block import BlockExpression
        compiled = [x.compile(resolver, None) for x in self.expressions]
        new_exprs = [ce for ce, _ in compiled]
        globals = [st for _, sts in compiled for st in sts]
        if any(x.spread and not isinstance(x.value.get_type(resolver), t.TupleSpec)
               for x in new_exprs):
            return dataclasses.replace(self, expressions=new_exprs), globals
        binders: list[s.Statement] = []
        entries: list[TupleEntryExpression] = []
        for idx, x in enumerate(new_exprs):
            if not x.spread:
                entries.append(x)
                continue
            stype = x.value.get_type(resolver)
            lr = x.value.line_ref
            fresh = [f"$spread{idx}$f{i}@{lr.hash6()}" for i in range(len(stype.entries))]
            targets = [s.LetStatement(lr, nm, None, {}, (), None, None) for nm in fresh]
            binders.append(s.DestructureStatement(lr, '_', None, {}, (), x.value, None, targets))
            entries.extend(TupleEntryExpression(None, NamedExpression(lr, nm)) for nm in fresh)
        block = BlockExpression(self.line_ref, binders,
                                TupleExpression(self.line_ref, entries))
        expr, block_globals = block.compile(resolver, expected_type)
        return expr, globals + block_globals

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement]]:
        if any(x.spread for x in self.expressions):
            return self.__expand_spreads(resolver, expected_type)
        # A tuple literal converges FIELD-WISE against a tuple receiver: each
        # entry compiles toward its slot and owns any boxing itself. Against a
        # UNION receiver holding a matching tuple variant, the fields converge
        # toward that variant, then the whole tuple owns the box into the union.
        from pyast.expression.conversion import converted, matching_tuple_variant
        effective = expected_type
        if isinstance(expected_type, t.CombinationSpec):
            actual = self.get_type(resolver)
            if actual is not None and actual.is_concrete():
                effective = matching_tuple_variant(actual, expected_type, resolver)
        expected_entries = effective.entries if isinstance(effective, t.TupleSpec) else []
        # Each entry converges toward the field it BINDS — positionally, or by
        # name (`f(5, bias = 7)` converges its second entry toward `bias`, not
        # toward whatever sits at index 1). The reorder/default-fill itself is
        # a conversion, owned by this node's `converted` wrap below.
        slot_of: dict[int, int] = {}
        if expected_entries:
            binding = t.bind_tuple_entries(expected_entries, [x.name for x in self.expressions])
            if binding is not None:
                slot_of = {b: i for i, b in enumerate(binding) if b is not None}
        def entry_expected(i: int) -> t.TypeSpec | None:
            if slot_of:
                j = slot_of.get(i)
                return expected_entries[j].type if j is not None else None
            return expected_entries[i].type if i < len(expected_entries) else None
        p = [x.compile(resolver, entry_expected(i)) for i, x in enumerate(self.expressions)]
        new_expressions, new_statements_lists = zip(*p) if p else ([], [])
        expr = dataclasses.replace(self, expressions=list(new_expressions))
        return converted(expr, expected_type, resolver), list(x for l in new_statements_lists for x in l)

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        # TODO: Breakdown expected_type and pass it into the check function
        errors = [e for x in self.expressions for e in x.check(resolver, None)]
        # A spread surviving to check never resolved to a tuple: compile only
        # expands `*x` once x's tuple arity is known.
        errors += [Error(self.line_ref, "can only spread a tuple value: `*x` needs x to be a tuple")
                   for x in self.expressions
                   if x.spread and not isinstance(x.value.get_type(resolver), t.TupleSpec)]
        # A WRITTEN entry name is a binding request: it must name a field of
        # the receiver. (The binding itself is lenient about non-overlapping
        # names — a piped value's incidental field names bind positionally —
        # but an explicit `name = value` here was typed by the author against
        # THIS receiver, so a name that matches nothing is a mistake, not a
        # coincidence.)
        if isinstance(expected_type, t.TupleSpec):
            bare = {g.bare_name(en.name) for en in expected_type.entries if en.name is not None}
            errors += [Error(self.line_ref, f"the target tuple has no field named '{x.name}'")
                       for x in self.expressions
                       if x.name is not None and x.name not in bare]
        return errors or []

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        param_bundles = [expr.generate(resolver).with_prefix(f"e{index}") for index, expr in enumerate(self.expressions)]
        # NewStruct field-name → result_var mapping is pinned to declared positions,
        # so the resulting tuple value is unaffected by any reordering of evaluation below.
        value = cg_p.NewStruct(tuple(((f"_{idx}", x.result_var) for idx, x in enumerate(param_bundles))))
        final_bundle = g.OperationBundle((), (), value)
        # At -O0, randomise the order in which children's side-effects fire so that
        # any code accidentally relying on left-to-right tuple evaluation surfaces.
        # Seed deterministically from the source location: same .yafl in → same .c out,
        # but order varies across tuple sites within a program.
        eval_bundles = param_bundles
        if resolver.get_optimization_level() == 0 and len(eval_bundles) > 1:
            rng = random.Random(f"{self.line_ref.filename}:{self.line_ref.line}:{self.line_ref.offset}")
            eval_bundles = list(param_bundles)
            rng.shuffle(eval_bundles)
        total_bundle = reduce(lambda x, y: y + x, reversed(eval_bundles), final_bundle)
        return total_bundle

    def trim_left(self, amount: int) -> TupleExpression:
        return dataclasses.replace(self, expressions=self.expressions[amount:])



