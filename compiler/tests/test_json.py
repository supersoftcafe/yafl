"""End-to-end tests for the JSON DOM parser/printer at samples/json.yafl."""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from unittest import TestCase

import compiler as c
from tests.testutil import _CLANG_BUILD_FLAGS, _RUN_ENV


_SAMPLE_DIR = Path(__file__).parent.parent / "samples"
_JSON_YAFL = (_SAMPLE_DIR / "json.yafl").read_text()


# Shared helper functions, one set of definitions reused across tests.
_HARNESS_PRELUDE = """namespace Main
import System
import System::IO
import Sample::Json

fun handleParse(r: (state: ParseState, v: JsonValue|JsonParseError),
                onValue: (:JsonValue): System::Int): System::Int
  ret match(r.v)
    (val: JsonValue)    => onValue(val)
    (e: JsonParseError) => 90

fun runOnHandle(h: IO, onValue: (:JsonValue): System::Int): System::Int
  let r = parseValue(ParseState(h, "", 0))
  ret handleParse(r, onValue)

fun runOnPath(path: System::String, onValue: (:JsonValue): System::Int): System::Int
  ret match(open_read(path))
    (h: IO) => runOnHandle(h, onValue)
    (e: IOError) => 80
"""


def _run_with_json_module(test_source: str, timeout: int = 5) -> int:
    c_code = c.compile(
        [c.Input(_JSON_YAFL, "json.yafl"), c.Input(test_source, "test.yafl")],
        use_stdlib=True, just_testing=False)
    assert c_code, "yafl compilation produced no output (type errors?)"
    with tempfile.NamedTemporaryFile(suffix="", delete=False) as tmp:
        binary = tmp.name
    try:
        result = subprocess.run(
            ["clang", "-g", "-x", "c", "-", "-O0", *_CLANG_BUILD_FLAGS, "-l", "yafl", "-l", "m", "-o", binary],
            input=c_code, text=True, capture_output=True, timeout=30,
        )
        assert result.returncode == 0, f"clang failed:\n{result.stderr}"
        run = subprocess.run([binary], capture_output=True, timeout=timeout, env=_RUN_ENV)
        return run.returncode
    finally:
        try:
            os.unlink(binary)
        except OSError:
            pass


class TestJsonScalars(TestCase):

    def _run(self, json_text: str, classify_body: str) -> int:
        """Run the parser on `json_text` and dispatch through `classify_body`."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "in.json")
            with open(path, "w") as f:
                f.write(json_text)
            src = _HARNESS_PRELUDE + f"""
fun classify(v: JsonValue): System::Int
{classify_body}

fun main(): System::Int
  ret runOnPath("{path}", classify)
"""
            return _run_with_json_module(src)

    def test_parse_true(self):
        body = """  ret match(v)
    (t: JsonTrue)  => 1
    (f: JsonFalse) => 2
    () => 99"""
        self.assertEqual(1, self._run("true", body))

    def test_parse_false(self):
        body = """  ret match(v)
    (t: JsonTrue)  => 1
    (f: JsonFalse) => 2
    () => 99"""
        self.assertEqual(2, self._run("false", body))

    def test_parse_null(self):
        body = """  ret match(v)
    (n: JsonNull) => 3
    () => 99"""
        self.assertEqual(3, self._run("null", body))

    def test_parse_number_integer(self):
        body = """  ret match(v)
    (n: JsonNum) => System::Int(n.numValue)
    () => 99"""
        self.assertEqual(42, self._run("42", body))

    def test_parse_number_with_leading_whitespace(self):
        body = """  ret match(v)
    (n: JsonNum) => System::Int(n.numValue)
    () => 99"""
        self.assertEqual(7, self._run("  \n\t7  ", body))

    def test_parse_simple_string(self):
        # Parse "hi" → JsonStr("hi") → length is 2.
        body = """  ret match(v)
    (s: JsonStr) => System::length(s.strValue)
    () => 99"""
        self.assertEqual(2, self._run('"hi"', body))

    def test_parse_string_with_escape(self):
        # Parse "a\nb" — three bytes: 'a', '\n', 'b'.
        body = """  ret match(v)
    (s: JsonStr) => System::length(s.strValue)
    () => 99"""
        self.assertEqual(3, self._run('"a\\nb"', body))

    def test_parse_empty_string(self):
        body = """  ret match(v)
    (s: JsonStr) => System::length(s.strValue)
    () => 99"""
        self.assertEqual(0, self._run('""', body))


class TestJsonComposite(TestCase):

    def _run(self, json_text: str, classify_body: str) -> int:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "in.json")
            with open(path, "w") as f:
                f.write(json_text)
            src = _HARNESS_PRELUDE + f"""
fun classify(v: JsonValue): System::Int
{classify_body}

fun main(): System::Int
  ret runOnPath("{path}", classify)
"""
            return _run_with_json_module(src)

    def test_parse_empty_array(self):
        body = """  ret match(v)
    (a: JsonArr) => match(a.elements)
      (n: JArrNil)  => 0
      (c: JArrCons) => 1
    () => 99"""
        self.assertEqual(0, self._run("[]", body))

    def test_parse_array_three_numbers(self):
        # [10, 20, 30] — sum the elements (each via the JsonNum extraction).
        body = """  ret match(v)
    (a: JsonArr) => sumArr(a.elements)
    () => 99

fun sumArr(l: JsonArrayList): System::Int
  ret match(l)
    (n: JArrNil)  => 0
    (c: JArrCons) => match(c.head)
      (n: JsonNum)       => System::Int(n.numValue) + sumArr(c.tail)
      (other: JsonValue) => 99 + sumArr(c.tail)"""
        self.assertEqual(60, self._run("[10, 20, 30]", body))

    def test_parse_nested_array(self):
        # [[1], [2, 3]] — count elements at top level (2).
        body = """  ret match(v)
    (a: JsonArr) => lenArr(a.elements)
    () => 99

