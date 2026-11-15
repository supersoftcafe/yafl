"""`$"text {expr} text {expr:spec}"` — an interpolated string, as the parser
read it.

Like PipeExpression, the node exists only between the parser and the end of
`parse()`, which lowers every one (parsing.parser.lower_interpolation) to
ONE `str_concat_n` over the text pieces and a `show(expr)` / `show(expr,
"spec")` call per slot — a single exact-size join, never a chain of `+` that
would copy the growing prefix again at every step. Nothing after `parse()`
sees it.

`show` is looked up where the string is written, exactly as a hand-written
`"a" + show(x)` would be, so a local overload of `show` takes over.

Each lowered `show` call carries an InterpolationOrigin: the slot's source
text. Type checking runs after lowering and sees only the call (and the join,
which checks its operands are Strings); the origin lets their errors say what
the user wrote (`cannot interpolate `x`: …`) at the slot, rather than
describe a call nobody wrote.
"""
from __future__ import annotations

from typing import Callable, Any
from dataclasses import dataclass

import pyast.rewrite as rw
import pyast.resolver as g
from parsing.tokenizer import LineRef
from pyast.expression.base import Expression


@dataclass(frozen=True)
class InterpolationOrigin:
    """What a lowered call was lowered FROM: an interpolation slot, by its
    source text. Error reporting reads it to phrase the message."""
    text: str

    def reword(self, message: str) -> str:
        return f"cannot interpolate `{self.text}`: {message}"


@dataclass
class InterpolationSlot:
    """One `{expression}` or `{expression:spec}`. `text` is the expression as
    written; `spec` the decoded text after the separating colon, or None."""
    line_ref: LineRef
    expression: Expression
    spec: str | None
    text: str

    def search_and_replace(self, resolver: g.Resolver,
                           replace: Callable[[g.Resolver, Any], Any]) -> "InterpolationSlot | Any":
        # Structural, like a tuple entry: the callback never visits a slot.
        return rw.rebuild(self,
            expression=self.expression.search_and_replace(resolver, replace))


@dataclass
class InterpolatedStringExpression(Expression):
    """`parts` alternate as written: decoded text (str) and slots. Adjacent
    text is one piece; an empty piece is never stored. `spelling` is the
    literal as written, for the formatter."""
    parts: list[str | InterpolationSlot]
    spelling: str = ""

    def search_and_replace(self, resolver: g.Resolver,
                           replace: Callable[[g.Resolver, Any], Any]) -> Expression:
        rewritten = [rw.UNCHANGED if isinstance(part, str) else part.search_and_replace(resolver, replace)
                     for part in self.parts]
        parts = rw.UNCHANGED if all(r is rw.UNCHANGED for r in rewritten) else \
            [part if r is rw.UNCHANGED else r for part, r in zip(self.parts, rewritten)]
        return rw.rewrite(self, replace, resolver, parts=parts)
