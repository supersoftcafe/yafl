from tests.testutil import BatchedTestCase as TestCase

import compiler as c
from tests.testutil import compile_and_run


def _compile_and_run(content: str, timeout: int = 5) -> int:
    code, _ = compile_and_run(content, timeout)
    return code


class TestNewFeatures(TestCase):
    """Tests for features not yet fully implemented or known to fail."""

    def test_pipeline(self):
        content = """namespace System
typealias Int : __builtin_type__<bigint>
fun main(): System::Int
    ret 1 |> (a: System::Int) => a
"""

        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=False, just_testing=False)
        self.assertNotEqual("", result)
        print(result)

    def test_pipeline2(self):
        content = """namespace System
typealias Int : __builtin_type__<bigint>
typealias String : __builtin_type__<str>
fun print(str: System::String): System::Int
    ret __builtin_op__<bigint>("print", str)
fun `+`(left: System::Int, right: System::Int): System::Int
    ret __builtin_op__<bigint>("add", left, right)
fun main(): System::Int
    ret (1, 2) |> (a: System::Int, b: System::Int) => a+b
"""

        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=False, just_testing=False)
        self.assertNotEqual("", result)
        print(result)

    def test_none(self):
        content = """namespace System
typealias Int : __builtin_type__<bigint>
typealias None : ()
let None:None = ()
fun testNone(value:None):Int
  ret 1
fun main(): Int
  ret testNone(None)
"""
        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=False, just_testing=False)
        self.assertNotEqual("", result)
        print(result)

    def test_union_type(self):
        """Union type T|None should parse and compile; a function accepting String|None must work."""
        content = """namespace System
typealias Int : __builtin_type__<bigint>
typealias String : __builtin_type__<str>
typealias None : ()
let None:None = ()

fun print(str: System::String): System::Int
    ret __builtin_op__<bigint>("print", str)

fun maybe_print(in: String|None): System::Int
    ret __builtin_op__<bigint>("print", in)

fun main(): System::Int
    ret maybe_print("Hello")
"""

        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=False, just_testing=False)
        self.assertNotEqual("", result)
        print(result)

    def test_match(self):
        """match expression should dispatch on the runtime variant of a union type."""
        content = """namespace System
typealias Int : __builtin_type__<bigint>
typealias String : __builtin_type__<str>
typealias None : ()
let None:None = ()

fun print(str: System::String): System::Int
    ret __builtin_op__<bigint>("print", str)

fun unwrap(in: String|None): System::Int
    ret match(in)
        (x:String) => print(x)
        (x:None) => 0

fun main(): System::Int
    ret unwrap("Hello")
"""

        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=False, just_testing=False)
        self.assertNotEqual("", result)
        print(result)

    def test_bind_operator(self):
        """?> parses as a call operator: A ?> B desugars to `?>`(A, B)."""
        content = """namespace System
typealias Int : __builtin_type__<bigint>
typealias String : __builtin_type__<str>
fun print(str: System::String): System::Int
    ret __builtin_op__<bigint>("print", str)

fun `?>`(val: System::String, f: (:System::String):System::Int): System::Int
    ret f(val)

fun main(): System::Int
    ret "Hello"
        ?> System::print
"""

        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=False, just_testing=False)
        self.assertNotEqual("", result)
        print(result)

    def test_action_statement(self):
        """Bare expression statement: effectful call result is discarded, return value is unaffected."""
        content = """namespace System
typealias Int : __builtin_type__<bigint>

fun sideEffect(x: System::Int): System::Int
    ret __builtin_op__<bigint>("integer_add", x, x)

fun main(): System::Int
    sideEffect(99)
    ret 7
"""
        code = _compile_and_run(content)
        self.assertEqual(7, code)

    def test_bind_operator_runs(self):
        """?> operator compiles and the binary produces the expected exit code."""
        content = """namespace System
typealias Int : __builtin_type__<bigint>

fun `?>`(val: System::Int, f: (:System::Int):System::Int): System::Int
    ret f(val)

fun double(x: System::Int): System::Int
    ret __builtin_op__<bigint>("integer_add", x, x)

fun main(): System::Int
    ret 3 ?> double
"""
        code = _compile_and_run(content)
        self.assertEqual(6, code)

    def test_oneliner_with_return_type(self):
        """One-liner function with explicit return type annotation."""
        content = """namespace System
typealias Int : __builtin_type__<bigint>

fun `+`(left: System::Int, right: System::Int): System::Int
    ret __builtin_op__<bigint>("integer_add", left, right)

fun addThree(n: System::Int): System::Int => n + 3

fun main(): System::Int => addThree(4)
"""
        code = _compile_and_run(content)
        self.assertEqual(7, code)

    def test_oneliner_infers_return_type(self):
        """One-liner function with no return type — compiler infers it."""
        content = """namespace System
typealias Int : __builtin_type__<bigint>

fun `+`(left: System::Int, right: System::Int): System::Int
    ret __builtin_op__<bigint>("integer_add", left, right)

fun addThree(n: System::Int) => n + 3

fun main(): System::Int => addThree(4)
"""
        code = _compile_and_run(content)
        self.assertEqual(7, code)

    def test_oneliner_block_form_unchanged(self):
        """Block-form functions still work alongside one-liners."""
        content = """namespace System
typealias Int : __builtin_type__<bigint>

fun `+`(left: System::Int, right: System::Int): System::Int
    ret __builtin_op__<bigint>("integer_add", left, right)

fun addThree(n: System::Int): System::Int
    ret n + 3

fun main(): System::Int => addThree(5)
"""
        code = _compile_and_run(content)
        self.assertEqual(8, code)

    def test_oneliner_calls_other_oneliner(self):
        """One-liners can call each other."""
        content = """namespace System
typealias Int : __builtin_type__<bigint>

fun `+`(left: System::Int, right: System::Int): System::Int
    ret __builtin_op__<bigint>("integer_add", left, right)

fun inc(n: System::Int) => n + 1
fun addTwo(n: System::Int) => inc(inc(n))

fun main(): System::Int => addTwo(3)
"""
        code = _compile_and_run(content)
        self.assertEqual(5, code)

    def test_single_element_tuple_collapses_to_value(self):
        """`( expr )` with a single un-named entry is just a parenthesised
        expression. It must lower to the element itself — not to a one-field
        struct that codegen then assigns to an `object_t*` slot, which is
        invalid C and clang rejects."""
        content = """namespace System
typealias Int : __builtin_type__<bigint>

fun `+`(left: System::Int, right: System::Int): System::Int
    ret __builtin_op__<bigint>("integer_add", left, right)

fun main(): System::Int
    ret (1)
"""
        self.assertEqual(1, _compile_and_run(content))

    def test_single_element_tuple_as_subexpression(self):
        """A parenthesised sub-expression — e.g. the else-branch of a ternary,
        as the auto-parallelise perf workload happened to write it — must not
        wrap its value in a one-element tuple either."""
        content = """namespace System
typealias Int : __builtin_type__<bigint>
typealias Bool : __builtin_type__<bool>

fun `+`(left: System::Int, right: System::Int): System::Int
    ret __builtin_op__<bigint>("integer_add", left, right)
fun `<`(left: System::Int, right: System::Int): System::Bool
    ret __builtin_op__<bool>("integer_test_lt", left, right)

fun main(): System::Int
    ret 1 < 0 ? 9 : (3 + 4)
"""
        self.assertEqual(7, _compile_and_run(content))