fun lenArr(l: JsonArrayList): System::Int
  ret match(l)
    (n: JArrNil)  => 0
    (c: JArrCons) => 1 + lenArr(c.tail)"""
        self.assertEqual(2, self._run("[[1], [2, 3]]", body))

    def test_parse_object_with_one_entry(self):
        # {"x": 7} — find "x" and return its number.
        body = """  ret match(v)
    (o: JsonObj) => lookupX(o.pairs)
    () => 99

fun unwrapNum(v: JsonValue): System::Int
  ret match(v)
    (n: JsonNum)       => System::Int(n.numValue)
    (other: JsonValue) => 98

fun lookupX(l: JsonObjectList): System::Int
  ret match(l)
    (n: JObjNil)  => 99
    (c: JObjCons) => c.key = "x" ? unwrapNum(c.value) : lookupX(c.tail)"""
        self.assertEqual(7, self._run('{"x": 7}', body))

    def test_parse_object_three_entries_count(self):
        body = """  ret match(v)
    (o: JsonObj) => lenObj(o.pairs)
    () => 99

fun lenObj(l: JsonObjectList): System::Int
  ret match(l)
    (n: JObjNil)  => 0
    (c: JObjCons) => 1 + lenObj(c.tail)"""
        self.assertEqual(3, self._run('{"a": 1, "b": 2, "c": 3}', body))

    def test_print_scalar_to_file(self):
        # Print JsonNum(42) to a file and verify the bytes.
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "out.json")
            src = _HARNESS_PRELUDE + f"""
fun doPrint(h: IO, v: JsonValue): System::Int
  let r = printValue(h, v)
  ret match(r.v)
    (n: System::Int) => 0
    (e: IOError)     => 70

fun closeOk(h: IO): System::Int
  ret match(h.close())
    (e: IOError)      => 60
    (n: System::None) => 0

fun afterPrint(h: IO, code: System::Int): System::Int
  ret code = 0 ? closeOk(h) : code

fun main(): System::Int
  let v: JsonValue = JsonNum(42.0)
  ret match(create("{path}"))
    (h: IO)      => afterPrint(h, doPrint(h, v))
    (e: IOError) => 80
"""
            self.assertEqual(0, _run_with_json_module(src))
            with open(path) as f:
                content = f.read()
            self.assertEqual("42", content)

    def _run_round_trip(self, original: str) -> str:
        """Compile a parse-then-print program, run it on `original`,
        return what came out. Caller asserts."""
        with tempfile.TemporaryDirectory() as tmp:
            in_path = os.path.join(tmp, "in.json")
            out_path = os.path.join(tmp, "out.json")
            with open(in_path, "w") as f:
                f.write(original)
            src = _HARNESS_PRELUDE + f"""
fun doPrint(h: IO, v: JsonValue): System::Int
  let r = printValue(h, v)
  ret match(r.v)
    (n: System::Int) => 0
    (e: IOError)     => 70

fun closeOk(h: IO): System::Int
  ret match(h.close())
    (e: IOError)      => 60
    (n: System::None) => 0

fun afterPrint(h: IO, code: System::Int): System::Int
  ret code = 0 ? closeOk(h) : code

fun handleParsed(v: JsonValue): System::Int
  ret match(create("{out_path}"))
    (h: IO)      => afterPrint(h, doPrint(h, v))
    (e: IOError) => 80

fun main(): System::Int
  ret runOnPath("{in_path}", handleParsed)
"""
            self.assertEqual(0, _run_with_json_module(src),
                             f"round-trip program exited non-zero for input {original!r}")
            with open(out_path) as f:
                return f.read()

    def test_round_trip_scalar_number(self):
        self.assertEqual("42", self._run_round_trip("42"))

    def test_round_trip_array(self):
        self.assertEqual("[1, 2, 3]", self._run_round_trip("[1, 2, 3]"))

    def test_round_trip_object_with_nested_array(self):
        # Complex case: object with mixed types including a nested array.
        # Originally crashed with SIGSEGV during GC due to a packed-string
        # value in the captured peek-task's lookahead field. Fixed in
        # yafllib/object.c:gc_object_is_on_heap_fast (alignment mask
        # extended from 3 to PTR_TAG_MASK so PTR_TAG_STRING is filtered).
        import json as pyjson
        original = '{"name": "yafl", "values": [1, 2, 3], "ok": true}'
        printed = self._run_round_trip(original)
        self.assertEqual(pyjson.loads(original), pyjson.loads(printed))

    def test_parse_mixed_nested(self):
        # {"items": [{"v": 5}, {"v": 8}]} — sum the inner v fields.
        body = """  ret match(v)
    (o: JsonObj) => sumInner(o.pairs)
    () => 99

fun sumInner(l: JsonObjectList): System::Int
  ret match(l)
    (n: JObjNil)  => 0
    (c: JObjCons) => match(c.value)
      (a: JsonArr) => sumArr(a.elements)
      (other: JsonValue) => 0

fun sumArr(l: JsonArrayList): System::Int
  ret match(l)
    (n: JArrNil)  => 0
    (c: JArrCons) => match(c.head)
      (o: JsonObj)       => firstNum(o.pairs) + sumArr(c.tail)
      (other: JsonValue) => sumArr(c.tail)

fun firstNum(l: JsonObjectList): System::Int
  ret match(l)
    (n: JObjNil)  => 0
    (c: JObjCons) => match(c.value)
      (n: JsonNum)       => System::Int(n.numValue)
      (other: JsonValue) => 0"""
        self.assertEqual(13, self._run('{"items": [{"v": 5}, {"v": 8}]}', body))
