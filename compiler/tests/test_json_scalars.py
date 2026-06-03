"""Consolidated JSON scalar test.

A single program parses every scalar case (true/false/null/42/3.14/1.5e2/
-7/whitespace/"hi"/"a\\nb"/"") with `System::Json::parse` and prints a
labelled classification per case.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from tests.testutil import TimedTestCase as TestCase

import compiler as c
from tests.testutil import _CLANG_BUILD_FLAGS, _RUN_ENV


# Each (label, json_text, expected) entry contributes one labelled line
# of program output. `expected` is what the program prints after parsing.
_CASES = [
    ("true",        "true",        "true"),
    ("false",       "false",       "false"),
    ("null",        "null",        "null"),
    ("int_42",      "42",          "int:42"),
    ("float_3_14",  "3.14",        "num:3"),
    ("exp_1_5e2",   "1.5e2",       "num:150"),
    ("int_neg_7",   "-7",          "int:-7"),
    ("int_ws_7",    "  \n\t7  ",   "int:7"),
    ("str_hi",      '"hi"',        "str_len:2"),
    ("str_esc",     '"a\\nb"',     "str_len:3"),
    ("str_empty",   '""',          "str_len:0"),
]


_PRELUDE = """namespace Main
import System
import System::Json

fun classify(v: JsonValue): System::String
  ret match(v)
    (t: JsonTrue)  => "true"
    (f: JsonFalse) => "false"
    (n: JsonNull)  => "null"
    (i: JsonInt)   => "int:" + System::String(i.intValue)
    (n: JsonNum)   => "num:" + System::String(System::truncateToInt(n.numValue))
    (s: JsonStr)   => "str_len:" + System::String(System::length(s.strValue))
    ()             => "??"

fun classifyResult(s: System::String): System::String
  ret match(parse(s))
    (val: JsonValue)    => classify(val)
    (e: JsonParseError) => "parse_error"

fun emit(label: System::String, result: System::String): System::None
  System::print(label + "=" + result + "\\n")
  ret None
"""


_ESCAPES = {"\\": "\\\\", '"': '\\"', "\n": "\\n", "\t": "\\t", "\r": "\\r"}


def _yafl_str(text: str) -> str:
    """Embed `text` as a YAFL string literal."""
    return '"' + "".join(_ESCAPES.get(ch, ch) for ch in text) + '"'


def _build_source() -> str:
    """Compose the full yafl main() that runs all cases."""
    body_lines = "\n".join(
        f'  emit("{label}", classifyResult({_yafl_str(json_text)}))'
        for label, json_text, _ in _CASES
    )
    return f"""{_PRELUDE}

fun main(): System::Int
{body_lines}
  ret 0
"""


def _run_yafl(source: str, timeout: int = 15) -> tuple[int, str]:
    c_code = c.compile([c.Input(source, "test.yafl")], use_stdlib=True, just_testing=False)
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
        return run.returncode, run.stdout.decode("utf-8", errors="replace")
    finally:
        try:
            os.unlink(binary)
        except OSError:
            pass


class TestAllJsonScalars(TestCase):
    def test_all_json_scalar_cases(self):
        rc, stdout = _run_yafl(_build_source())
        self.assertEqual(0, rc, f"program exited with {rc}; stdout:\n{stdout}")
        expected = [f"{label}={expected}" for label, _, expected in _CASES]
        self.assertEqual(expected, stdout.splitlines())
