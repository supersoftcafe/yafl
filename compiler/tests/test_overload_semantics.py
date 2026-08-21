"""The overload / dispatch semantics matrix.

Pins the ruled semantics (2026-07-04):

  - Multiple values may share a name, distinguished only by type; AMBIGUITY
    AT THE REFERRER is the error, never the coexistence itself.
  - Selection is EXCLUSIVELY by expected type: there is no call node, only a
    LOAD (disambiguated by its expected shape — for a call site, the callable
    shape assembled from arguments AND required result) followed by a call of
    the loaded value. `fun` and `let` are indistinguishable targets.
  - A subclass function overrides every parent function whose definition is
    trivially assignable to it.
  - Optimisation must be observationally invisible to dispatch: -O0 (real
    vtables) and -O3 (devirtualised, vtable-trimmed, fused) agree.

Cases marked RULING-NEEDED probe corners the rules do not yet decide; their
assertions pin CURRENT behaviour and carry the open question, so a future
ruling flips the test knowingly rather than silently.
"""
from __future__ import annotations

import contextlib
import io

import compiler as c
from tests.testutil import BatchedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


def _errors_of(src: str) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = c.compile([c.Input(src, "test.yafl")], use_stdlib=True,
                         just_testing=True)
    return "" if code else buf.getvalue()


class TestSameNameValues(TestCase):
    def test_lets_share_a_name_recipient_type_selects(self):
        # Two globals named `v`; each use site's expected type picks its own.
        rc, out = compile_and_run_stdlib_capture(
            "namespace Main\nimport System\n"
            "let v: System::Int = 41\n"
            "let v: System::String = \"hi\"\n"
            "fun wantStr(s: System::String): System::Int\n"
            "  ret System::length(s)\n"
            "fun wantInt(n: System::Int): System::Int\n"
            "  ret n + 1\n"
            "fun main(): System::Int\n"
            "  ret wantInt(v) + wantStr(v)\n")
        self.assertEqual(44, rc)   # 42 + 2

    def test_ambiguous_referrer_is_the_error(self):
        # Same two globals; a use with no distinguishing expectation errors AT
        # THE USE — the definitions themselves are legal.
        errs = _errors_of(
            "namespace Main\nimport System\n"
            "let v: System::Int = 41\n"
            "let v: System::String = \"hi\"\n"
            "fun same(a: System::Int, b: System::Int): System::Int\n"
            "  ret a + b\n"
            "fun same(a: System::String, b: System::String): System::Int\n"
            "  ret System::length(a) + System::length(b)\n"
            "fun main(): System::Int\n"
            "  ret same(v, v)\n")
        self.assertNotEqual("", errs)
        self.assertNotIn("let v", errs)   # not blamed at the definitions


class TestExpectedShapeSelectsFunctions(TestCase):
    def test_argument_shape_reaches_the_load(self):
        rc, _ = compile_and_run_stdlib_capture(
            "namespace Main\nimport System\n"
            "fun f(n: System::Int): System::Int\n  ret 1\n"
            "fun f(s: System::String): System::Int\n  ret 2\n"
            "fun f(a: System::Int, b: System::Int): System::Int\n  ret 3\n"
            "fun main(): System::Int\n"
            "  ret f(0) * 100 + f(\"x\") * 10 + f(0, 0)\n")
        self.assertEqual(123, rc)

    def test_result_shape_alone_selects(self):
        # The cornerstone: two nullary functions differing ONLY in result
        # type; each recipient's expectation selects its function.
        rc, _ = compile_and_run_stdlib_capture(
            "namespace Main\nimport System\n"
            "fun g(): System::Int\n  ret 7\n"
            "fun g(): System::String\n  ret \"seven\"\n"
            "fun wantStr(s: System::String): System::Int\n"
            "  ret System::length(s)\n"
            "fun wantInt(n: System::Int): System::Int\n"
            "  ret n\n"
            "fun main(): System::Int\n"
            "  ret wantInt(g()) * 10 + wantStr(g())\n")
        self.assertEqual(75, rc)   # 7*10 + 5

    def test_result_only_overloads_ambiguous_without_expectation(self):
        errs = _errors_of(
            "namespace Main\nimport System\n"
            "fun g(): System::Int\n  ret 7\n"
            "fun g(): System::String\n  ret \"seven\"\n"
            "fun main(): System::Int\n"
            "  let x = g()\n"
            "  ret 0\n")
        self.assertNotEqual("", errs)

    def test_local_let_shadows_outer_fun(self):
        # RULED (2026-07-04): a local `let`/`fun` SHADOWS (hides) same-name
        # outers — it does not join the candidate set. So the local String
        # `h` hides the global Int `h`, and h(21) cannot resolve.
        errs = _errors_of(
            "namespace Main\nimport System\n"
            "fun h(n: System::Int): System::Int\n  ret n * 2\n"
            "fun main(): System::Int\n"
            "  let h = (s: System::String) => System::length(s)\n"
            "  ret h(21) + h(\"abc\")\n")
        self.assertNotEqual("", errs)


