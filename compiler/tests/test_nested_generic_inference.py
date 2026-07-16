"""Inferring a generic function's type param from a NESTED generic call whose
result is a generic-instance type.

`c(wrap(x))` where `wrap<S>(x): Wrap<S>` and `c<S>(x: S): …` must infer c's S =
Wrap<...>. This used to fail: CallExpression compiled the function (and inferred
its params) before the argument, so the argument's type was still `Wrap<S_wrap>`
(placeholder) and c's S came out non-concrete, never instantiating. Compiling the
argument first fixes it. This is what lets generic stream transformers compose
through a `|>` chain.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib

_BASE = (
    "namespace Main\nimport System\n"
    "class [final] Leaf()\n"
    "class [final] Wrap<S>(inner: S)\n"
    "fun wrap<S>(x: S): Wrap<S>\n"
    "  ret Wrap<S>(x)\n"
    "fun unwrap<S>(w: Wrap<S>): S\n"
    "  ret w.inner\n")


class TestNestedGenericInference(TestCase):
    def test_infer_param_from_nested_generic_call(self):
        # c<S>(x: S) inferring S = Wrap<Leaf> from the nested call wrap(Leaf()).
        src = _BASE + (
            "fun c<S>(x: S): System::Int\n"
            "  ret 9\n"
            "fun main(): System::Int\n"
            "  ret c(wrap(Leaf()))\n")
        self.assertEqual(9, compile_and_run_stdlib(src))

    def test_double_nested_generic_call(self):
        # Two levels: c(wrap(wrap(Leaf()))) -> S = Wrap<Wrap<Leaf>>.
        src = _BASE + (
            "fun c<S>(x: S): System::Int\n"
            "  ret 7\n"
            "fun main(): System::Int\n"
            "  ret c(wrap(wrap(Leaf())))\n")
        self.assertEqual(7, compile_and_run_stdlib(src))

    def test_nested_call_value_flows(self):
        # The value must actually thread through, not just type-check:
        # unwrap(wrap(Box(5))) gives back the Box, .n = 5.
        src = (
            "namespace Main\nimport System\n"
            "class [final] Box(n: System::Int)\n"
            "class [final] Wrap<S>(inner: S)\n"
            "fun wrap<S>(x: S): Wrap<S>\n"
            "  ret Wrap<S>(x)\n"
            "fun unwrap<S>(w: Wrap<S>): S\n"
            "  ret w.inner\n"
            "fun main(): System::Int\n"
            "  ret unwrap(wrap(Box(5))).n\n")
        self.assertEqual(5, compile_and_run_stdlib(src))

    def test_generic_result_into_generic_param(self):
        # The OUTER callee is itself generic and the INNER's result is a generic
        # ENUM instance (List<T>). Early passes latch the outer's T to the raw
        # `List<T>` spelling of the inner's uncompiled signature; compiled in
        # main's scope that spelling became EnumSpec(type_params=(NamedSpec T))
        # — a hole has_free_placeholders couldn't see, so the latch never
        # refreshed and 'T' survived to the post-converge NamedSpec scan.
        src = (
            "namespace Main\nimport System\n"
            "fun single<T>(a: T): List<T>\n"
            "  ret append(List<T>(), a)\n"
            "fun outer<T>(a: T): List<T>\n"
            "  ret append(List<T>(), a)\n"
            "fun main(): System::Int\n"
            "  let xs = outer(single(42))\n"
            "  ret isEmpty(xs) ? 0 : 9\n")
        self.assertEqual(9, compile_and_run_stdlib(src))

    def test_generic_result_into_same_generic(self):
        # Same shape, same function on both levels: list1(list1(42)).
        src = (
            "namespace Main\nimport System\n"
            "fun list1<T>(a: T): List<T>\n"
            "  ret append(List<T>(), a)\n"
            "fun main(): System::Int\n"
            "  let xs = list1(list1(42))\n"
            "  ret isEmpty(xs) ? 0 : 9\n")
        self.assertEqual(9, compile_and_run_stdlib(src))
