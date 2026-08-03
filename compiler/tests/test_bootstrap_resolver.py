"""bootstrap/resolver.yafl — the ported name resolution must AGREE with
compiler/pyast/resolver.py.

Drives BOTH implementations over the SAME lookups against real corpus files:
for every declaration in a source (and every bare/simple/qualified spelling of
its name), `find_data` / `find_type` must return the same candidate set, in
the same order. That covers the prefix index (a query matches its own
`@`-hashed form), the type/data split, enum-variant indexing, and the
namespace-qualified spellings.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pyast.statement as s
import pyast.resolver as g
from parsing.tokenizer import tokenize
from parsing.parser import parse

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import _RUN_ENV, _CLANG_BUILD_FLAGS, _STATIC_LINK

_REPO = Path(__file__).parent.parent.parent
_BOOTSTRAP = _REPO / "bootstrap"
_CORPUS = [
    _REPO / "compiler" / "stdlib" / "args.yafl",
    _REPO / "compiler" / "stdlib" / "list.yafl",
    _REPO / "compiler" / "stdlib" / "string.yafl",
    _REPO / "examples" / "ylisp.yafl",
    _BOOTSTRAP / "ast" / "nodes.yafl",
]


def _queries(statements) -> list[str]:
    """Every declaration, asked for under each spelling a caller might use."""
    out: list[str] = []
    for st in statements:
        if not isinstance(st, s.NamedStatement):
            continue
        kind = "type" if isinstance(st, (s.ClassStatement, s.EnumStatement,
                                         s.TypeAliasStatement)) else "data"
        for spelling in {st.name, g.simple_name(st.name), g.bare_name(st.name)}:
            if spelling:
                out.append(f"{kind} {spelling}")
        # And the opposite kind, so the type/data split is exercised both ways.
        other = "data" if kind == "type" else "type"
        out.append(f"{other} {g.simple_name(st.name)}")
    return sorted(set(out))


def _python_answers(statements, queries: list[str]) -> list[str]:
    root = g.ResolverRoot(statements)
    out = []
    for q in queries:
        kind, _, name = q.partition(" ")
        bag = root.find_type(name) if kind == "type" else root.find_data(name)
        names = ",".join(r.unique_name for r in bag)
        out.append(f"{len(bag)}|{names}")
    return out


class TestBootstrapResolver(TestCase):
    _TIMEOUT = 400

    @classmethod
    def setUpClass(cls):
        from tests.testutil import shared_bootstrap_binary
        cls.binary = shared_bootstrap_binary()

    @classmethod
    def tearDownClass(cls):
        pass  # the shared binary is cache-owned

    def test_lookups_agree_with_python(self):
        for path in _CORPUS:
            with self.subTest(file=path.name):
                text = path.read_text()
                result = parse(tokenize(text, "x"))
                self.assertFalse(result.errors, f"{path.name}: python parse errors")
                queries = _queries(result.value)
                self.assertGreater(len(queries), 10)
                expected = _python_answers(result.value, queries)
                stdin = text + "\n?\n" + "\n".join(queries) + "\n"
                r = subprocess.run([self.binary, "resolve"], input=stdin,
                                   capture_output=True, timeout=90, text=True, env=_RUN_ENV)
                self.assertEqual(0, r.returncode, f"{path.name}: {r.stdout[:200]}")
                got = r.stdout.splitlines()
                self.assertEqual(len(expected), len(got), f"{path.name}: answer count")
                for q, e, gg in zip(queries, expected, got):
                    self.assertEqual(e, gg, f"{path.name} {q!r}: python {e!r}, bootstrap {gg!r}")
