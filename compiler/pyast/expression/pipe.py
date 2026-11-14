"""`subject |> stage` — a pipeline stage, as the parser read it.

The node exists only between the parser and the end of `parse()`, which lowers
every one of them (parsing.parser.lower_pipe): a lambda stage beta-reduces to
blocks, a `_` placeholder stage binds the subject and substitutes it, and any
other stage becomes an ordinary call. Nothing after `parse()` ever sees a
PipeExpression, so it has no type, check or code of its own.

It is a node rather than parse-time sugar so the parse itself still says that
a pipeline was written: the formatter prints what the parser read, and a plain
`x |> f` lowers to `f(x)`, which no longer says so.

`line_ref` is the stage's, the position every lowering of it carries.
"""
from __future__ import annotations

from typing import Callable, Any
from dataclasses import dataclass

import pyast.rewrite as rw
import pyast.resolver as g
from pyast.expression.base import Expression


@dataclass
class PipeExpression(Expression):
    subject: Expression
    stage: Expression

    def search_and_replace(self, resolver: g.Resolver,
                           replace: Callable[[g.Resolver, Any], Any]) -> Expression:
        return rw.rewrite(self, replace, resolver,
            subject=self.subject.search_and_replace(resolver, replace),
            stage=self.stage.search_and_replace(resolver, replace))
