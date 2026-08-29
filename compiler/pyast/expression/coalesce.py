"""`a ?? b` — a's value when it is not None, otherwise b.

The elimination half of the option idiom. `?>` (stdlib/result.yafl) PROPAGATES
the absent case; almost every site in the compiler wants to END it with a
default instead, and wrote the match out by hand:

    match(x)              ->      x ?? false
      (b: Bool) => b
      ()        => false

WHY THIS IS A NODE AND NOT PARSE-TIME SUGAR, as `&&`/`||` are. The desugar
wants a match whose first arm binds the subject's non-None part:

    match(a)
      (v: T) => v
      ()     => b

and `T` — the subject's type minus None — is not spellable at parse time. The
tempting sugar that needs no type,

    match(a)
      (_: None) => b
      (v)       => v

does not work: `()`/`(v)` is the ELSE arm and binds at the SUBJECT's type, so
the result comes out `T|None` rather than `T`, which defeats the point.

So the node exists only until the fixpoint knows the subject's type, then
rewrites itself into exactly that match — the ConvertExpression pattern
(compile is identity while the types are not ground, and the rewrite is what
dissolves the node). Nothing downstream of the fixpoint ever sees a
CoalesceExpression, so codegen needs no case for it.

Short-circuit is therefore structural, not an optimiser artefact: `b` lands in
a match arm, and an arm is only evaluated when it is taken.
"""
from __future__ import annotations

from typing import Callable, Any
import dataclasses
from dataclasses import dataclass

import pyast.rewrite as rw
from parsing.parselib import Error

import pyast.resolver as g
import pyast.statement as s
import pyast.typespec as t
from pyast.expression.base import Expression


def _is_none_member(member: t.TypeSpec) -> bool:
    """True for the unit type — `typealias None : ()`, the empty tuple.

    Spelling-level, deliberately: an unresolved `NamedSpec("None")` is NOT
    treated as the none member, because the subject may not be ground yet and
    guessing would desugar against a type that is still moving. Such a subject
    simply fails `without_none` below and the node waits another pass.
    """
    return isinstance(member, t.TupleSpec) and not member.entries


def without_none(spec: t.TypeSpec) -> t.TypeSpec | None:
    """`spec` minus its None member, or None when that is not yet answerable.

    Answers None (meaning "not yet") when the subject is not a union at all,
    when it carries no None member, or when removing None leaves nothing —
    each of which is either a type error for `check` to report or a type that
    has not settled.
    """
    if not isinstance(spec, t.CombinationSpec):
        return None
    members = list(spec.repr_members())
    kept = [m for m in members if not _is_none_member(m)]
    if len(kept) == len(members) or not kept:
        return None
    if len(kept) == 1:
        return kept[0]
    return t.CombinationSpec(spec.line_ref, tuple(kept))


@dataclass
class CoalesceExpression(Expression):
    """`subject ?? fallback`, until the subject's type is ground."""
    subject: Expression
    fallback: Expression

    def search_and_replace(self, resolver: g.Resolver,
                           replace: Callable[[g.Resolver, Any], Any]) -> Expression:
        return rw.rewrite(self, replace, resolver,
            subject=self.subject.search_and_replace(resolver, replace),
            fallback=self.fallback.search_and_replace(resolver, replace))

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        """The narrowed subject joined with the fallback — the same rule the
        match it becomes would give, so the type does not shift when the node
        dissolves."""
        st = self.subject.get_type(resolver)
        ft = self.fallback.get_type(resolver)
        narrowed = without_none(st) if st is not None else None
        if narrowed is None:
            return ft if st is None else None
        return narrowed if ft is None else t.join(narrowed, ft)

    def compile(self, resolver: g.Resolver,
                expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement]]:
        # The subject compiles with NO expected type: feeding the receiver's
        # type down would push the fallback's type onto the option and defeat
        # the narrowing. This compile is also how the subject's type becomes
        # known, which is what decides whether the node can dissolve yet.
        subject, s1 = self.subject.compile(resolver, None)
        st = subject.get_type(resolver)
        narrowed = without_none(st) if st is not None else None
        if narrowed is not None and st.is_concrete():
            # Desugar from the ORIGINAL children, and drop `s1`. The match
            # compiles its own subject and arms, so passing the already-compiled
            # ones would compile each twice — and a compile is not idempotent
            # for anything that LIFTS: a lambda in the subject became two
            # `$lambdas::lambda@…` globals, and the two compilers disagreed
            # about which survived. Recompiling from the original is
            # deterministic and yields exactly one of each.
            return self.__desugar(narrowed, resolver, expected_type)
        # Not ground yet: keep the node, with both children advanced one pass.
        fallback, s2 = self.fallback.compile(resolver, expected_type)
        return dataclasses.replace(self, subject=subject, fallback=fallback), s1 + s2

    def __desugar(self, narrowed, resolver, expected_type):
        """Become `match(subject) (v: narrowed) => v; () => fallback`.

        The binder carries the site hash exactly as the with-expression's arms
        do, so two coalesces in one scope cannot collide; the body references
        it bare, which is what MatchArm's binding finder matches on.

        The arms MUST be given a target type. A match's arms converge on the
        receiver's type — that is what makes each arm wrap itself when the arms
        differ (here they do whenever the fallback is itself an option, as in
        `a ?? b ?? c`: the hit arm is `T`, the fallback `T|None`). With no
        receiver the arms stay unconverted while the match's own type is their
        join, and the mismatch surfaces as a generate-time "conversion required"
        abort. So when the receiver supplies nothing, the node supplies its own
        type, which is that join by construction.
        """
        from pyast.match import MatchArm, MatchExpression
        from pyast.expression.access import NamedExpression
        lr = self.line_ref
        # The binder is keyed on the FALLBACK's position, not this node's.
        # `a ?? b ?? c` folds left-associatively and every node in that fold
        # inherits the LEFT operand's line_ref — so all of them hash the same,
        # and a shared binder name means two arms defining one SSA value
        # ($qq defined 2 times). The fallbacks are what actually differ. The
        # base name carries the hash too, not just the `@` suffix, because
        # MatchArm's binding finder matches on the bare name with the suffix
        # stripped — two arms named `$qq@a` and `$qq@b` would both answer to a
        # bare `$qq`.
        # No `@`-suffix here: MatchArm's own _arm_unique_name appends
        # `@arm<line hash>` to whatever it is given, so adding one produces a
        # doubly-suffixed name and the port (which relies on that same
        # machinery) emits a different C identifier. Uniqueness comes from the
        # BASE being keyed on the fallback's position.
        uniq = self.fallback.line_ref.hash6()
        binder = f"$qq{uniq}"
        hit = MatchArm(lr, binder, narrowed, NamedExpression(lr, binder))
        els = MatchArm(lr, None, None, self.fallback)
        target = expected_type if expected_type is not None else self.get_type(resolver)
        return MatchExpression(lr, self.subject, [hit, els]).compile(resolver, target)

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        errors = (self.subject.check(resolver, None)
                  + self.fallback.check(resolver, expected_type))
        st = self.subject.get_type(resolver)
        # A surviving node at check time means the subject never became an
        # option: `??` on a type with nothing to eliminate is a mistake worth
        # naming, not a silent identity.
        if st is not None and st.is_concrete() and without_none(st) is None:
            errors = errors + [Error(self.line_ref,
                "`??` needs a `T|None` left operand; this one cannot be None")]
        return errors

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        raise AssertionError(
            "CoalesceExpression reached codegen — it must dissolve into a match "
            "during compile once the subject's type is ground")
