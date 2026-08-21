"""End-to-end tests for the System::Json stdlib converter.

`System::Json` is a pure String→JsonValue / JsonValue→String converter (no IO,
no async): `parse(s)` reads, `stringify(v)` / `stringify(v, pretty)` write.
Tests embed JSON as string literals and either return a classification exit
code or print the stringified result and capture stdout.
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
from tests.testutil import TimedTestCase as TestCase

import compiler as c
from tests.testutil import _CLANG_BUILD_FLAGS, _STATIC_LINK, _RUN_ENV


_HARNESS_PRELUDE = """namespace Main
import System
import System::Json

fun onResult(r: JsonValue|JsonParseError, f: (:JsonValue): System::Int): System::Int
  ret match(r)
    (v: JsonValue)      => f(v)
    (e: JsonParseError) => 90
"""


def _yafl_str(text: str) -> str:
    """Embed `text` as a YAFL string literal (escape `\\` and `"`; the
    string-literal encoder handles other bytes)."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _build(binary_src: str) -> str:
    c_code = c.compile([c.Input(binary_src, "test.yafl")], use_stdlib=True, just_testing=False)
    assert c_code, "yafl compilation produced no output (type errors?)"
    with tempfile.NamedTemporaryFile(suffix="", delete=False) as tmp:
        binary = tmp.name
    result = subprocess.run(
        ["clang", "-g", "-x", "c", "-", "-O0", *_CLANG_BUILD_FLAGS, *_STATIC_LINK, "-o", binary],
        input=c_code, text=True, capture_output=True, timeout=30,
    )
    assert result.returncode == 0, f"clang failed:\n{result.stderr}"
    return binary


def _run_exit(test_source: str, timeout: int = 5) -> int:
    if _COLLECT is not None:
        _COLLECT.append(("exit", test_source))
        return 0
    if ("exit", test_source) in _RESULTS:
        return _RESULTS[("exit", test_source)]
    binary = _build(test_source)
    try:
        return subprocess.run([binary], capture_output=True, timeout=timeout, env=_RUN_ENV).returncode
    finally:
        try:
            os.unlink(binary)
        except OSError:
            pass


def _run_stdout(test_source: str, timeout: int = 5, _batched: bool = True) -> str:
    if _batched:
        if _COLLECT is not None:
            _COLLECT.append(("out", test_source))
            return ""
        if ("out", test_source) in _RESULTS:
            return _RESULTS[("out", test_source)]
    binary = _build(test_source)
    try:
        run = subprocess.run([binary], capture_output=True, timeout=timeout, env=_RUN_ENV)
        assert run.returncode == 0, f"program exited {run.returncode}"
        return run.stdout.decode("utf-8", errors="replace")
    finally:
        try:
            os.unlink(binary)
        except OSError:
            pass


# ── ONE compile for the whole module ─────────────────────────────────────────
# Every test here builds `_HARNESS_PRELUDE + <its own functions>` and compiles
# it, so the module paid 19 whole-stdlib compiles to run 19 tiny programs.
# They stack into one unit instead: the prelude ONCE (a namespace does not
# scope unqualified lookup, so one `onResult` serves every program), each
# test's functions suffixed with its index so nothing collides, and a driver
# that prints a marker around each. Python splits the markers back apart —
# YAFL just prints lines.

_FUN_DEF = re.compile(r"(?m)^fun\s+([A-Za-z_]\w*)")
_MARK = re.compile(r"\n@@(\d+|end)@@\n")

_COLLECT: "list | None" = None       # sources being gathered, or None to serve
_RESULTS: "dict[tuple, int | str]" = {}


def _suffix(tail: str, i: int) -> str:
    """Index every function this program defines, references included, so two
    programs' `classify`/`emit`/`main` cannot collide in a shared unit."""
    for name in sorted(set(_FUN_DEF.findall(tail)), key=len, reverse=True):
        tail = re.sub(rf"\b{name}\b", f"{name}_{i}", tail)
    return tail


def _batch(entries: "list[tuple[str, str]]") -> None:
    """Compile+run every collected program as one unit; fill _RESULTS."""
    if not entries:
        return
    parts = [_HARNESS_PRELUDE]
    for i, (_kind, src) in enumerate(entries):
        parts.append("\n" + _suffix(src[len(_HARNESS_PRELUDE):], i) + "\n")
    parts.append("\nfun main(): System::Int\n")
    for i, (kind, _src) in enumerate(entries):
        parts.append(f'  print("\\n@@{i}@@\\n")\n')
        # An exit-code test reports an Int, so print it; a stdout test prints
        # its own text and its result is noise.
        parts.append(f"  print(stringify(JsonInt(main_{i}())))\n"
                     if kind == "exit"
                     else f"  let _ = main_{i}()\n")
    parts.append('  print("\\n@@end@@\\n")\n  ret 0\n')

    out = _run_stdout("".join(parts), timeout=120, _batched=False)
    cuts = list(_MARK.finditer(out))
    for m, nxt in zip(cuts, cuts[1:]):
        if m.group(1) == "end":
            break
        i = int(m.group(1))
        payload = out[m.end():nxt.start()]
        kind, src = entries[i]
        _RESULTS[(kind, src)] = int(payload) if kind == "exit" else payload


