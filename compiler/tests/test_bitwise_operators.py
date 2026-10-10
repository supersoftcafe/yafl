"""Bitwise operators `~`, `&`, `|`, `^` and the `andNot` method.

Provided by the `Bitwise<T>` interface (stdlib/traits.yafl) with an instance
per integer type (stdlib/integer.yafl); `&`/`^`/`|` parse at a precedence
between arithmetic and comparison (so `a & b == c` is `(a & b) == c`), and `~`
is unary complement. `andNot(a, b)` is `a & ~b` — the parser folds that
spelling onto the single-pass method. Float and String have no Bitwise instance.

The runtime checks are [test]s in compiler/yafl_tests/bitwise_operators.yafl;
the parse-time fold is checked here.
"""
from __future__ import annotations

import pyast.expression as e
from tests.testutil import TimedTestCase as TestCase


class TestBitwiseOperators(TestCase):
    def test_andnot_fold_at_parse_time(self):
        # `a & ~b` and (by commutativity) `~a & b` fold to a single andNot call,
        # not a complement-then-and; both-inverted and plain stay as-is.
        import parsing.parser as pp
        from parsing.tokenizer import tokenize

        def head(src: str) -> str:
            expr = pp.parse_expression(tokenize(src, "file")).value
            self.assertIsInstance(expr, e.CallExpression)
            return expr.function.name

        self.assertEqual("andNot", head("a & ~b"))   # andNot(a, b)
        self.assertEqual("andNot", head("~a & b"))    # andNot(b, a)
        self.assertEqual("andNot", head("~a & ~b"))   # andNot(~a, b) == ~a & ~b
        self.assertEqual("`&`", head("a & b"))        # no fold
        self.assertEqual("`~`", head("~a"))           # plain complement
