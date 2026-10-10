"""Postfix chaining: `.field` / `(...)` / `[...]` interleave freely.

Previously the parser split dotting and calling into two non-interleaved layers,
so a postfix applied to the *result of a call or index* (`f().g()`, `a().b`,
`m()[0].x`) was rejected. They now form one left-associative chain
(`parsing/parser.py`, `__parse_invoke` / `__to_invokes`). Existing forms
(`a.b.c`, `io.read(5)`, `arr[0]`) are unchanged, and a non-identifier dot target
is still an error. The chains' runtime behaviour is checked by
compiler/yafl_tests/postfix_chaining.yafl.
"""
from __future__ import annotations

from parsing.tokenizer import tokenize
from parsing.parser import parse_expression
from tests.testutil import TimedTestCase as TestCase


class TestPostfixChainingParse(TestCase):
    def _parse(self, src: str):
        return parse_expression(tokenize(src, "t.yafl"))

    def test_newly_enabled_chains_parse(self):
        # Each of these used to fail with "extra unexpected characters".
        for src in ("f().g()", "a().b", "m()[0]", "arr[0].field",
                    "f(x).y().z()", "a.b(x).c"):
            r = self._parse(src)
            self.assertTrue(r.value is not None, f"{src!r} failed to parse")
            self.assertEqual([], r.errors, f"{src!r} produced errors: {r.errors}")
            leftover = [t.value for t in r.tokens if t.value]
            self.assertEqual([], leftover, f"{src!r} left tokens unparsed: {leftover}")

    def test_existing_forms_unchanged(self):
        import pyast.expression as e
        # (source, expected top node type) — guards against the merge altering
        # how already-working expressions parse.
        cases = [
            ("a.b.c", e.DotExpression),
            ("io.read(5)", e.CallExpression),
            ("f(x)", e.CallExpression),
            ("arr[0]", e.CallExpression),   # `[]` lowers to a call
            ("a.b(x)", e.CallExpression),
        ]
        for src, node in cases:
            r = self._parse(src)
            self.assertIsInstance(r.value, node, f"{src!r} changed shape")
            self.assertEqual([], r.errors, f"{src!r} produced errors: {r.errors}")

    def test_non_identifier_dot_target_still_errors(self):
        for src in ('a.(b+c)', 'a."x"'):
            r = self._parse(src)
            self.assertTrue(any("Must be an identifier" in e.message for e in r.errors),
                            f"{src!r} should report a non-identifier dot target")
