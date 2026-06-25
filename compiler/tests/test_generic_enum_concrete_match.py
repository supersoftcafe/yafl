"""Matching the VARIANTS of a generic enum at a CONCRETE instantiation.

Matching `Chain<T>`'s variants inside a generic function works (the whole stdlib
relies on it); matching a generic enum's variants where the instantiation is
spelled concretely in a non-generic context used to crash codegen
(union_repr.leaf_id: the arm's leaf name was mangled `$generic$…` while the
subject's all_leaf_names were not, so the tag-index lookup missed). leaf_id now
compares leaves by base identity, so either spelling lines up.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib

_ENUM = ("namespace Main\nimport System\n"
         "enum Box<T>\n"
         "  enum BoxEmpty()\n"
         "  enum BoxFull(value: T)\n")


class TestGenericEnumConcreteMatch(TestCase):
    def test_concrete_variant_match_full(self):
        src = _ENUM + (
            "fun classify(x: Box<System::Int>): System::Int\n"
            "  ret match(x)\n"
            "    (e: BoxEmpty) => 0\n"
            "    (f: BoxFull)  => f.value\n"
            "fun main(): System::Int\n"
            "  ret classify(BoxFull<System::Int>(7))\n")
        self.assertEqual(7, compile_and_run_stdlib(src))

    def test_concrete_variant_match_empty(self):
        src = _ENUM + (
            "fun classify(x: Box<System::Int>): System::Int\n"
            "  ret match(x)\n"
            "    (e: BoxEmpty) => 42\n"
            "    (f: BoxFull)  => f.value\n"
            "fun main(): System::Int\n"
            "  ret classify(BoxEmpty<System::Int>())\n")
        self.assertEqual(42, compile_and_run_stdlib(src))
