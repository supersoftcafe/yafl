"""Runtime tests for the string additions: indexOf, contains, startsWith,
endsWith, split, join, trim / trimStart / trimEnd.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


_SRC = """\
namespace System
import System

fun emit(label: System::String, value: System::Int): System::None
  System::print(label + "=" + System::String(value) + "\\n")
  ret None

fun emitBool(label: System::String, value: System::Bool): System::None
  ret emit(label, value ? 1 : 0)

fun emitStr(label: System::String, value: System::String): System::None
  System::print(label + "=" + value + "\\n")
  ret None

fun count(l: List<String>): Int
  ret fold<String,Int>(l, 0, (a: Int, x: String) => a + 1)

fun firstOr(l: List<String>, dflt: String): String
  ret match(head<String>(l))
    (x: String) => x
    (e: None)   => dflt

fun main(): Int
  let s = "hello, world"

  # ─── indexOf ───────────────────────────────────────────────────────────
  emit("indexOf_hit",   indexOf(s, "world", 0))
  emit("indexOf_miss",  indexOf(s, "xyz", 0))
  emit("indexOf_from",  indexOf("ababab", "ab", 1))
  emit("indexOf_empty", indexOf(s, "", 3))
  emit("indexOf_start", indexOf(s, "hello", 0))

  # ─── contains / startsWith / endsWith ──────────────────────────────────
  emitBool("contains_yes",   contains(s, "lo, w"))
  emitBool("contains_no",    contains(s, "z"))
  emitBool("contains_empty", contains(s, ""))
  emitBool("starts_yes",     startsWith(s, "hello"))
  emitBool("starts_no",      startsWith(s, "world"))
  emitBool("starts_long",    startsWith("hi", "hippo"))
  emitBool("ends_yes",       endsWith(s, "world"))
  emitBool("ends_no",        endsWith(s, "hello"))

  # ─── split ─────────────────────────────────────────────────────────────
  emit("split_count",    count(split("a,b,c", ",")))
  emit("split_empties",  count(split("a,,b", ",")))
  emit("split_trailing", count(split("a,", ",")))
  emit("split_nosep",    count(split("abc", ",")))
  emit("split_emptysep", count(split("abc", "")))
  emitStr("split_first", firstOr(split("x-y-z", "-"), "?"))
  emitStr("split_multichar", firstOr(split("a::b", "::"), "?"))

  # ─── join (and split/join round-trip) ──────────────────────────────────
  emitStr("join_basic",  join(append<String>(append<String>(append<String>(List<String>(), "a"), "b"), "c"), "-"))
  emitStr("join_single", join(append<String>(List<String>(), "solo"), "-"))
  emitStr("join_empty",  join(List<String>(), "-"))
  emitStr("roundtrip",   join(split("a,b,c", ","), ","))

  # ─── trim family ───────────────────────────────────────────────────────
  emitStr("trim",          trim("  hi there  "))
  emitStr("trimStart",     trimStart("  hi  "))
  emitStr("trimEnd",       trimEnd("  hi  "))
  emitStr("trim_tabs",     trim("\\t\\n x \\r\\n"))
  emitStr("trim_none",     trim("abc"))
  emitStr("trim_allspace", trim("   "))

  ret 0
"""


_EXPECTED_LINES = [
    "indexOf_hit=7",
    "indexOf_miss=-1",
    "indexOf_from=2",
    "indexOf_empty=3",
    "indexOf_start=0",
    "contains_yes=1",
    "contains_no=0",
    "contains_empty=1",
    "starts_yes=1",
    "starts_no=0",
    "starts_long=0",
    "ends_yes=1",
    "ends_no=0",
    "split_count=3",
    "split_empties=3",
    "split_trailing=2",
    "split_nosep=1",
    "split_emptysep=1",
    "split_first=x",
    "split_multichar=a",
    "join_basic=a-b-c",
    "join_single=solo",
    "join_empty=",
    "roundtrip=a,b,c",
    "trim=hi there",
    "trimStart=hi  ",
    "trimEnd=  hi",
    "trim_tabs=x",
    "trim_none=abc",
    "trim_allspace=",
]


class TestStringSearch(TestCase):
    def test_all_string_search(self):
        rc, stdout = compile_and_run_stdlib_capture(_SRC, timeout=15)
        self.assertEqual(0, rc, f"program exited with {rc}; stdout:\n{stdout}")
        self.assertEqual(_EXPECTED_LINES, stdout.splitlines())
