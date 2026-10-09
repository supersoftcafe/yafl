"""Streaming JSON tokenizer + serialiser (System::Json).

A byte stream is tokenised into a `JsonToken` stream — whitespace preserved,
strings/numbers carrying raw text — and serialised back to a String stream. With
whitespace kept, tokenise→serialise is the identity on lexically-valid input, so
a round-trip is the cleanest test. The error channel is `Never | JsonParseError`
(collapsing to `JsonParseError`): the in-memory source can't fail, only the
lexer can — and only on LEXICAL errors (unterminated string, bad number,
unexpected byte); structural validity is the DOM builder's concern, not the
tokenizer's, so `"{"` is a valid lone token.

Exercises the error-growing-union machinery end to end (the lexer's output error
is `E | JsonParseError` over the source's `E`).
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


def _run(body: str) -> int:
    src = (
        "namespace Test\n"
        "import System\n"
        "import System::Json\n"
        "fun rt(input: System::String): System::Int\n"
        "  ret match(System::Json::tokenStringRoundTrip(input))\n"
        "    (s: System::String)               => s == input ? 0 : 1\n"
        "    (e: System::Json::JsonParseError) => 2\n"
        "fun err(input: System::String): System::Int\n"
        "  ret match(System::Json::tokenStringRoundTrip(input))\n"
        "    (s: System::String)               => 0\n"
        "    (e: System::Json::JsonParseError) => 1\n"
        f"fun main(): System::Int\n  {body}\n")
    rc, _ = compile_and_run_stdlib_capture(src, timeout=120)
    return rc

    # (rc is the program's exit code = main's return)


class TestJsonStream(TestCase):
    def test_roundtrip_preserves_input(self):
        # Whitespace, escapes, numbers and structure reproduce verbatim.
        rc = _run('ret rt("[]") + rt("  {  } ") + rt("[1, 2, 3.5]")\n'
                  '    + rt("{ \\"a\\": 12, \\"b\\": [true, null], \\"c\\": \\"x\\\\ny\\" }")')
        self.assertEqual(0, rc)

    def test_lexical_errors_detected(self):
        # Unterminated string, unexpected byte, malformed number → JsonParseError.
        rc = _run('ret err("\\"abc") + err("@") * 10 + err("1.2.3") * 100')
        self.assertEqual(111, rc)

    def test_truncated_input_rejected(self):
        # EOF inside an open container is a parse error from the PRETTY
        # PRINTER (the tokenizer stays lexical-only by design, so a lone
        # "{" is a valid token stream — but not a complete document).
        src = (
            "namespace Test\n"
            "import System\n"
            "import System::Json\n"
            "fun chk(input: System::String): System::Int\n"
            "  ret match(System::Json::prettyString(input))\n"
            "    (s: System::String)               => 0\n"
            "    (e: System::Json::JsonParseError) => 1\n"
            "fun main(): System::Int\n"
            '  ret chk("{\\"a\\": [1,2") + chk("[") * 10 + chk("[]") * 100\n')
        rc, _ = compile_and_run_stdlib_capture(src, timeout=120)
        self.assertEqual(11, rc)

    def test_pretty_printer(self):
        # Token-level reformat: drop source whitespace, insert two-space indent;
        # empty {}/[] stay inline. `prettyString` = tokenise -> reformat -> fold.
        src = (
            "namespace Test\n"
            "import System\n"
            "import System::Json\n"
            'let [const] EXPECTED: System::String = '
            '"{\\n  \\"a\\": 1,\\n  \\"b\\": [\\n    true,\\n    null\\n  ],'
            '\\n  \\"c\\": {},\\n  \\"d\\": []\\n}"\n'
            "fun main(): System::Int\n"
            '  ret match(System::Json::prettyString('
            '"{\\"a\\":1,\\"b\\":[true,null],\\"c\\":{},\\"d\\":[]}"))\n'
            "    (s: System::String)               => s == EXPECTED ? 0 : 1\n"
            "    (e: System::Json::JsonParseError) => 2\n")
        rc, _ = compile_and_run_stdlib_capture(src, timeout=120)
        self.assertEqual(0, rc)
