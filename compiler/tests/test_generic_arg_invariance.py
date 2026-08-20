"""Generic type arguments are INVARIANT, and the checker must enforce it.

The gap this pins: ClassSpec assignability compared the mangled class NAME
alone, so `List<B2>` passed where `List<A2>` was declared — through plain
calls and enum constructors alike — and the first symptom was a codegen
crash pointing at union representation, nowhere near the fault (the shifted
PsEnum arguments, found 2026-08-04).
"""
from __future__ import annotations

import compiler as c
from tests.testutil import TimedTestCase as TestCase


def _diagnostics(content: str) -> str:
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        out = c.compile([c.Input(content, "file.yafl")], use_stdlib=True,
                        just_testing=False, optimization_level=0)
    return buf.getvalue() if not out else ""


_PRELUDE = """\
import System

class [final] A2(av: System::Int)
class [final] B2(bv: System::Int)

enum E2
  enum L2(xs: System::List<A2>)

"""


class TestGenericArgInvariance(TestCase):
    def test_wrong_type_argument_via_function_call(self):
        src = _PRELUDE + """\
fun takesA(xs: System::List<A2>): System::Int
  ret 0

fun main(): System::Int
  ret takesA(System::prepend(B2(1), System::List<B2>()))
"""
        diag = _diagnostics(src)
        self.assertNotEqual("", diag, "COMPILED CLEAN — the invariance gap is back")

    def test_wrong_type_argument_via_enum_constructor(self):
        src = _PRELUDE + """\
fun main(): System::Int
  let e = L2(System::prepend(B2(1), System::List<B2>()))
  ret 0
"""
        diag = _diagnostics(src)
        self.assertNotEqual("", diag, "COMPILED CLEAN — the invariance gap is back")

    def test_right_type_argument_still_accepted(self):
        src = _PRELUDE + """\
fun main(): System::Int
  let e = L2(System::prepend(A2(1), System::List<A2>()))
  ret 0
"""
        self.assertEqual("", _diagnostics(src))
