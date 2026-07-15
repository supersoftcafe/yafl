"""bootstrap literals stage — the post-monomorphisation driver segment must
produce the same AST as compiler.py:588-614: the inline segment, then the string and bigint literal hoists — lambda_lift
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
import lowering.generics
import lowering.ast_inline
import lowering.integers
import lowering.strings
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
    + sorted((_REPO / "bootstrap").glob("*.yafl")) \
    + sorted((Path(__file__).parent / "corpus_converge").glob("*.yafl"))

_CONVERGE = c.__dict__["__converge"]


class TestBootstrapLiterals(TestCase):
    _TIMEOUT = 2400

    @classmethod
    def setUpClass(cls):
        sys.setrecursionlimit(20000)
        inputs = [c.Input(p.read_text(), p.name) for p in sorted(_BOOTSTRAP.glob("*.yafl"))]
        c_code = c.compile(inputs, use_stdlib=True, just_testing=False, optimization_level=1)
        assert c_code, "bootstrap compilation failed"
        with tempfile.NamedTemporaryFile(suffix="", delete=False) as tmp:
            cls.binary = tmp.name
        r = subprocess.run(
            ["clang", "-g", "-x", "c", "-", "-O0", *_CLANG_BUILD_FLAGS, *_STATIC_LINK,
             "-o", cls.binary],
            input=c_code, text=True, capture_output=True, timeout=90)
        assert r.returncode == 0, f"clang failed:\n{r.stderr[:2000]}"

    @classmethod
    def tearDownClass(cls):
        try:
            os.unlink(cls.binary)
        except OSError:
            pass

    def _python_literals(self, text: str) -> str:
        result = parse(tokenize(text, "x"))
        self.assertFalse(result.errors, "python parse errors")
        statements, _resolver, _passes = _CONVERGE(result.value)
        statements = lowering.lambda_globals.lower_lambda_globals(statements)
        statements, dropped = lowering.drops.insert_drops(statements)
        if dropped:
            statements, _resolver, _p2 = _CONVERGE(statements)
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
        statements = lowering.ast_inline.inline_ast(statements, 1)
        statements = lowering.strings.fix_global_strings(statements)
        statements = lowering.integers.fix_global_integers(statements)
        return dump(statements)

    def test_literals_ast_matches_python(self):
        for path in _CORPUS:
            with self.subTest(file=path.name):
                text = path.read_text()
                expected = self._python_literals(text).splitlines()
                r = subprocess.run([self.binary, "literals"], input=text,
                                   capture_output=True, timeout=240, text=True,
                                   env=_RUN_ENV)
                self.assertEqual(0, r.returncode,
                                 f"{path.name}: {r.stdout[:300]}")
                got = r.stdout.splitlines()
                for i, (e, gg) in enumerate(zip(expected, got)):
                    self.assertEqual(e, gg, f"{path.name}: literals AST "
                                            f"differs at line {i + 1}")
                self.assertEqual(len(expected), len(got),
                                 f"{path.name}: literals AST length differs")