def setUpModule():
    """Run every test once with the runners recording instead of compiling,
    then compile the lot as a single unit."""
    global _COLLECT
    _COLLECT = []
    for cls in (TestJsonComposite, TestJsonInteger, TestLargeString):
        for name in sorted(n for n in dir(cls) if n.startswith("test")):
            try:
                getattr(cls(name), name)()
            except Exception:
                pass          # collect mode: only the sources matter
    entries, _COLLECT = _COLLECT, None
    seen, uniq = set(), []
    for e in entries:
        if e not in seen:
            seen.add(e); uniq.append(e)
    _batch(uniq)


class TestJsonComposite(TestCase):

    def _run(self, json_text: str, classify_body: str) -> int:
        src = _HARNESS_PRELUDE + f"""
fun classify(v: JsonValue): System::Int
{classify_body}

fun main(): System::Int
  ret onResult(parse({_yafl_str(json_text)}), classify)
"""
        return _run_exit(src)

    def test_parse_empty_array(self):
        body = """  ret match(v)
    (a: JsonArr) => match(head<JsonValue>(a.elements))
      (n: None)      => 0
      (v: JsonValue) => 1
    () => 99"""
        self.assertEqual(0, self._run("[]", body))

    def test_parse_array_three_numbers(self):
        body = """  ret match(v)
    (a: JsonArr) => sumArr(a.elements)
    () => 99

fun sumArr(l: List<JsonValue>): System::Int
  let h = head<JsonValue>(l)
  ret match(h)
    (n: None) => 0
    (v: JsonValue) => match(v)
      (n: JsonInt)       => n.intValue + sumArr(tail<JsonValue>(l))
      (other: JsonValue) => 99 + sumArr(tail<JsonValue>(l))"""
        self.assertEqual(60, self._run("[10, 20, 30]", body))

    def test_parse_nested_array(self):
        body = """  ret match(v)
    (a: JsonArr) => lenArr(a.elements)
    () => 99

fun lenArr(l: List<JsonValue>): System::Int
  let h = head<JsonValue>(l)
  ret match(h)
    (n: None)      => 0
    (v: JsonValue) => 1 + lenArr(tail<JsonValue>(l))"""
        self.assertEqual(2, self._run("[[1], [2, 3]]", body))

    def test_parse_object_with_one_entry(self):
        body = """  ret match(v)
    (o: JsonObj) => lookupX(o.pairs)
    () => 99

fun unwrapInt(v: JsonValue): System::Int
  ret match(v)
    (n: JsonInt)       => n.intValue
    (other: JsonValue) => 98

fun lookupX(l: List<JsonPair>): System::Int
  let h = head<JsonPair>(l)
  ret match(h)
    (n: None)     => 99
    (p: JsonPair) => p.key == "x" ? unwrapInt(p.value) : lookupX(tail<JsonPair>(l))"""
        self.assertEqual(7, self._run('{"x": 7}', body))

    def test_parse_object_three_entries_count(self):
        body = """  ret match(v)
    (o: JsonObj) => lenObj(o.pairs)
    () => 99

fun lenObj(l: List<JsonPair>): System::Int
  let h = head<JsonPair>(l)
  ret match(h)
    (n: None)     => 0
    (p: JsonPair) => 1 + lenObj(tail<JsonPair>(l))"""
        self.assertEqual(3, self._run('{"a": 1, "b": 2, "c": 3}', body))

    def test_stringify_scalar(self):
        src = _HARNESS_PRELUDE + """
fun main(): System::Int
  print(stringify(JsonNum(42.0)))
  ret 0
"""
        self.assertEqual("42", _run_stdout(src))

    def test_stringify_pretty_overload(self):
        # stringify(v, true) indents; empty containers stay inline. Parses the
        # printed form back with Python to assert structure plus the layout.
        import json as pyjson
        src = _HARNESS_PRELUDE + f"""
fun emit(v: JsonValue): System::Int
  print(stringify(v, true))
  ret 0

fun main(): System::Int
  ret onResult(parse({_yafl_str('{"a":[1,2],"b":{}}')}), emit)
"""
        out = _run_stdout(src)
        self.assertEqual({"a": [1, 2], "b": {}}, pyjson.loads(out))
        self.assertIn("\n  ", out, "pretty output should be indented")
        self.assertIn('"b": {}', out, "empty object should stay inline")

    def _round_trip(self, original: str) -> str:
        src = _HARNESS_PRELUDE + f"""
fun emit(v: JsonValue): System::Int
  print(stringify(v))
  ret 0

fun main(): System::Int
  ret onResult(parse({_yafl_str(original)}), emit)
"""
        return _run_stdout(src, timeout=30)

    def test_round_trip_scalar_number(self):
        self.assertEqual("42", self._round_trip("42"))

    def test_round_trip_array(self):
        self.assertEqual("[1, 2, 3]", self._round_trip("[1, 2, 3]"))

    def test_round_trip_object_with_nested_array(self):
        import json as pyjson
        original = '{"name": "yafl", "values": [1, 2, 3], "ok": true}'
        printed = self._round_trip(original)
        self.assertEqual(pyjson.loads(original), pyjson.loads(printed))

    def test_parse_mixed_nested(self):
        body = """  ret match(v)
    (o: JsonObj) => sumInner(o.pairs)
    () => 99

fun sumInner(l: List<JsonPair>): System::Int
  let h = head<JsonPair>(l)
  ret match(h)
    (n: None)     => 0
    (p: JsonPair) => match(p.value)
      (a: JsonArr)       => sumArr(a.elements)
      (other: JsonValue) => 0

fun sumArr(l: List<JsonValue>): System::Int
  let h = head<JsonValue>(l)
  ret match(h)
    (n: None)      => 0
    (v: JsonValue) => match(v)
      (o: JsonObj)       => firstNum(o.pairs) + sumArr(tail<JsonValue>(l))
      (other: JsonValue) => sumArr(tail<JsonValue>(l))

fun firstNum(l: List<JsonPair>): System::Int
  let h = head<JsonPair>(l)
  ret match(h)
    (n: None)     => 0
    (p: JsonPair) => match(p.value)
      (n: JsonInt)       => n.intValue
      (other: JsonValue) => 0"""
        self.assertEqual(13, self._run('{"items": [{"v": 5}, {"v": 8}]}', body))


