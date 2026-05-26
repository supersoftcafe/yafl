"""Consolidated format / Show test.

Covers `System::format<...>` at every arity (1–4) and the `Show<T>`
trait instances for Int/String/Bool/Float.

Why four sub-programs instead of one: the compiler's overload resolution
trips when calls to `format<...>` at different arities appear in the
same program ('could not cast None to CallableSpec' at codegen). Each
arity therefore gets its own compile. Show tests piggyback on the arity-1
program since they don't touch `format` (they go through `show()`
directly), so they're free.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


_PRELUDE = """\
import System

fun emit(label: System::String, value: System::Int): System::None
  print(label + "=" + String(value) + "\\n")
  ret None

fun _showLen<T>(v: T): System::Int where Show<T>
  ret length(show(v))
fun _showByte<T>(v: T, at: System::Int): System::Int where Show<T>
  ret byteAt(show(v), at)
"""


_ARITY1_SRC = _PRELUDE + """\

fun main(): System::Int
  # ─── Show<Int> ──────────────────────────────────────────────────────────
  emit("show_Int_positive_len",  _showLen<Int>(12345))
  emit("show_Int_zero_len",      _showLen<Int>(0))
  emit("show_Int_negative_byte0",_showByte<Int>(-42, 0))
  emit("show_Int_first_digit",   _showByte<Int>(12345, 0))
  # ─── Show<String> (identity) ───────────────────────────────────────────
  emit("show_String_len",        _showLen<String>("hello"))
  emit("show_String_byte0",      _showByte<String>("hello", 0))
  emit("show_String_empty_len",  _showLen<String>(""))
  # ─── Show<Bool> ────────────────────────────────────────────────────────
  emit("show_Bool_true_len",     _showLen<Bool>(1 < 2))
  emit("show_Bool_false_len",    _showLen<Bool>(1 > 2))
  emit("show_Bool_true_byte0",   _showByte<Bool>(1 < 2, 0))
  emit("show_Bool_false_byte0",  _showByte<Bool>(1 > 2, 0))
  # ─── Show<Float> — pin only invariants that don't depend on %g ─────────
  emit("show_Float_positive_nonempty", _showLen<Float>(3.14) > 0 ? 1 : 0)
  emit("show_Float_first_digit",       _showByte<Float>(3.14, 0))
  # ─── format arity 1 ────────────────────────────────────────────────────
  emit("fmt1_basic_len",        length(format<String>("hello {1}", "world")))
  emit("fmt1_byte_at_slot",     byteAt(format<String>("a{1}b", "X"), 1))
  emit("fmt1_int_arg_len",      length(format<Int>("value={1}", 42)))
  emit("fmt1_no_slot_len",      length(format<String>("no slots here", "ignored")))
  emit("fmt1_literal_brace",    byteAt(format<String>("{not a slot}", "x"), 0))
  emit("fmt1_out_of_range_idx", byteAt(format<String>("{2}", "x"), 0))
  ret 0
"""

_ARITY2_SRC = _PRELUDE + """\

fun main(): System::Int
  emit("fmt2_in_order_len",     length(format<String, Int>("{1}={2}", "x", 42)))
  emit("fmt2_reordered_byte0",  byteAt(format<String, String>("{2}{1}", "A", "B"), 0))
  emit("fmt2_repeated_idx_len", length(format<String, Int>("{1}-{1}-{2}", "x", 7)))
  ret 0
"""

_ARITY3_SRC = _PRELUDE + """\

fun main(): System::Int
  emit("fmt3_basic_len", length(format<Int, Int, Int>("{1}+{2}={3}", 1, 2, 3)))
  ret 0
"""

_ARITY4_SRC = _PRELUDE + """\

fun main(): System::Int
  let s: System::String = format<String, Bool, Int, Float>("{1} {2} {3} {4}", "x", 1 < 2, 42, 3.0)
  emit("fmt4_basic_len",   length(format<Int, Int, Int, Int>("{1}{2}{3}{4}", 1, 2, 3, 4)))
  emit("fmt4_mixed_byte0", byteAt(s, 0))
  emit("fmt4_mixed_byte2", byteAt(s, 2))
  ret 0
"""


_EXPECTED_ARITY1 = [
    # Show<Int>
    "show_Int_positive_len=5",
    "show_Int_zero_len=1",
    f"show_Int_negative_byte0={ord('-')}",
    f"show_Int_first_digit={ord('1')}",
    # Show<String>
    "show_String_len=5",
    f"show_String_byte0={ord('h')}",
    "show_String_empty_len=0",
    # Show<Bool>
    "show_Bool_true_len=4",
    "show_Bool_false_len=5",
    f"show_Bool_true_byte0={ord('t')}",
    f"show_Bool_false_byte0={ord('f')}",
    # Show<Float>
    "show_Float_positive_nonempty=1",
    f"show_Float_first_digit={ord('3')}",
    # format arity 1
    "fmt1_basic_len=11",
    f"fmt1_byte_at_slot={ord('X')}",
    "fmt1_int_arg_len=8",
    "fmt1_no_slot_len=13",
    f"fmt1_literal_brace={ord('{')}",
    f"fmt1_out_of_range_idx={ord('?')}",
]

_EXPECTED_ARITY2 = [
    "fmt2_in_order_len=4",
    f"fmt2_reordered_byte0={ord('B')}",
    "fmt2_repeated_idx_len=5",
]

_EXPECTED_ARITY3 = [
    "fmt3_basic_len=5",
]

_EXPECTED_ARITY4 = [
    "fmt4_basic_len=4",
    f"fmt4_mixed_byte0={ord('x')}",
    f"fmt4_mixed_byte2={ord('t')}",
]


class TestFormatAndShow(TestCase):
    """Each test method compiles one program; the compiler can't yet
    handle multiple format arities in a single program."""

    def _check(self, src: str, expected: list[str]) -> None:
        rc, stdout = compile_and_run_stdlib_capture(src, timeout=15)
        self.assertEqual(0, rc, f"program exited with {rc}; stdout was:\n{stdout}")
        self.assertEqual(expected, stdout.splitlines())

    def test_show_traits_and_format_arity1(self):
        self._check(_ARITY1_SRC, _EXPECTED_ARITY1)

    def test_format_arity2(self):
        self._check(_ARITY2_SRC, _EXPECTED_ARITY2)

    def test_format_arity3(self):
        self._check(_ARITY3_SRC, _EXPECTED_ARITY3)

    def test_format_arity4(self):
        self._check(_ARITY4_SRC, _EXPECTED_ARITY4)
