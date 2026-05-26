import unittest
from io import StringIO
from contextlib import redirect_stdout
from tests.testutil import TimedTestCase as TestCase, compile_and_run

import compiler as c


# Minimal `System::Int` prelude used by every test program below.
_PRELUDE = (
    "namespace System\n"
    "typealias Int : __builtin_type__<bigint>\n"
    "fun `+`(left: System::Int, right: System::Int): System::Int\n"
    "    ret __builtin_op__<bigint>(\"integer_add\", left, right)\n"
)


def _compile_capturing_errors(content: str) -> tuple[str, str]:
    buf = StringIO()
    with redirect_stdout(buf):
        result = c.compile([c.Input(content, "file.yafl")],
                           use_stdlib=False, just_testing=False, optimization_level=0)
    return result, buf.getvalue()


class TestLazyLets(TestCase):
    """Step-2 end-to-end checks for `let [lazy] x: T = expr` at local scope.

    Step 2 supports only DataPointer-shaped values (Int (bigint), strings,
    classes/unions).  Globals, Int32/Float values, and forward references
    are intentionally out of scope — see test_forward_reference_xfail.
    """

    def test_lazy_let_emits_expected_symbols(self):
        """A `[lazy]` let compiles to C referencing the Lazy$ptr machinery."""
        content = _PRELUDE + (
            "fun main(): System::Int\n"
            "    let [lazy] x: System::Int = 41 + 1\n"
            "    ret x\n"
        )
        result = c.compile([c.Input(content, "file.yafl")],
                           use_stdlib=False, just_testing=False, optimization_level=0)
        self.assertNotEqual("", result, "compilation produced no output")
        self.assertIn("Lazy_ptr_t", result)
        self.assertIn("lazy_fetch_ptr", result)
        self.assertIn("lazy_thunk_enqueue", result)

    def test_lazy_let_returns_correct_value(self):
        """Forcing a `[lazy]` let returns the closure's value."""
        content = _PRELUDE + (
            "fun main(): System::Int\n"
            "    let [lazy] x: System::Int = 41 + 1\n"
            "    ret x\n"
        )
        exit_code, _ = compile_and_run(content)
        self.assertEqual(exit_code, 42)

    def test_lazy_let_referenced_twice_memoises(self):
        """Two references compute the value once (visible via correct result)."""
        content = _PRELUDE + (
            "fun main(): System::Int\n"
            "    let [lazy] x: System::Int = 21\n"
            "    ret x + x\n"
        )
        exit_code, _ = compile_and_run(content)
        self.assertEqual(exit_code, 42)

    def test_lazy_let_captures_normal_local(self):
        """A `[lazy]` body that captures a preceding non-lazy let evaluates
        correctly when forced."""
        content = _PRELUDE + (
            "fun main(): System::Int\n"
            "    let y: System::Int = 40\n"
            "    let [lazy] x: System::Int = y + 2\n"
            "    ret x\n"
        )
        exit_code, _ = compile_and_run(content)
        self.assertEqual(exit_code, 42)

    def test_lazy_let_takes_no_args(self):
        """`[lazy(foo)]` is an error."""
        content = _PRELUDE + (
            "fun main(): System::Int\n"
            "    let [lazy(1)] x: System::Int = 1\n"
            "    ret x\n"
        )
        result, captured = _compile_capturing_errors(content)
        self.assertEqual(result, "")
        self.assertIn("[lazy] takes no arguments", captured)

    def test_lazy_let_requires_initialiser(self):
        """`let [lazy] x: T` (no =) is an error."""
        content = _PRELUDE + (
            "fun main(): System::Int\n"
            "    let [lazy] x: System::Int\n"
            "    ret 1\n"
        )
        result, captured = _compile_capturing_errors(content)
        self.assertEqual(result, "")
        self.assertIn("[lazy] requires an initialiser", captured)

    def test_lazy_let_global_emits_stub(self):
        """A `[lazy]` global lowers to a static Lazy$<irmangle> instance
        and references go through the per-IR-type fetch."""
        content = _PRELUDE + (
            "let [lazy] cached: System::Int = 6 + 1\n"
            "fun main(): System::Int\n"
            "    ret cached\n"
        )
        result = c.compile([c.Input(content, "file.yafl")],
                           use_stdlib=False, just_testing=False, optimization_level=0)
        self.assertNotEqual("", result)
        self.assertIn("Lazy_ptr_t",     result)
        self.assertIn("lazy_fetch_ptr", result)
        # The static stub data lands at `<mangled_name>_data` and the
        # `<mangled_name>` symbol points at it.
        self.assertIn("_data = {",      result)
        self.assertIn("System__cached", result)

    def test_lazy_let_global_returns_correct_value(self):
        """Forcing a `[lazy]` global yields its initialiser's value."""
        content = _PRELUDE + (
            "let [lazy] answer: System::Int = 41 + 1\n"
            "fun main(): System::Int\n"
            "    ret answer\n"
        )
        exit_code, _ = compile_and_run(content)
        self.assertEqual(exit_code, 42)

    def test_lazy_let_global_memoises_across_calls(self):
        """A `[lazy]` global referenced from two functions still inits once."""
        content = _PRELUDE + (
            "let [lazy] shared: System::Int = 20 + 1\n"
            "fun double_it(): System::Int\n"
            "    ret shared + shared\n"
            "fun main(): System::Int\n"
            "    ret double_it()\n"
        )
        exit_code, _ = compile_and_run(content)
        self.assertEqual(exit_code, 42)

    def test_lazy_let_int32_compiles(self):
        """`[lazy]` of an Int32 value generates the Int32-shaped machinery.

        We don't link/run (no native int32 add in libyafl) — this checks the
        compiler emits the correct per-IR-type symbols.
        """
        content = (
            "namespace System\n"
            "typealias Int  : __builtin_type__<bigint>\n"
            "typealias Int32: __builtin_type__<int32>\n"
            "fun main(): System::Int\n"
            "    let [lazy] x: System::Int32 = 42i32\n"
            "    ret 0\n"
        )
        # just_testing=False to exercise the full pipeline including
        # async_lower; just_testing=True skips finals so a missing-use of
        # `x` still leaves the machinery referenced.  Touch x in main so
        # trim doesn't elide everything.
        content = (
            "namespace System\n"
            "typealias Int  : __builtin_type__<bigint>\n"
            "typealias Int32: __builtin_type__<int32>\n"
            "let [const] FORTY_TWO: Int32 = 42i32\n"
            "fun main(): System::Int\n"
            "    let [lazy] x: System::Int32 = FORTY_TWO\n"
            "    let _: System::Int32 = x\n"
            "    ret 0\n"
        )
        result = c.compile([c.Input(content, "file.yafl")],
                           use_stdlib=False, just_testing=True, optimization_level=0)
        self.assertNotEqual("", result)
        self.assertIn("Lazy_i32_t",     result)
        # Waiter task subtype shares its name with async_lower's
        # canonical naming: task$Int32 (C-mangled to task_Int32).
        self.assertIn("task_Int32",     result)
        self.assertIn("lazy_fetch_i32", result)
        self.assertIn("lazy_drain_i32", result)

    def test_lazy_let_tuple_compiles(self):
        """`[lazy]` of a tuple type lowers to a struct-shaped Lazy$s_<hash>
        with the per-shape drain function emitted by the compiler."""
        content = (
            "namespace System\n"
            "typealias Int  : __builtin_type__<bigint>\n"
            "typealias Int32: __builtin_type__<int32>\n"
            "let [const] ONE: Int32 = 1i32\n"
            "let [const] TWO: Int32 = 2i32\n"
            "fun main(): System::Int\n"
            "    let [lazy] x: (a: System::Int32, b: System::Int32) = (a=ONE, b=TWO)\n"
            "    let _: (a: System::Int32, b: System::Int32) = x\n"
            "    ret 0\n"
        )
        result = c.compile([c.Input(content, "file.yafl")],
                           use_stdlib=False, just_testing=True, optimization_level=0)
        self.assertNotEqual("", result)
        # Stub + per-shape drain + fetch all present.
        self.assertIn("Lazy_s_",          result)
        self.assertIn("lazy_fetch_s_",    result)
        self.assertIn("lazy_drain_s_",    result)
        # The waiter task subtype shares its name with async_lower's
        # struct-result task subtype (task$T<hash>) so casts hit the
        # actual emitted struct.
        self.assertIn("task_T",           result)
        # The chain primitives are referenced by the per-IR-type drain.
        self.assertIn("lazy_chain_swap_sentinel", result)
        self.assertIn("lazy_chain_step",          result)

    def test_lazy_let_float64_compiles(self):
        """`[lazy]` of a Float64 value emits the f64 machinery."""
        content = (
            "namespace System\n"
            "typealias Int    : __builtin_type__<bigint>\n"
            "typealias Float64: __builtin_type__<float64>\n"
            "let [const] PI: Float64 = 3.14\n"
            "fun main(): System::Int\n"
            "    let [lazy] x: System::Float64 = PI\n"
            "    let _: System::Float64 = x\n"
            "    ret 0\n"
        )
        result = c.compile([c.Input(content, "file.yafl")],
                           use_stdlib=False, just_testing=True, optimization_level=0)
        self.assertNotEqual("", result)
        self.assertIn("Lazy_f64_t",     result)
        # task$Float64 canonical name shared with async_lower.
        self.assertIn("task_T",         result)
        self.assertIn("lazy_fetch_f64", result)
        self.assertIn("lazy_drain_f64", result)

    def test_forward_reference_between_lazies(self):
        """Two `[lazy]` lets in the same block; the first references
        the second.  Stub allocations hoisted to block entry mean the
        forward-referenced stub slot is bound before the referencing
        lazy's closure is constructed."""
        content = _PRELUDE + (
            "fun main(): System::Int\n"
            "    let [lazy] x: System::Int = y + 1\n"
            "    let [lazy] y: System::Int = 2\n"
            "    ret x\n"
        )
        exit_code, _ = compile_and_run(content)
        self.assertEqual(exit_code, 3)

    def test_forward_reference_to_non_lazy_is_rejected_at_compile(self):
        """A `[lazy]` body that forward-references a *non-lazy* let
        used to crash at force time (only `[lazy]` lets get hoisted to
        block entry; a non-lazy let's slot is uninitialised at the
        capture site).  `check_lazy_forward_refs` now surfaces the
        problem as a compile error with an actionable message."""
        content = _PRELUDE + (
            "fun main(): System::Int\n"
            "    let [lazy] x: System::Int = y + 1\n"
            "    let y: System::Int = 2\n"
            "    ret x\n"
        )
        result, captured = _compile_capturing_errors(content)
        self.assertEqual(result, "")
        self.assertIn("forward-references non-lazy let",                  captured)
        self.assertIn("Mark",                                             captured)
        self.assertIn("as [lazy], or move its declaration before",       captured)
