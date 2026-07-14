"""bootstrap/specs.yafl + algebra.yafl — the ported typespec must AGREE with
compiler/pyast/typespec over the same cases.

The same diff methodology as the parser port: a compact spec spelling drives
BOTH implementations over generated cases, and the answers must match —
`uid` (as_unique_id_str: the structural identity every layout, mangle and
union dedup reads through), `meet` (the fixpoint's refinement rule, including
its CONFLICT verdict), and `bind_tuple_entries` (the one binding shared by
assignability, unification, conversion and calls).
"""
from __future__ import annotations

import itertools
import os
import subprocess
import tempfile
from pathlib import Path

import pyast.typespec as t
from parsing.tokenizer import LineRef

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import _RUN_ENV, _CLANG_BUILD_FLAGS, _STATIC_LINK

_REPO = Path(__file__).parent.parent.parent
_BOOTSTRAP = _REPO / "bootstrap"
_LR = LineRef("x", 0, 0)


def _spec(text: str) -> t.TypeSpec | None:
    """The Python spec for a case spelling (mirrors specs.yafl parseSpecText)."""
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
        leaf_names = tuple(leaves.split("|")) if leaves else ()
        return t.EnumSpec(_LR, root, frozenset(leaf_names), leaf_names, ())
    if kind == "U":
        inner = text[text.index("(") + 1: -1]
        return t.CombinationSpec(_LR, tuple(_spec(p) for p in inner.split(",")))
    raise AssertionError(f"bad case spelling: {text!r}")


def _entries(text: str) -> list[t.TupleEntrySpec]:
    out = []
    for part in text.split(";"):
        part = part.strip()
        has_default = part.endswith("!")
        core = part[:-1] if has_default else part
        name, _, ty = core.partition("=")
        out.append(t.TupleEntrySpec(
            None if name == "_" else name,
            _spec(ty) if ty else None,
            t.BuiltinSpec(_LR, "bigint") if has_default else None))
    return out


def _py_uid(spec) -> str:
    u = spec.as_unique_id_str() if spec is not None else None
    return u if u else ("-" if spec is not None else "!")


def _py_meet(a: str, b: str) -> str:
    from pyast.typespec.algebra import meet, _CONFLICT
    r = meet(_spec(a), _spec(b))
    if r is _CONFLICT:
        return "CONFLICT"
    if r is None:
        return "NONE"
    return r.as_unique_id_str() or "-"


def _py_bind(decl: str, supplied: str) -> str:
    names = [None if n == "_" else n for n in supplied.split(",")]
    binding = t.bind_tuple_entries(_entries(decl), names)
    if binding is None:
        return "NONE"
    if not binding:
        return "()"
    return ",".join("-1" if b is None else str(b) for b in binding)


_ATOMS = ["i", "b", "s", "C:Foo@1", "C:Bar@2", "E:En@1:LA|LB", "E:En@1:LA", "G:T@1"]


def _cases() -> tuple[list[str], list[str]]:
    """(driver lines, expected answers) — the two implementations' contract."""
    lines: list[str] = []
    expected: list[str] = []
    for a in _ATOMS:
        lines.append(f"uid {a}")
        expected.append(_py_uid(_spec(a)))
    unions = [f"U({x},{y})" for x, y in itertools.combinations(_ATOMS, 2)]
    for u in unions:
        lines.append(f"uid {u}")
        expected.append(_py_uid(_spec(u)))
    for a, b in itertools.product(_ATOMS + unions[:6], repeat=2):
        lines.append(f"meet {a} ;; {b}")
        expected.append(_py_meet(a, b))
    binds = [
        ("x=i;y=b", "_,_"), ("x=i;y=b", "_"), ("x=i;y=b!", "_"),
        ("x=i;y=b", "y,x"), ("x=i;y=b", "y"), ("x=i;y=b!", "x"),
        ("x=i;y=b", "_,_,_"), ("x=i", "z"), ("x=i;y=b!;z=s!", "x"),
    ]
    for decl, sup in binds:
        lines.append(f"bind {decl} ;; {sup}")
        expected.append(_py_bind(decl, sup))
    return lines, expected


class TestBootstrapSpecs(TestCase):
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

    def test_specs_agree_with_python(self):
        lines, expected = _cases()
        self.assertGreater(len(lines), 200)
        r = subprocess.run([self.binary, "specs"], input="\n".join(lines) + "\n",
                           capture_output=True, timeout=60, text=True, env=_RUN_ENV)
        self.assertEqual(0, r.returncode)
        got = r.stdout.splitlines()
        self.assertEqual(len(expected), len(got), "case count differs")
        for line, e, g in zip(lines, expected, got):
            self.assertEqual(e, g, f"case {line!r}: python {e!r}, bootstrap {g!r}")