class TestStrictAmbiguity(TestCase):
    def test_subtype_related_candidates_are_ambiguous(self):
        # RULED (2026-07-04): NO most-specific tie-breaking. An Int is
        # assignable to both `Int` and `Int|String` params, so f(5) has two
        # viable candidates → ambiguity error, NOT a silent pick of `Int`.
        errs = _errors_of(
            "namespace Main\nimport System\n"
            "fun f(x: System::Int): System::Int\n  ret 1\n"
            "fun f(x: System::Int | System::String): System::Int\n  ret 2\n"
            "fun main(): System::Int\n  ret f(5)\n")
        self.assertIn("Ambiguous", errs)


class TestFragileBaseWarning(TestCase):
    @staticmethod
    def __stderr_of(src: str) -> tuple[bool, str]:
        import contextlib as _c, io as _io2
        buf = _io2.StringIO()
        with _c.redirect_stderr(buf):   # warnings print to stderr
            code = c.compile([c.Input(src, "test.yafl")],
                             use_stdlib=True, just_testing=True)
        return bool(code), buf.getvalue()

    def test_multiple_overloads_of_one_parent_warns_and_names_it(self):
        # REFINED (2026-07-05): warn only when one override subsumes several
        # SIMILAR methods of a SINGLE immediate parent (a family of overloads
        # captured by a broad union/generic signature) — and name that parent.
        code, out = self.__stderr_of(
            "namespace Main\nimport System\n"
            "interface P\n"
            "  fun handle(x: System::Int): System::Int\n"
            "  fun handle(x: System::String): System::Int\n"
            "class C() : P\n"
            "  fun handle(x: System::Int | System::String): System::Int\n"
            "    ret 1\n"
            "fun main(): System::Int\n  ret 0\n")
        self.assertTrue(code)                       # a WARNING, not an error
        self.assertIn("warning", out)
        self.assertIn("overrides 2 similar methods of `P`", out)

    def test_one_method_each_from_different_parents_is_silent(self):
        # The normal case: two interfaces each declaring the same method, one
        # impl satisfying both — different parents, one each → no warning.
        code, out = self.__stderr_of(
            "namespace Main\nimport System\n"
            "interface A\n  fun m(): System::Int\n"
            "interface B\n  fun m(): System::Int\n"
            "class C() : A|B\n  fun m(): System::Int\n    ret 1\n"
            "fun main(): System::Int\n  ret 0\n")
        self.assertTrue(code)
        self.assertNotIn("overrides", out)

    def test_single_slot_override_is_silent(self):
        code, out = self.__stderr_of(
            "namespace Main\nimport System\n"
            "interface A\n  fun m(): System::Int\n"
            "class C() : A\n  fun m(): System::Int\n    ret 1\n"
            "fun main(): System::Int\n  ret 0\n")
        self.assertTrue(code)
        self.assertNotIn("overrides", out)

    def test_global_let_of_function_type_now_works(self):
        # Was a KNOWN_GAP (function-typed global crashed lazy init); fixed
        # 2026-07-04 — see tests/test_function_typed_globals.py. Here just
        # confirm it compiles and runs (a direct lambda lowers to a fun; the
        # lazy path handles the rest).
        rc, _ = compile_and_run_stdlib_capture(
            "namespace Main\nimport System\n"
            "let h: (:System::String): System::Int = (s: System::String) => System::length(s)\n"
            "fun main(): System::Int\n"
            "  ret h(\"abc\")\n")
        self.assertEqual(3, rc)


