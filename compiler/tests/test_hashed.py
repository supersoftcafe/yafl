"""`[hashed]`/`[refeq]` on FUNCTIONS — representation-aware caching.

Every BOXED enum carries a hidden `$hash: Int32` slot by default (no
annotation, no boxing force — the representation stays the compiler's
decision). A `[hashed]` function `(v: T): Int32` is wrapped: slot hit returns
it; miss computes, remaps 0 to 1, stores. A `[refeq]` function
`(l: T, r: T): Bool` gets the identity shortcut. On a VALUE-repr enum the
internals resolve to constants at codegen — no cache, no identity — and the
functions still compute correctly.

Runtime behaviour is checked by compiler/yafl_tests/hashed.yafl.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_c_result


def _diagnostics(content: str) -> str:
    r = compile_c_result(content, "file.yafl")
    return r.stdout if not r.c else ""


# The compute bodies print, so the trace shows which calls ran them. One
# program, three properties:
#   tree  — the nested leaves cache on the first outer call, so hashing the
#           same object again computes nothing: CCC then nothing;
#   boxes — equal content in two objects caches in two slots: CC;
#   refeq — the same object skips the compare, others run it: EE.


class TestHashedValidation(TestCase):
    def test_hashed_fun_must_return_int32(self):
        src = """\
import System

enum H
  enum H1(v: System::Int)

fun [hashed] hHash(h: H): System::Int
  ret 1

fun main(): System::Int
  ret 0
"""
        diag = _diagnostics(src)
        self.assertIn("Int32", diag, diag)


class TestRefEq(TestCase):
    """`[refeq]` — the opt-in reference-equality shortcut (plan §3c). On a
    function `(l: T, r: T): Bool` over a [hashed] enum, the body is wrapped:
    same object returns true WITHOUT running the compare. Opt-in is the whole
    NaN answer: a non-reflexive equality simply does not opt in."""

    def test_refeq_must_return_bool(self):
        src = """\
import System

enum H2
  enum H21(v: System::Int)

fun [refeq] hEq(l: H2, r: H2): System::Int
  ret 1

fun main(): System::Int
  ret 0
"""
        diag = _diagnostics(src)
        self.assertIn("Bool", diag, diag)
