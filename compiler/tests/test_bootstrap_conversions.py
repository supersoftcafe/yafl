"""bootstrap/conversions.yafl — the ported conversion DECISION must AGREE with
compiler/pyast/expression/conversion.py (needs_conversion).

This is the single most consequential predicate in the compiler: the compile
pass inserts a ConvertExpression exactly when this says yes, and codegen NEVER
converts — a conversion still needed at generate time is a hard error, and one
inserted that wasn't needed is a silent miscompile. So a disagreement here is
never "just" a type error.

The cases are the ones that actually bite, and each has drawn blood before:
  * boxing a value into a union that holds it;
  * a 1-tuple and its element (ONE type, TWO representations — wrap/unwrap);
  * a tuple into a union with a matching tuple variant;
  * a NAME-DIRECTED reorder, whose ids are IDENTICAL on both sides (an id is
    positional types only) and which must still rebuild the value;
  * a [final] class member of a union, represented structurally as its field
    tuple (this is what simple_classes rewrites it to).
"""
from __future__ import annotations

import itertools
import os
import subprocess
import tempfile
from pathlib import Path

import pyast.typespec as t
import pyast.resolver as g
import pyast.statement as s
from pyast.expression.conversion import needs_conversion
from parsing.tokenizer import tokenize
from parsing.parser import parse

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import _RUN_ENV, _CLANG_BUILD_FLAGS, _STATIC_LINK
from tests.test_bootstrap_assignability import _spec, _SOURCE, _STATEMENTS, _NAMES

_REPO = Path(__file__).parent.parent.parent
_BOOTSTRAP = _REPO / "bootstrap"


def _py(a: str, b: str) -> str:
    r = needs_conversion(_spec(a), _spec(b), g.ResolverRoot(_STATEMENTS))
    return "Y" if r else "N"


_CORPUS = [
    "i", "b", "s",
    f"C:{_NAMES['Foo']}",
    "E:En@1:LA|LB", "E:En@1:LA", "E:En@1:",            # last = Never
    "G:T@1",
    "U(i,b)", "U(i,b,s)", f"U(i,C:{_NAMES['Foo']})",
    "T(_=i)",                                          # 1-tuple of Int
    "T(_=i,_=b)",
    "T(x=i,y=b)",
    "T(y=b,x=i)",                                      # SAME ids, reordered
    "T(_=U(i,b))",
    "U(T(_=i,_=b),s)",                                 # union w/ a tuple variant
]


class TestBootstrapConversions(TestCase):
    _TIMEOUT = 400

    @classmethod
    def setUpClass(cls):
        from tests.testutil import shared_bootstrap_binary
        cls.binary = shared_bootstrap_binary()

    @classmethod
    def tearDownClass(cls):
        pass  # the shared binary is cache-owned

    def test_conversion_decision_agrees_with_python(self):
        lines, expected = [], []
        for a, b in itertools.product(_CORPUS, repeat=2):
            lines.append(f"{a} ;; {b}")
            expected.append(_py(a, b))
        self.assertGreater(len(lines), 200)
        # Only meaningful if the corpus actually exercises both answers.
        self.assertIn("Y", expected)
        self.assertIn("N", expected)

        stdin = _SOURCE + "\n?\n" + "\n".join(lines) + "\n"
        r = subprocess.run([self.binary, "convert"], input=stdin, capture_output=True,
                           timeout=90, text=True, env=_RUN_ENV)
        self.assertEqual(0, r.returncode, r.stdout[:200])
        got = r.stdout.splitlines()
        self.assertEqual(len(expected), len(got), "case count differs")
        for line, e, gg in zip(lines, expected, got):
            self.assertEqual(e, gg, f"case {line!r}: python {e!r}, bootstrap {gg!r}")
