"""Linear-type checking — every linear value used exactly once.

Uses a test-only `[linear,final]` class `H` so these tests are independent
of whether the IO library is marked linear.
"""
from __future__ import annotations

import io
import contextlib

from tests.testutil import TimedTestCase as TestCase

import compiler as c


# A linear class plus the helpers most tests share.
_PRELUDE = """namespace Main
import System

class [linear,final] H(id: System::Int)

fun mk(): H
  ret H(1)

fun sink([terminal] h: H): System::Int
  ret h.id

fun thread(h: H): H
  ret h
"""


def _compile(body: str) -> tuple[str, str]:
    """Compile _PRELUDE + body; return (c_code, captured_diagnostics)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        result = c.compile([c.Input(_PRELUDE + body, "test.yafl")],
                           use_stdlib=True, just_testing=False)
    return result, buf.getvalue()


class TestLinearPositive(TestCase):
    """Programs that thread linear values correctly must compile."""

    def test_use_once(self):
        code, _ = _compile("""
fun main(): System::Int
  let a = mk()
  ret sink(a)
""")
        self.assertTrue(code, "threading a linear value once must compile")

    def test_thread_through_function(self):
        code, _ = _compile("""
fun main(): System::Int
  let a = mk()
  let b = thread(a)
  ret sink(b)
""")
        self.assertTrue(code, "a non-terminal function may thread the handle on")

    def test_terminal_param_may_be_dropped(self):
        code, _ = _compile("""
fun discard([terminal] h: H): System::Int
  ret 99
fun main(): System::Int
  ret discard(mk())
""")
        self.assertTrue(code, "a [terminal] parameter need not be consumed")

    def test_branch_consumes_consistently(self):
        code, _ = _compile("""
fun pick(h: H, c: System::Bool): System::Int
  ret c ? sink(h) : sink(h)
fun main(): System::Int
  ret pick(mk(), 1 < 2)
""")
        self.assertTrue(code, "using the handle once in every branch must compile")

    def test_early_return_consumes_consistently(self):
        # An `if` whose body early-returns makes the fall-through the *else*
        # path. The handle is consumed exactly once on each path, so this is
        # the early-return equivalent of test_branch_consumes_consistently and
        # must compile — the analysis must not count both uses on one path.
        code, _ = _compile("""
fun pick(h: H, c: System::Bool): System::Int
  if c
    ret sink(h)
  ret sink(h)
fun main(): System::Int
  ret pick(mk(), 1 < 2)
""")
        self.assertTrue(code, "early-return branches each consuming once must compile")

    def test_early_return_then_thread(self):
        # The realistic loop shape: a guard early-returns the handle, and the
        # fall-through threads it on and consumes it.
        code, _ = _compile("""
fun step(h: H, stop: System::Bool): System::Int
  if stop
    ret sink(h)
  let h2 = thread(h)
  ret sink(h2)
fun main(): System::Int
  ret step(mk(), 1 < 2)
""")
        self.assertTrue(code, "guard early-return plus fall-through thread must compile")

    def test_linear_lambda_parameter(self):
        code, _ = _compile("""
fun run(f: (:H): System::Int): System::Int
  ret f(mk())
fun main(): System::Int
  ret run((h: H) => sink(h))
""")
        self.assertTrue(code, "a lambda may take and consume a linear parameter")

    def test_linear_generic_threads(self):
        code, _ = _compile("""
fun idH<[linear] T>(x: T): T
  ret x
fun main(): System::Int
  let a = mk()
  let b = idH<H>(a)
  ret sink(b)
""")
        self.assertTrue(code, "a [linear] type parameter may carry a linear argument")

    def test_linear_generic_accepts_nonlinear(self):
        code, _ = _compile("""
fun idH<[linear] T>(x: T): T
  ret x
fun main(): System::Int
  ret idH<System::Int>(7)
""")
        self.assertTrue(code, "a [linear] type parameter also accepts a non-linear argument")

    def test_destructure_threads_linear(self):
        code, _ = _compile("""
fun pair(): (a: H, b: System::Int)
  ret (a = mk(), b = 0)
fun main(): System::Int
  let (x, y) = pair()
  ret sink(x)
""")
        self.assertTrue(code, "a linear value bound by a destructure must be consumable")

    def test_linear_in_union_consumed_by_match(self):
        code, _ = _compile("""
fun wrap(h: H): H|System::Int
  ret h
fun unwrap(u: H|System::Int): System::Int
  ret match(u)
    (h: H)           => sink(h)
    (n: System::Int) => n
