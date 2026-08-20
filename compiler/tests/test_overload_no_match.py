"""A call whose callee has overloads but NONE that accept the argument types
must say so — not report an ambiguity.

`Ambiguous reference 'f' — qualify it. Candidates: ...` tells the author to
disambiguate. When the real situation is that no overload accepts what they
passed, qualifying is impossible and the message sends them the wrong way. The
call site knows the argument types, so it can say which arguments failed and
what the candidates actually take.

The sibling case — two or more candidates that DO accept the arguments — is a
real ambiguity and must keep the qualification message; that is covered by
test_project_build.test_ambiguous_reference_lists_candidates and re-asserted
here so the two paths stay distinct.
"""
from __future__ import annotations

import contextlib
import io
import unittest

import compiler as c


def _diagnostics(src: str) -> tuple[object, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        out = c.compile([c.Input(src, "t.yafl")], use_stdlib=True)
    return out, buf.getvalue()


class TestOverloadNoMatch(unittest.TestCase):

    def test_no_overload_accepts_the_argument_type(self):
        # `singleOrNone` is declared for Set<T> and Bag<T> only — stdlib has no
        # List overload. Passing a List must be reported as "nothing accepts
        # this", naming the argument type and the real signatures.
        src = """namespace Main
import System
fun pick(l: List<System::String>): System::String|System::None
  ret singleOrNone(l)
fun main(): System::Int
  ret 0
"""
        out, diag = _diagnostics(src)
        self.assertFalse(out, "a call with no matching overload must be rejected")
        self.assertIn("singleOrNone", diag)
        self.assertNotIn("Ambiguous reference", diag)
        # Names the arguments that failed, and what the candidates do take.
        self.assertIn("accepts arguments", diag)
        self.assertIn("List", diag)
        self.assertIn("Set", diag)

    def test_a_real_ambiguity_still_asks_for_qualification(self):
        # Two candidates that BOTH accept `()`: genuinely ambiguous, and the
        # only fix is to qualify. This message must not regress.
        src = """namespace A
fun thing(): System::Int
  ret 1
namespace B
fun thing(): System::Int
  ret 2
namespace Main
import System
import A
import B
fun main(): System::Int
  ret thing()
"""
        out, diag = _diagnostics(src)
        self.assertFalse(out, "ambiguous reference should be rejected")
        self.assertIn("Ambiguous reference 'thing'", diag)
        self.assertIn("A::thing", diag)
        self.assertIn("B::thing", diag)

    def test_a_resolvable_overload_is_unaffected(self):
        # The same name WITH a matching overload compiles: narrowing by
        # argument type still works, and neither diagnostic fires.
        src = """namespace Main
import System
fun pick(s: Set<System::String >): System::String|System::None
  ret singleOrNone(s)
fun main(): System::Int
  ret 0
"""
        out, diag = _diagnostics(src)
        self.assertTrue(out, f"a matching overload must resolve; got:\n{diag}")


if __name__ == "__main__":
    unittest.main()
