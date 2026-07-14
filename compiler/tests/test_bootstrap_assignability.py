"""bootstrap/assignability.yafl — the ported assignability must AGREE with
compiler/pyast/typespec (trivially_assignable_equals / _from).

Assignability is THREE-valued, and the third value carries the weight:

    True  — yes, structurally.
    False — no, definitively; a caller may discard the candidate.
    None  — not decidable YET (an unresolved name, or a generic placeholder
            that may fit once bound). The compile fixpoint asks again.

Collapsing None into False is the bug this contract exists to catch: overload
resolution would discard the candidate that was about to win, one pass before
its types resolved. So the diff below distinguishes all three answers (T/F/?)
over every ordered pair of a spec corpus — atoms, unions, tuples (including
the named/default binding cases and the 1-tuple/element equivalence), enum
narrowings, and placeholders.
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
from parsing.tokenizer import LineRef, tokenize
from parsing.parser import parse

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import _RUN_ENV, _CLANG_BUILD_FLAGS, _STATIC_LINK

_REPO = Path(__file__).parent.parent.parent
_BOOTSTRAP = _REPO / "bootstrap"
_LR = LineRef("x", 0, 0)


def _spec(text: str):
    """The Python spec for a case spelling — the same grammar the bootstrap's
    parseSpecText reads (see tests/test_bootstrap_specs.py)."""
    text = text.strip()
    if not text:
        return None
    kind = text[0]
    if kind == "i":
        return t.BuiltinSpec(_LR, "bigint")
    if kind == "b":
        return t.BuiltinSpec(_LR, "bool")
    if kind == "s":
        return t.BuiltinSpec(_LR, "str")
    if kind == "G":
        return t.GenericPlaceholderSpec(_LR, text.split(":", 1)[1])
    if kind == "C":
        return t.ClassSpec(_LR, text.split(":", 1)[1])
    if kind == "E":
        body = text.split(":", 1)[1]
        root, _, leaves = body.partition(":")
        names = tuple(leaves.split("|")) if leaves else ()
        return t.EnumSpec(_LR, root, frozenset(names), names, ())
    if kind == "U":
        inner = text[text.index("(") + 1: -1]
        return t.CombinationSpec(_LR, tuple(_spec(p) for p in _split(inner)))
    if kind == "T":
        inner = text[text.index("(") + 1: -1]
        entries = []
        for part in _split(inner):
            if not part:
                continue
            name, _, ty = part.partition("=")
            entries.append(t.TupleEntrySpec(None if name == "_" else name,
                                            _spec(ty) if ty else None))
        return t.TupleSpec(_LR, entries)
    raise AssertionError(f"bad case spelling: {text!r}")


def _split(text: str) -> list[str]:
    """Split on top-level commas (a nested U(...)/T(...) may contain them)."""
    out, depth, cur = [], 0, ""
    for ch in text:
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        cur += ch
    out.append(cur)
    return out


# A class spec must resolve against a REAL declaration — its rule asks the
# resolver for the class's parents. (With no declaration Python's own rule
# raises IndexError; the compiler never hits that because every spec it holds
# came from a declaration.) So the contract carries a source, and both sides
# resolve against it.
_SOURCE = """namespace Test

interface Shape<T>
  fun area(s: T): Int

class [final] Circle(radius: Int): Shape<Circle>

class [final] Foo(x: Int)

class [final] Bar(y: Int)
"""


def _decls():
    """The declared classes, by bare name → unique (hashed) name."""
    result = parse(tokenize(_SOURCE, "x"))
    assert not result.errors, result.errors
    names = {}
    for st in result.value:
        if isinstance(st, s.ClassStatement):
            names[g.bare_name(st.name)] = st.name
    return result.value, names


_STATEMENTS, _NAMES = _decls()


def _py(a: str, b: str) -> str:
    r = t.trivially_assignable_equals(g.ResolverRoot(_STATEMENTS),
                                      _spec(a), _spec(b))
    return "T" if r is True else ("F" if r is False else "?")


# Atoms, unions, tuples, enum narrowings, placeholders — and the shapes where
# the three-valued rule actually bites: a 1-tuple against its element, a named
# tuple against a positional one, a class against its interface.
_CORPUS = [
    "i", "b", "s",
    f"C:{_NAMES['Foo']}", f"C:{_NAMES['Bar']}",
    f"C:{_NAMES['Shape']}", f"C:{_NAMES['Circle']}",   # interface + implementor
    "E:En@1:LA|LB", "E:En@1:LA", "E:En@1:",            # last = Never (no leaves)
    "G:T@1", "G:U@2",
    "U(i,b)", f"U(i,C:{_NAMES['Foo']})", "U(i,b,s)",
    "T(_=i)",                                          # 1-tuple of Int
    "T(_=i,_=b)",
    "T(x=i,y=b)",
    "T(y=b,x=i)",                                      # same fields, reordered
    "T(_=U(i,b))",
    "T(_=G:T@1)",
]


class TestBootstrapAssignability(TestCase):
    _TIMEOUT = 400

    @classmethod
    def setUpClass(cls):
        import compiler as c
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

    def test_assignability_agrees_with_python(self):
        lines, expected = [], []
        for a, b in itertools.product(_CORPUS, repeat=2):
            lines.append(f"{a} ;; {b}")
            expected.append(_py(a, b))
        self.assertGreater(len(lines), 300)
        # The contract is only meaningful if all three answers actually occur.
        for verdict in ("T", "F", "?"):
            self.assertIn(verdict, expected, f"corpus never produces {verdict}")

        stdin = _SOURCE + "\n?\n" + "\n".join(lines) + "\n"
        r = subprocess.run([self.binary, "assign"], input=stdin,
                           capture_output=True, timeout=90, text=True, env=_RUN_ENV)
        self.assertEqual(0, r.returncode)
        got = r.stdout.splitlines()
        self.assertEqual(len(expected), len(got), "case count differs")
        for line, e, gg in zip(lines, expected, got):
            self.assertEqual(e, gg, f"case {line!r}: python {e!r}, bootstrap {gg!r}")
