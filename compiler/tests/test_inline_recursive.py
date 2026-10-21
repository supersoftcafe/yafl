"""Recursive functions are never inlined.

A function on a cycle of the call graph — calling itself, or reaching itself
through other functions — is left out of every IR inlining policy: inlining
one only unrolls the recursion, a level per round. (`[tail]` recursion is not
affected: tail_loop has already turned it into a loop on the AST.)

`isEven` and `isOdd` below call each other. Without the rule, the size pass
(its threshold raised to take them) inlines each into the other, after which
`isOdd` is unreferenced and trimmed; the pair must survive intact. `count`
calls itself: its caller must not take a copy of its body either.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_c


class TestRecursiveNotInlined(TestCase):
    def test_mutual_pair_survives(self):
        src = (
            "namespace Main\nimport System\n"
            "fun isEven(n: System::Int): System::Bool\n"
            "  ret n == 0 ? true : isOdd(n - 1)\n"
            "fun isOdd(n: System::Int): System::Bool\n"
            "  ret n == 0 ? false : isEven(n - 1)\n"
            "fun main(): System::Int\n"
            "  ret isEven(10) ? 0 : 1\n")
        c = compile_c(src, optimization_level=2, args=("--inline-threshold", "40"))
        self.assertTrue("isEven" in c and "isOdd" in c, "a recursive function was inlined")

    def test_self_recursive_body_not_copied_into_caller(self):
        src = (
            "namespace Main\nimport System\n"
            "fun count(n: System::Int): System::Int\n"
            "  ret n == 0 ? 0 : 1 + count(n - 1)\n"
            "fun main(): System::Int\n"
            "  ret count(5) - 5\n")
        c = compile_c(src, optimization_level=2, args=("--inline-threshold", "40"))
        # The one `n == 0` test is count's own.
        self.assertEqual(c.count("integer_test_eq("), 1)