class TestJsonInteger(TestCase):
    """Round-trips and edge cases specific to JsonInt."""

    def _round_trip(self, original: str) -> str:
        src = _HARNESS_PRELUDE + f"""
fun emit(v: JsonValue): System::Int
  print(stringify(v))
  ret 0

fun main(): System::Int
  ret onResult(parse({_yafl_str(original)}), emit)
"""
        return _run_stdout(src)

    def test_int_round_trip_small(self):
        self.assertEqual("42", self._round_trip("42"))

    def test_int_round_trip_zero(self):
        self.assertEqual("0", self._round_trip("0"))

    def test_int_round_trip_large(self):
        # Larger than int32 — exercises bigint precision through the parser.
        self.assertEqual("123456789012345", self._round_trip("123456789012345"))

    def test_float_round_trip(self):
        # 0.5 is exactly representable, so the printer's text matches the input.
        self.assertEqual("0.5", self._round_trip("0.5"))


class TestLargeString(TestCase):
    """Large string bodies parse to a single JsonStr regardless of size."""

    def _classify_string(self, json_text: str, body: str) -> int:
        src = _HARNESS_PRELUDE + f"""
fun classify(v: JsonValue): System::Int
{body}

fun main(): System::Int
  ret onResult(parse({_yafl_str(json_text)}), classify)
"""
        return _run_exit(src, timeout=30)

    def test_short_string_is_jsonstr(self):
        body = """  ret match(v)
    (s: JsonStr) => 1
    () => 0"""
        self.assertEqual(1, self._classify_string('"' + ("x" * 100) + '"', body))

    def test_large_string_is_jsonstr(self):
        body = """  ret match(v)
    (s: JsonStr) => 1
    () => 0"""
        self.assertEqual(1, self._classify_string('"' + ("x" * 15000) + '"', body))

    def test_large_string_length_preserved(self):
        body = """  ret match(v)
    (s: JsonStr) => System::length(s.strValue) % 256
    () => 99"""
        self.assertEqual(30000 % 256, self._classify_string('"' + ("x" * 30000) + '"', body))

    def test_large_string_round_trip(self):
        original = '"' + ("x" * 30000) + '"'
        src = _HARNESS_PRELUDE + f"""
fun emit(v: JsonValue): System::Int
  print(stringify(v))
  ret 0

fun main(): System::Int
  ret onResult(parse({_yafl_str(original)}), emit)
"""
        self.assertEqual(original, _run_stdout(src, timeout=30))
