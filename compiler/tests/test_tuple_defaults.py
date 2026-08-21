"""Named fields and default values are TUPLE-type features.

A tuple type may declare per-field defaults (`(x: Int, y: Int = 10)`); a tuple
value converging on such a receiver is transformed — positional entries bind
left to right, named entries bind by field name in any order after the
positionals, and every remaining unbound field fills from its default. Function
calling inherits all of this because parameters ARE a tuple: there is no
call-specific machinery.

A default must be a literal (Integer/Float/String/Bool) or a reference to a
`[const]` global let — nothing with captures, effects, or evaluation order.
"""
from __future__ import annotations

import contextlib
import io

import compiler as c

from tests.testutil import BatchedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


def _errors(src: str) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        c.compile([c.Input(src, "test.yafl")], use_stdlib=True, just_testing=True)
    return buf.getvalue()


_RUNTIME = """namespace Test
import System

let [const] BIAS: Int = 100

fun scale(x: Int, factor: Int = 10, bias: Int = 1): Int
  ret x * factor + bias

fun shift(x: Int, by: Int = BIAS): Int
  ret x + by

fun main(): Int
  print(String(scale(5, 2, 3)) + "\\n")
  print(String(scale(5, 2)) + "\\n")
  print(String(scale(5)) + "\\n")
  print(String(scale(5, bias = 7)) + "\\n")
  print(String(scale(5, bias = 7, factor = 2)) + "\\n")
  print(String(shift(5)) + "\\n")
  let p: (x: Int, y: Int = 10) = (x = 5)
  print(String(p.x + p.y) + "\\n")
  let q: (a: Int, b: Int) = (b = 2, a = 40)
  print(String(q.a - q.b) + "\\n")
  ret 0
"""

_RUNTIME_EXPECTED = "13\n11\n51\n57\n17\n105\n15\n38\n"


class TestTupleDefaultsRuntime(TestCase):
    def test_defaults_named_and_tuple_receivers(self):
        rc, out = compile_and_run_stdlib_capture(_RUNTIME, timeout=30)
        self.assertEqual(0, rc, f"program failed; stdout:\n{out}")
        self.assertEqual(_RUNTIME_EXPECTED, out)


_PRELUDE = "namespace Test\nimport System\n"


class TestTupleDefaultsErrors(TestCase):
    def test_default_must_be_literal_or_const(self):
        errs = _errors(_PRELUDE
            + "fun g(): Int\n  ret 3\n"
            + "fun f(x: Int = g()): Int\n  ret x\n"
            + "fun main(): Int\n  ret f()\n")
        self.assertIn("default", errs.lower())

    def test_unknown_named_field_is_rejected(self):
        errs = _errors(_PRELUDE
            + "fun f(x: Int, y: Int = 1): Int\n  ret x + y\n"
            + "fun main(): Int\n  ret f(1, nope = 2)\n")
        self.assertTrue(errs.strip(), "expected an error for an unknown field name")

    def test_double_binding_is_rejected(self):
        errs = _errors(_PRELUDE
            + "fun f(x: Int, y: Int = 1): Int\n  ret x + y\n"
            + "fun main(): Int\n  ret f(1, x = 2)\n")
        self.assertTrue(errs.strip(), "expected an error for binding x twice")

    def test_missing_required_field_is_rejected(self):
        errs = _errors(_PRELUDE
            + "fun f(x: Int, y: Int = 1): Int\n  ret x + y\n"
            + "fun main(): Int\n  ret f(y = 2)\n")
        self.assertTrue(errs.strip(), "expected an error for the missing x")


class TestTupleDefaultsOverloads(TestCase):
    def test_defaults_do_not_confuse_distinct_overloads(self):
        # Same name, parameter types differ: the shortened call still selects
        # by the argument it does supply.
        src = (_PRELUDE
            + "fun tag(x: Int, pad: Int = 0): Int\n  ret x + pad\n"
            + "fun tag(x: String, pad: Int = 0): Int\n  ret pad\n"
            + "fun main(): Int\n  ret tag(7) == 7 ? 0 : 1\n")
        rc, out = compile_and_run_stdlib_capture(src, timeout=30)
        self.assertEqual(0, rc, f"overload selection failed; stdout:\n{out}")

    def test_ambiguous_after_defaults_is_an_error(self):
        # With defaults considered, tag(7) matches both — must be reported,
        # never silently picked.
        errs = _errors(_PRELUDE
            + "fun tag(x: Int, pad: Int = 0): Int\n  ret x + pad\n"
            + "fun tag(x: Int): Int\n  ret x\n"
            + "fun main(): Int\n  ret tag(7)\n")
        self.assertTrue(errs.strip(), "expected an ambiguity error")


_NONE_DEFAULT = """namespace Test
import System

# `None` is a literal: no captures, no effects, no evaluation order — exactly
# what a default is allowed to be. An optional field defaulting to None is the
# single most natural default there is.
class [final] Node(tag: String, parent: Node|None = None)

fun label(x: String, note: String|None = None): String
  ret match(note)
    (n: String) => x + "/" + n
    ()          => x

fun parentTag(n: Node): String
  ret match(n.parent)
    (p: Node) => p.tag
    ()        => "-"

fun main(): Int
  let root = Node("root")
  let kid = Node("kid", root)
  print(label("a") + "\\n")
  print(label("a", "b") + "\\n")
  print(parentTag(kid) + "\\n")
  print(parentTag(root) + "\\n")
  ret 0
"""


class TestNoneDefault(TestCase):
    def test_none_is_a_valid_default(self):
        self.assertEqual("", _errors(_NONE_DEFAULT))

    def test_none_default_runs(self):
        self.assertEqual((0, "a\na/b\nroot\n-\n"),
                         compile_and_run_stdlib_capture(_NONE_DEFAULT))
