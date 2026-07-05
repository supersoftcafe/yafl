"""JSON of a String: the IO pipeline over a one-shot in-memory source.

`System::once` (a `Never`-typed single-value stream — it cannot fail, and the
type says so) + `System::collect` (a StringBuilder drain) make
`Json::prettyString` pure composition: once → tokenize → prettyEmit → collect.
The result carries the honest union `String | JsonParseError | Never`;
exhaustiveness counts inhabited members only, so consumers owe no arm for the
uninhabited member — two arms are a complete match.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


_MAIN = """namespace Main
import System
import System::Json

fun show(v: System::String | JsonParseError | System::Never): System::Int
  ret match(v)
    (out: System::String)  => System::print(out) |> (n) => 0
    (p: JsonParseError)    => 2

fun main(): System::Int
  ret show(prettyString(%s))
"""


class TestJsonOfString(TestCase):
    def test_pretty_string_exact_output(self):
        rc, out = compile_and_run_stdlib_capture(
            _MAIN % '"{\\"a\\":[1,2],\\"b\\":null}"')
        self.assertEqual(0, rc)
        self.assertEqual(
            '{\n  "a": [\n    1,\n    2\n  ],\n  "b": null\n}', out)

    def test_pretty_string_at_o3(self):
        # The fully-fused, synchronously-driven pipeline (no IO anywhere):
        # pins the -O3 path the stub-launch bug broke (async_lower's
        # _STUB_THRESHOLD_OPS note) — the -O0 tests above cannot see it.
        rc, out = compile_and_run_stdlib_capture(
            _MAIN % '"{\\"a\\":[1,2],\\"b\\":null}"', optimization_level=3)
        self.assertEqual(0, rc)
        self.assertEqual(
            '{\n  "a": [\n    1,\n    2\n  ],\n  "b": null\n}', out)

    def test_pretty_string_parse_error(self):
        rc, _out = compile_and_run_stdlib_capture(_MAIN % '"{\\"a\\": nope}"')
        self.assertEqual(2, rc)

    def test_pretty_string_escapes_flow_through(self):
        # Escapes are preserved verbatim by the token stream (TokString carries
        # the raw body); the StringBuilder-backed collect must reassemble them.
        rc, out = compile_and_run_stdlib_capture(
            _MAIN % '"{\\"s\\":\\"x\\\\ny\\"}"')
        self.assertEqual(0, rc)
        self.assertEqual('{\n  "s": "x\\ny"\n}', out)

    def test_value_parser_string_body_builder(self):
        # `parse` decodes string bodies through the StringBuilder-backed
        # _strBody (bulk runs + escape expansion); verify decode + error paths.
        rc, out = compile_and_run_stdlib_capture(
            "namespace Main\n"
            "import System\n"
            "import System::Json\n"
            "fun main(): System::Int\n"
            "  ret match(parse(\"\\\"a\\\\nb\\\"\"))\n"
            "    (v: JsonValue)      => match(v)\n"
            "      (s: JsonStr)      => System::length(s.strValue) == 3 ? 0 : 3\n"
            "      (other)           => 4\n"
            "    (p: JsonParseError) => 2\n")
        self.assertEqual(0, rc)

    def test_value_parser_unterminated_string(self):
        rc, _out = compile_and_run_stdlib_capture(
            "namespace Main\n"
            "import System\n"
            "import System::Json\n"
            "fun main(): System::Int\n"
            "  ret match(parse(\"\\\"abc\"))\n"
            "    (p: JsonParseError) => 2\n"
            "    (other)             => 4\n")
        self.assertEqual(2, rc)
