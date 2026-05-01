"""End-to-end tests for the System::Json stdlib parser/printer."""
from __future__ import annotations

import os
import subprocess
import tempfile
from unittest import TestCase

import compiler as c
from tests.testutil import _CLANG_BUILD_FLAGS, _RUN_ENV


# Shared helper functions, one set of definitions reused across tests.
_HARNESS_PRELUDE = """namespace Main
import System
import System::IO
import System::Json

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
        [c.Input(test_source, "test.yafl")],
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
        # Whole numbers without fractional or exponent now parse as JsonInt,
        # not JsonNum — JsonNum is reserved for values that need Float precision.
        body = """  ret match(v)
    (n: JsonInt) => n.intValue
    (n: JsonNum) => System::Int(n.numValue)
    () => 99"""
        self.assertEqual(42, self._run("42", body))

    def test_parse_number_float(self):
        # A value with a fractional part is JsonNum (Float).
        body = """  ret match(v)
    (n: JsonNum) => System::Int(n.numValue)
    () => 99"""
        self.assertEqual(3, self._run("3.14", body))

    def test_parse_number_exponent(self):
        # Exponent notation is also JsonNum.
        body = """  ret match(v)
    (n: JsonNum) => System::Int(n.numValue)
    () => 99"""
        self.assertEqual(150, self._run("1.5e2", body))

    def test_parse_number_negative_int(self):
        # Reflect the negative through a small offset so the exit code stays in 0..255.
        body = """  ret match(v)
    (n: JsonInt) => 100 + n.intValue
    () => 99"""
        self.assertEqual(93, self._run("-7", body))   # 100 + -7 = 93

    def test_parse_number_with_leading_whitespace(self):
        body = """  ret match(v)
    (n: JsonInt) => n.intValue
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
    (a: JsonArr) => match(head<JsonValue>(a.elements))
      (n: None)      => 0
      (v: JsonValue) => 1
    () => 99"""
        self.assertEqual(0, self._run("[]", body))

    def test_parse_array_three_numbers(self):
        # [10, 20, 30] — sum the elements (each via the JsonInt extraction).
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
        # [[1], [2, 3]] — count elements at top level (2).
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
        # {"x": 7} — find "x" and return its number.
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
    (p: JsonPair) => p.key = "x" ? unwrapInt(p.value) : lookupX(tail<JsonPair>(l))"""
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


# Threshold inside System::Json — keep in sync with stdlib/json.yafl.
_CHUNK_SOFT_LEN = 14336


class TestJsonInteger(TestCase):
    """Round-trips and edge cases specific to JsonInt."""

    def _round_trip(self, original: str) -> str:
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

    def test_int_round_trip_small(self):
        self.assertEqual("42", self._round_trip("42"))

    def test_int_round_trip_zero(self):
        self.assertEqual("0", self._round_trip("0"))

    def test_int_round_trip_large(self):
        # Larger than int32 — exercises bigint precision through the parser.
        self.assertEqual("123456789012345", self._round_trip("123456789012345"))

    def test_float_round_trip(self):
        # A value with a decimal stays Float — round-trip through printValue.
        # Use a power-of-two-friendly value (0.5) that's exactly representable
        # in IEEE 754 so the printer's text form matches the input exactly.
        self.assertEqual("0.5", self._round_trip("0.5"))


class TestJsonBigStr(TestCase):
    """Strings exceeding the 14 KiB chunk threshold parse to JsonBigStr."""

    def _classify_string(self, json_text: str, body: str) -> int:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "in.json")
            with open(path, "w") as f:
                f.write(json_text)
            src = _HARNESS_PRELUDE + f"""
fun classify(v: JsonValue): System::Int
{body}

fun main(): System::Int
  ret runOnPath("{path}", classify)
"""
            return _run_with_json_module(src)

    def _make_body_string(self, n: int, ch: str = "x") -> str:
        return ch * n

    def test_short_string_stays_jsonstr(self):
        # A 100-byte string is well under the threshold → JsonStr.
        body = """  ret match(v)
    (s: JsonStr)    => 1
    (b: JsonBigStr) => 2
    () => 0"""
        text = '"' + self._make_body_string(100) + '"'
        self.assertEqual(1, self._classify_string(text, body))

    def test_just_over_threshold_becomes_jsonbigstr(self):
        # 15000 bytes > _CHUNK_SOFT_LEN (14336) → JsonBigStr.
        body = """  ret match(v)
    (s: JsonStr)    => 1
    (b: JsonBigStr) => 2
    () => 0"""
        text = '"' + self._make_body_string(15000) + '"'
        self.assertEqual(2, self._classify_string(text, body))

    def test_jsonbigstr_chunk_count(self):
        # 30000 bytes splits into 3 chunks: ~14336 + ~14336 + remainder.
        # Verify chunks > 1 (exact count depends on flush timing).
        body = """  ret match(v)
    (b: JsonBigStr) => System::length<String>(b.chunks)
    () => 99"""
        text = '"' + self._make_body_string(30000) + '"'
        n_chunks = self._classify_string(text, body)
        self.assertGreater(n_chunks, 1, "expected multiple chunks for a 30KB string")

    def test_jsonbigstr_total_length_preserved(self):
        # Sum of chunk lengths matches the input string body.  The exit code
        # wraps modulo 256, so we ask the program to mod the sum itself and
        # then assert against the expected wrap.
        body = """  ret match(v)
    (b: JsonBigStr) => System::abs(sumChunks(b.chunks)) % 256
    () => 99

fun sumChunks(l: List<String>): System::Int
  let h = head<String>(l)
  ret match(h)
    (n: None)   => 0
    (s: String) => System::length(s) + sumChunks(tail<String>(l))"""
        text = '"' + self._make_body_string(30000) + '"'
        self.assertEqual(30000 % 256, self._classify_string(text, body))

    def test_jsonbigstr_utf8_chunks_at_codepoint_boundaries(self):
        # Drop 3-byte UTF-8 codepoints around the chunk boundary. If chunks
        # split correctly, no chunk's first byte will be a continuation byte
        # (0x80–0xBF) — and that condition implies the *previous* chunk
        # ended at a codepoint boundary, since the input itself is well-formed.
        body = """  ret match(v)
    (b: JsonBigStr) => allStartAtBoundary(b.chunks)
    () => 99

fun startsAtBoundary(s: System::String): System::Int
  let bv: System::Int = System::length(s) = 0 ? 0 : System::byteAt(s, 0)
  let lowHi: System::Int = bv > 191 ? 1 : 0
  ret bv < 128 ? 1 : lowHi

fun allStartAtBoundary(l: List<System::String>): System::Int
  let h = head<System::String>(l)
  ret match(h)
    (n: None)   => 1
    (s: System::String) => startsAtBoundary(s) > 0
                            ? allStartAtBoundary(tail<System::String>(l))
                            : 0"""
        # ASCII padding + 3-byte € characters straddling the chunk boundary.
        ascii_padding = "x" * 14000
        text = '"' + ascii_padding + ("€" * 200) + '"'   # ≈ 14000 + 600 = 14600 bytes
        self.assertEqual(1, self._classify_string(text, body))

    def test_jsonbigstr_round_trip(self):
        # Parse → print → re-parse → assert structurally identical content.
        with tempfile.TemporaryDirectory() as tmp:
            in_path = os.path.join(tmp, "in.json")
            out_path = os.path.join(tmp, "out.json")
            body_str = "x" * 30000
            original = f'"{body_str}"'
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
            self.assertEqual(0, _run_with_json_module(src, timeout=30))
            with open(out_path) as f:
                printed = f.read()
            self.assertEqual(original, printed)