fun main(): System::Int
  ret unwrap(wrap(mk()))
""")
        self.assertTrue(code, "a linear value may sit in a union and be discharged by match")


class TestLinearNegative(TestCase):
    """Programs that misuse linear values must be rejected."""

    def _reject(self, body: str, needle: str):
        code, errors = _compile(body)
        self.assertEqual("", code, "expected a compile error")
        self.assertIn(needle, errors.lower())

    def test_leak(self):
        self._reject("""
fun main(): System::Int
  let a = mk()
  ret 0
""", "never used")

    def test_fresh_linear_dropped_in_statement(self):
        # A fresh linear value produced by a bare statement and never bound
        # leaks — it must be bound and consumed.
        self._reject("""
fun main(): System::Int
  mk()
  ret 0
""", "discarded")

    def test_unmarked_drop_rejected(self):
        # A function that quietly drops a linear param — without [terminal] —
        # is an error; the loophole cannot be pushed into another function.
        self._reject("""
fun discard(h: H): System::Int
  ret 0
fun main(): System::Int
  ret discard(mk())
""", "never used")

    def test_double_use(self):
        self._reject("""
fun two(a: H, b: H): System::Int
  ret sink(a) + sink(b)
fun main(): System::Int
  let a = mk()
  ret two(a, a)
""", "used 2 times")

    def test_use_after_consume(self):
        self._reject("""
fun main(): System::Int
  let a = mk()
  let n = sink(a)
  ret sink(a)
""", "used 2 times")

    def test_branch_inconsistent(self):
        self._reject("""
fun pick(h: H, c: System::Bool): System::Int
  ret c ? sink(h) : 0
fun main(): System::Int
  ret pick(mk(), 1 < 2)
""", "inconsistently across branches")

    def test_lambda_capture(self):
        self._reject("""
fun run(f: (:System::Int): System::Int): System::Int
  ret f(1)
fun main(): System::Int
  let a = mk()
  ret run((n: System::Int) => sink(a))
""", "captured by a nested function or lambda")

    def test_nested_function_capture(self):
        self._reject("""
fun main(): System::Int
  let a = mk()
  fun inner(): System::Int
    ret sink(a)
  ret inner()
""", "captured by a nested function or lambda")

    def test_lazy_let_of_linear_type(self):
        """`[lazy]` memoises its value across forces — multiple reads
        of a linear value would each yield the cached instance,
        breaking the use-once invariant.  Reject at declaration."""
        self._reject("""
fun main(): System::Int
  let [lazy] h: H = mk()
  ret sink(h)
""", "linear")

    def test_lazy_body_captures_linear(self):
        """A `[lazy]` body captures linear values into its synthesised
        closure — same rationale as the lambda-capture rejection."""
        self._reject("""
fun main(): System::Int
  let a = mk()
  let [lazy] x: System::Int = sink(a)
  ret x
""", "linear")

    def test_match_arm_leaks_linear(self):
        # The IO arm binds a linear value but never consumes it.
        self._reject("""
fun unwrap(u: H|System::Int): System::Int
  ret match(u)
    (h: H)           => 0
    (n: System::Int) => n
fun main(): System::Int
  ret 0
""", "never used")

    def test_linear_stored_in_enum_rejected(self):
        self._reject("""
enum Box
  enum Full(h: H)
  enum Empty()
fun main(): System::Int
  ret 0
""", "stored in an enum")

    def test_linear_field_in_nonlinear_class(self):
        self._reject("""
class [final] Box(h: H)
fun main(): System::Int
  ret 0
""", "must be declared [linear]")

    def test_linear_requires_final(self):
        self._reject("""
class [linear] NotFinal(id: System::Int)
fun main(): System::Int
  ret 0
""", "final")

    def test_global_linear_let(self):
        self._reject("""
let g: H = mk()
fun main(): System::Int
  ret 0
""", "global let")

    def test_generic_dup_is_template_error(self):
        self._reject("""
fun dup<[linear] T>(x: T): (a: T, b: T)
  ret (a = x, b = x)
fun main(): System::Int
  ret 0
""", "used 2 times")

    def test_linear_to_unrestricted_type_parameter(self):
        self._reject("""
fun plain<T>(x: T): System::Int
  ret 0
fun main(): System::Int
  let a = mk()
  ret plain<H>(a)
""", "unrestricted type parameter")

    def test_linear_type_param_on_class_rejected(self):
        self._reject("""
class [final] Box<[linear] T>(v: T)
fun main(): System::Int
  ret 0
""", "only supported on functions")