class TestPipeCaptureAvoidance(TestCase):
    """`l |> (x) => body`: the parameter scopes to the body ONLY — a name in
    `l` must resolve in the enclosing scope even when it matches a parameter
    (the beta-block lowering is capture-avoiding via a fresh $pipe@hash
    intermediate)."""

    def test_pipe_param_shadows_body_not_argument(self):
        # 5 |> (x) => ((x + 1) |> (x) => x * 2): the inner stage's argument
        # `(x + 1)` reads the OUTER stage's x (5) — the inner parameter must
        # not capture it — then the inner x binds 6 → 12. (Parens needed:
        # `|>` binds tighter than `+`.)
        from tests.testutil import compile_and_run_stdlib
        rc = compile_and_run_stdlib(
            "namespace Main\nimport System\n"
            "fun main(): System::Int\n"
            "  ret 5 |> (x) => ((x + 1) |> (x) => x * 2)\n")
        self.assertEqual(12, rc)

    def test_pipe_tuple_params_shadow_body_not_argument(self):
        # The shape that failed in json_pretty: the second binder reuses the
        # names of the first; the argument tuple references the FIRST stage's.
        from tests.testutil import compile_and_run_stdlib
        rc = compile_and_run_stdlib(
            "namespace Main\nimport System\n"
            "fun main(): System::Int\n"
            "  ret (1, 2)\n"
            "    |> (a, b) => (a + b, b)\n"
            "    |> (a, b) => a * b\n")
        self.assertEqual(6, rc)
