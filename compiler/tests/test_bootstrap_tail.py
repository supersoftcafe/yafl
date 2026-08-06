"""bootstrap tail stage — the post-monomorphisation driver segment must
produce the same AST as compiler.py:588-611: the postmono segment, then lambda_lift
(captures become parameters where the helper is only ever called),
hoist_nested (closure-vs-global strategy, mutual SCCs coalesced into one
class), then tail_loop ([tail] bodies wrapped as LoopExpression with each
tail self-call a RecurExpression; hard errors otherwise).

Telescopes on the postmono contract: same corpus, same error-printing rule,
three passes further. The dump has teeth: Loop prints its carried param names,
Recur its ordinal; hoisted globals and $mutual:: closure classes appear as
top-level statements; lifted calls carry their threaded capture arguments.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import compiler as c
import lowering.complex_enums
import lowering.constants
import lowering.drops
import lowering.instances
import lowering.hashed
import lowering.derive_eq
import lowering.generics
import lowering.hoist_nested
import lowering.lambda_globals
import lowering.lambda_lift
import lowering.tail_loop
from parsing.tokenizer import tokenize
from parsing.parser import parse
from tests.astdump import dump

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import _RUN_ENV, _CLANG_BUILD_FLAGS, _STATIC_LINK

_REPO = Path(__file__).parent.parent.parent
_BOOTSTRAP = _REPO / "bootstrap"

_CORPUS = sorted((_REPO / "compiler" / "stdlib").glob("*.yafl")) \
    + sorted((_REPO / "examples").glob("*.yafl")) \
    + sorted((_REPO / "bootstrap").rglob("*.yafl")) \
    + sorted((Path(__file__).parent / "corpus_converge").glob("*.yafl"))

_CONVERGE = c.__dict__["__converge"]


class TestBootstrapTail(TestCase):
    _TIMEOUT = 2400

    @classmethod
    def setUpClass(cls):
        from tests.testutil import shared_bootstrap_binary
        cls.binary = shared_bootstrap_binary()

    @classmethod
    def tearDownClass(cls):
        pass  # the shared binary is cache-owned

    def _python_tail(self, text: str) -> str:
        from tests.testutil import cached_reference
        return cached_reference("tail", text,
                                lambda: self._python_tail_uncached(text))

    def _python_tail_uncached(self, text: str) -> str:
        result = parse(tokenize(text, "x"))
        self.assertFalse(result.errors, "python parse errors")
        statements, _resolver, _passes = _CONVERGE(result.value)
        statements = lowering.lambda_globals.lower_lambda_globals(statements)
        statements, dropped = lowering.drops.insert_drops(statements)
        if dropped:
            statements, _resolver, _p2 = _CONVERGE(statements)
        # Lower first-class `instance` statements before monomorphisation, as
        # compiler.py does — the port's dump modes all run through postmonoRes,
        # which includes it. Omitting it here made every stdlib file that
        # declares an `instance` (complex, float, traits, …) diverge.
        # Derived enum equality, then the [hashed] split, as compiler.py does.
        statements, _derived = lowering.derive_eq.derive_equality(statements)
        if _derived:
            statements, _resolver, _pd = _CONVERGE(statements)
        # [hashed] split before instance lowering, as compiler.py does.
        statements, _herrs, _hchanged = lowering.hashed.lower_hashed(statements)
        if _herrs:
            return "".join(f"{e}\n" for e in sorted(set(str(x) for x in _herrs)))
        if _hchanged:
            statements, _resolver, _ph = _CONVERGE(statements)
        statements, lowered = lowering.instances.lower_trait_instances(statements)
        if lowered:
            statements, _resolver, _p3b = _CONVERGE(statements)
        statements, poly_errors = lowering.generics.convert_generic_to_concrete(statements)
        if poly_errors:
            return "".join(f"{e}\n" for e in sorted(set(poly_errors)))
        unresolved = lowering.generics.report_unresolved_generic_calls(statements)
        if unresolved:
            return "".join(f"{e}\n" for e in sorted(set(unresolved)))
        statements, resolver3, _p3 = _CONVERGE(statements)
        statements = lowering.complex_enums.mark_complex_enums(statements)
        statements = lowering.constants.inline_constants(statements)
        statements = lowering.lambda_lift.lift_captured_calls(statements)
        statements = lowering.hoist_nested.hoist_nested_functions(statements)
        statements, tail_errors = lowering.tail_loop.lower_tail_loops(statements, resolver3)
        if tail_errors:
            return "".join(f"{e}\n" for e in sorted(set(tail_errors)))
        return dump(statements)

    def test_tail_ast_matches_python(self):
        for path in _CORPUS:
            with self.subTest(file=path.name):
                text = path.read_text()
                expected = self._python_tail(text).splitlines()
                r = subprocess.run([self.binary, "tail"], input=text,
                                   capture_output=True, timeout=240, text=True,
                                   env=_RUN_ENV)
                self.assertEqual(0, r.returncode,
                                 f"{path.name}: {r.stdout[:300]}")
                got = r.stdout.splitlines()
                for i, (e, gg) in enumerate(zip(expected, got)):
                    self.assertEqual(e, gg, f"{path.name}: tail AST "
                                            f"differs at line {i + 1}")
                self.assertEqual(len(expected), len(got),
                                 f"{path.name}: tail AST length differs")
