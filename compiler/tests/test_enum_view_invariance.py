"""Generic type arguments are INVARIANT over enum views.

A narrowed view (`Circle` of enum `Shape`) is a different type from the root,
so `Box<Circle>` must not pass where `Box<Shape>` is declared — for a generic
ENUM argument exactly as for a generic CLASS argument (user ruling: "They ARE
different types, and it is dangerous to say otherwise"). That the two share a
representation, or would monomorphise to one instance, is a code-sharing
question, never a typing rule. Values still subsume: a `Circle` value is a
`Shape` value, so spelling the root's type argument accepts it.
"""
from __future__ import annotations

import contextlib
import io

import compiler as c
from tests.testutil import TimedTestCase as TestCase


_PRELUDE = """
namespace Test
import System

enum Shape
  enum Circle(r: System::Int)
  enum Square(s: System::Int)

enum Box<T>
  enum Full(v: T)
  enum Empty()

class [final] Holder<T>(v: T)

fun takesBox(b: Box<Shape>): System::Int
  ret 0

fun takesHolder(h: Holder<Shape>): System::Int
  ret 0
"""


def _errors(src: str) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        c.compile([c.Input(src, "test.yafl")], use_stdlib=True, just_testing=True)
    return buf.getvalue()


class TestEnumViewInvariance(TestCase):
    # The value is typed BEFORE it meets the parameter (a let has no expected
    # type), so it really is a Box<Circle>. Written inline as an argument, the
    # construction would take the parameter's `Box<Shape>` as its expected type
    # and legitimately build a Box<Shape> holding a Circle.
    def test_view_as_enum_type_argument_is_rejected(self):
        errs = _errors(_PRELUDE + "fun main(): System::Int\n"
                       "  let b = Full(Circle(1))\n  ret takesBox(b)\n")
        self.assertIn("Parameters are not assignment compatible", errs)

    def test_view_as_class_type_argument_is_rejected(self):
        errs = _errors(_PRELUDE + "fun main(): System::Int\n"
                       "  let h = Holder(Circle(1))\n  ret takesHolder(h)\n")
        self.assertIn("Parameters are not assignment compatible", errs)

    def test_view_values_widen_into_a_root_container(self):
        # The builder's element type is inferred from Circle/Square VALUES, but
        # the declared result asks for List<Shape>: a view binding is
        # provisional, so it widens to the root instead of latching Circle.
        errs = _errors(_PRELUDE + "fun shapes(): System::List<Shape>\n"
                       "  ret System::build(System::push(System::push(System::builder(),"
                       " Circle(1)), Square(2)))\n"
                       "fun main(): System::Int\n  ret System::isEmpty(shapes()) ? 0 : 1\n")
        diagnostics = [l for l in errs.splitlines() if "] - " in l and "warning:" not in l]
        self.assertEqual([], diagnostics)

    def test_let_bound_view_container_is_still_rejected(self):
        # Widening follows the CONTEXT: a let has none, so this really is a
        # List<Circle>, and List<Circle> is not List<Shape>.
        errs = _errors(_PRELUDE + "fun takesList(l: System::List<Shape>): System::Int\n  ret 0\n"
                       "fun main(): System::Int\n"
                       "  let cs = System::prepend(Circle(1), System::List<Circle>())\n"
                       "  ret takesList(cs)\n")
        self.assertIn("Parameters are not assignment compatible", errs)

    def test_root_type_argument_accepts_a_view_value(self):
        errs = _errors(_PRELUDE + "fun main(): System::Int\n"
                       "  ret takesBox(Full<Shape>(Circle(1))) + takesHolder(Holder<Shape>(Circle(2)))\n")
        diagnostics = [l for l in errs.splitlines() if "] - " in l and "warning:" not in l]
        self.assertEqual([], diagnostics)