class TestOverrideByAssignability(TestCase):
    _SHAPES = (
        "namespace Main\nimport System\n"
        "interface Shape\n"
        "  fun describe(): System::Int\n"
        "class Circle() : Shape\n"
        "  fun describe(): System::Int\n"
        "    ret 10\n"
        "class Square() : Shape\n"
        "  fun describe(): System::Int\n"
        "    ret 20\n"
        "fun poke(s: Shape): System::Int\n"
        "  ret s.describe()\n")

    def test_virtual_dispatch_o0_and_o3_agree(self):
        src = self._SHAPES + (
            "fun main(): System::Int\n"
            "  ret poke(Circle()) + poke(Square())\n")
        for level in (0, 3):
            rc, _ = compile_and_run_stdlib_capture(src, optimization_level=level)
            self.assertEqual(30, rc, f"dispatch diverged at -O{level}")


class TestKnownGaps(TestCase):
    def test_duplicate_route_resolution_is_not_ambiguous(self):
        # Regression: the same statement reachable via root scope and import
        # scope must count as ONE candidate (was: "Ambiguous — candidates: X"
        # listing a single name).
        rc, _ = compile_and_run_stdlib_capture(
            "namespace Main\nimport System\nimport System::IO\n"
            "fun f(c: System::Int): System::Bool\n  ret c == 32\n"
            "fun main(): System::Int\n  ret f(32) ? 0 : 1\n")
        self.assertEqual(0, rc)

    def test_literal_spelling_is_its_type(self):
        # RULED (2026-07-04, final): 37 is Int, 37i32 is Int32, a char
        # literal IS an Int32 literal, 12.5 is Float64, 12.5f32 is Float32.
        # No conversion in any direction: type what you mean.
        rc, _ = compile_and_run_stdlib_capture(
            "namespace Main\nimport System\n"
            "fun isParen(c: System::Int32): System::Bool\n"
            "  ret c == 40i32\n"
            "fun isParenChar(c: System::Int32): System::Bool\n"
            "  ret c == '('\n"
            "fun main(): System::Int\n"
            "  ret isParen(System::byteAt(\"(\", 0)) && isParenChar(System::byteAt(\"(\", 0)) ? 0 : 1\n")
        self.assertEqual(0, rc)

    def test_bare_int_literal_does_not_convert_to_int32(self):
        # `c == 40` with c: Int32 is an ERROR — spell it 40i32.
        errs = _errors_of(
            "namespace Main\nimport System\n"
            "fun isParen(c: System::Int32): System::Bool\n"
            "  ret c == 40\n"
            "fun main(): System::Int\n"
            "  ret isParen(System::byteAt(\"(\", 0)) ? 0 : 1\n")
        self.assertNotEqual("", errs)

    def test_char_literal_is_not_an_Int(self):
        # RULED (2026-07-04, final): a char literal is an Int32 literal —
        # comparing one against a bigint Int is an error, like any other
        # width mismatch. Type what you mean.
        errs = _errors_of(
            "namespace Main\nimport System\n"
            "fun isSpace(c: System::Int): System::Bool\n"
            "  ret c == ' '\n"
            "fun main(): System::Int\n"
            "  ret isSpace(32) ? 0 : 1\n")
        self.assertNotEqual("", errs)
