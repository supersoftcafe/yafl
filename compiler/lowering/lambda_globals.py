"""A global `let` whose value is a lambda IS a function — lower it to one.

`let h = (s: String) => length(s)` at file scope is a function by another
name: captureless (globals can't see locals), so it needs none of the closure
or lazy-init machinery a lambda-value otherwise carries. Rewriting it to a
plain `fun h(s: String): Int` means it compiles as an ordinary function — no
lazy stub, no fun_t threaded through the async force path (which the lazy
machinery does not handle for callable values). A `fun` and a `let` holding a
callable are indistinguishable at every use site, so the rewrite is
transparent to callers and to code that passes `h` as a value.

Runs after convergence, so every lambda is already fully typed: the
parameters carry their types and the return type is known — no inference to
do here, just a repackaging.
"""
from __future__ import annotations

import pyast.statement as s
import pyast.expression as e


def lower_lambda_globals(statements: list[s.Statement]) -> list[s.Statement]:
    def convert(st: s.Statement) -> s.Statement:
        if (isinstance(st, s.LetStatement)
                and not isinstance(st, s.DestructureStatement)
                and isinstance(st.default_value, e.LambdaExpression)):
            lam = st.default_value
            # A lambda is fully typed by the time any lowering runs, so its
            # `return_type` is the whole `(params): result` CallableSpec; the
            # function wants just the result type.
            return s.FunctionStatement(
                line_ref=st.line_ref,
                name=st.name,
                imports=st.imports,
                attributes=st.attributes,
                type_params=st.type_params,
                parameters=lam.parameters,
                body=lam.expression,
                return_type=lam.return_type.result,
                trait_params=st.trait_params)
        return st

    return [convert(st) for st in statements]
