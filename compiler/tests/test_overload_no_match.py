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

import unittest

from tests.testutil import compile_c_result


def _diagnostics(src: str) -> tuple[object, str]:
    r = compile_c_result(src, "t.yafl")
    return r.c, r.stdout


class TestOverloadNoMatch(unittest.TestCase):

    def test_no_overload_accepts_the_argument_type(self):
        # `singleOrNone` is declared for Set<T> and Bag<T> only — stdlib has no
        # List overload. Passing a List must be reported as "nothing accepts
        # this", naming the argument type and the real signatures.
        src = """namespace Main
import System
import System::Containers
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
import System::Containers
fun pick(s: Set<System::String >): System::String|System::None
  ret singleOrNone(s)
fun main(): System::Int
  ret 0
"""
        out, diag = _diagnostics(src)
        self.assertTrue(out, f"a matching overload must resolve; got:\n{diag}")

    # ── member calls: the load narrows by the call's shape ───────────────────

    def test_member_call_no_overload_accepts(self):
        # `K().f(true)`: the member lookup finds two `f`, neither takes a Bool.
        # That is "nothing accepts this", never an ambiguity.
        src = """namespace Main
import System
class K()
  fun f(v: Int): String
    ret "i"
  fun f(v: String): String
    ret "s"
fun main(): Int
  System::println(K().f(true))
  ret 0
"""
        out, diag = _diagnostics(src)
        self.assertFalse(out)
        self.assertIn("accepts arguments", diag)
        self.assertIn("Bool", diag)
        self.assertNotIn("Ambiguous", diag)

    def test_member_overloads_resolve_by_arguments(self):
        src = """namespace Main
import System
class K()
  fun f(v: Int): Int
    ret 1
  fun f(v: String): Int
    ret 2
fun main(): Int
  ret K().f("x")
"""
        out, diag = _diagnostics(src)
        self.assertTrue(out, f"a matching member overload must resolve; got:\n{diag}")

    def test_overloaded_let_bindings_resolve_by_call_shape(self):
        # Named bindings may be overloaded; the call's shape picks one.
        src = """namespace Main
import System
fun a(v: String): None
  ret None
fun b(v: Int): None
  ret None
let myPrint: (:String): None = a
let myPrint: (:Int): None = b
fun main(): Int
  myPrint("fred")
  ret 0
"""
        out, diag = _diagnostics(src)
        self.assertTrue(out, f"overloaded bindings must resolve; got:\n{diag}")

    def test_overloaded_let_bindings_no_match(self):
        src = """namespace Main
import System
fun a(v: String): None
  ret None
fun b(v: Int): None
  ret None
let myPrint: (:String): None = a
let myPrint: (:Int): None = b
fun main(): Int
  myPrint(true)
  ret 0
"""
        out, diag = _diagnostics(src)
        self.assertFalse(out)
        self.assertIn("accepts arguments", diag)
        self.assertNotIn("Ambiguous", diag)


if __name__ == "__main__":
    unittest.main()
