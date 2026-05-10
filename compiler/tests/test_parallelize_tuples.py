"""Unit tests for the auto-parallelise pass.

Drives small yafl programs through tokenize+parse+compile-loop, then runs
parallelize_heavy_tuples() and inspects the resulting AST. The cost-model
test infrastructure is reused for the parse-and-compile-loop helper.

Note on test sources: the yafl parser interprets `fun f(): (T, T, T)` as a
function with three parameters (one of an unnamed type), not a tuple-return
function. We therefore build tuples on the right-hand side of let-destructure
bindings, which exercises the same TupleExpression node we want to test.
"""
from tests.testutil import TimedTestCase as TestCase
from tests.test_cost_model import _statements

import pyast.expression as e
import pyast.match as m
import pyast.statement as s

from lowering.parallelize_tuples import parallelize_heavy_tuples


_PRELUDE = (
    "namespace System\n"
    "typealias Int : __builtin_type__<bigint>\n"
    "fun `+`(left: System::Int, right: System::Int): System::Int\n"
    "    ret __builtin_op__<bigint>(\"add\", left, right)\n"
)


def _function_body(stmts: list, name_part: str) -> e.Expression | None:
    for stmt in stmts:
        if isinstance(stmt, s.FunctionStatement) and f"::{name_part}@" in stmt.name:
            return stmt.body
    raise AssertionError(f"function {name_part!r} not found")


def _find_tuple_or_parallel(node) -> e.Expression | None:
    """Return the first TupleExpression or ParallelExpression encountered
    while walking `node`'s subtree (includes the node itself)."""
    if isinstance(node, (e.TupleExpression, e.ParallelExpression)):
        return node
    if isinstance(node, e.BlockExpression):
        for st in node.statements:
            if isinstance(st, s.LetStatement) and st.default_value is not None:
                found = _find_tuple_or_parallel(st.default_value)
                if found is not None:
                    return found
        return _find_tuple_or_parallel(node.value)
    if isinstance(node, e.CallExpression):
        return _find_tuple_or_parallel(node.parameter) or _find_tuple_or_parallel(node.function)
    if isinstance(node, e.NewExpression):
        return _find_tuple_or_parallel(node.parameter)
    if isinstance(node, e.DotExpression):
        return _find_tuple_or_parallel(node.base)
    if isinstance(node, e.TernaryExpression):
        return (_find_tuple_or_parallel(node.condition)
                or _find_tuple_or_parallel(node.trueResult)
                or _find_tuple_or_parallel(node.falseResult))
    if isinstance(node, e.LambdaExpression):
        return _find_tuple_or_parallel(node.expression)
    if isinstance(node, m.MatchExpression):
        found = _find_tuple_or_parallel(node.subject)
        if found is not None:
            return found
        for arm in node.arms:
            found = _find_tuple_or_parallel(arm.body)
            if found is not None:
                return found
    return None


class TestRewriteDecision(TestCase):
    def test_trivial_tuple_not_rewritten(self):
        src = _PRELUDE + (
            "fun trivialTuple(): System::Int\n"
            "    let (a, b, c) = (1, 2, 3)\n"
            "    ret a + b + c\n"
        )
        rewritten = parallelize_heavy_tuples(_statements(src))
        body = _function_body(rewritten, "trivialTuple")
        found = _find_tuple_or_parallel(body)
        self.assertIsInstance(found, e.TupleExpression,
                              "trivial tuple should not be parallelised")

    def test_two_heavy_children_rewritten(self):
        src = _PRELUDE + (
            "fun heavy(n: System::Int): System::Int\n"
            "    ret heavy(n) + 1\n"
            "fun pair(): System::Int\n"
            "    let (a, b) = (heavy(10), heavy(20))\n"
            "    ret a + b\n"
        )
        rewritten = parallelize_heavy_tuples(_statements(src))
        body = _function_body(rewritten, "pair")
        found = _find_tuple_or_parallel(body)
        self.assertIsInstance(found, e.ParallelExpression,
                              "tuple of two heavy children should be parallelised")
        self.assertEqual(len(found.exprs), 2)
        for child in found.exprs:
            self.assertIsInstance(child, e.LambdaExpression)
            self.assertEqual(len(child.parameters.targets), 0,
                             "synthesised lambda must be zero-arg")

    def test_one_heavy_one_trivial_not_rewritten(self):
        src = _PRELUDE + (
            "fun heavy(n: System::Int): System::Int\n"
            "    ret heavy(n) + 1\n"
            "fun mixed(): System::Int\n"
            "    let (a, b) = (heavy(10), 42)\n"
            "    ret a + b\n"
        )
        rewritten = parallelize_heavy_tuples(_statements(src))
        body = _function_body(rewritten, "mixed")
        found = _find_tuple_or_parallel(body)
        self.assertIsInstance(found, e.TupleExpression,
                              "single heavy child should not trigger parallelisation")

    def test_io_qualifies_low_cpu_child(self):
        src = _PRELUDE + (
            'fun [foreign("rt_io_a"),impure] _io_a(): System::Int\n'
            'fun [foreign("rt_io_b"),impure] _io_b(): System::Int\n'
            "fun ioPair(): System::Int\n"
            "    let (a, b) = (_io_a(), _io_b())\n"
            "    ret a + b\n"
        )
        rewritten = parallelize_heavy_tuples(_statements(src))
        body = _function_body(rewritten, "ioPair")
        found = _find_tuple_or_parallel(body)
        self.assertIsInstance(found, e.ParallelExpression,
                              "two IO-qualifying children should be parallelised")

    def test_existing_parallel_passed_through(self):
        src = _PRELUDE + (
            "fun userPar(): System::Int\n"
            "    let (a, b) = __parallel__(() => 1, () => 2)\n"
            "    ret a + b\n"
        )
        rewritten = parallelize_heavy_tuples(_statements(src))
        body = _function_body(rewritten, "userPar")
        found = _find_tuple_or_parallel(body)
        self.assertIsInstance(found, e.ParallelExpression)


class TestNoSemanticRegression(TestCase):
    def test_pass_idempotent_below_threshold(self):
        src = _PRELUDE + (
            "fun two(): System::Int\n"
            "    let (a, b) = (1, 2)\n"
            "    ret a + b\n"
        )
        once = parallelize_heavy_tuples(_statements(src))
        twice = parallelize_heavy_tuples(once)
        body_once = _function_body(once, "two")
        body_twice = _function_body(twice, "two")
        self.assertIsInstance(_find_tuple_or_parallel(body_once), e.TupleExpression)
        self.assertIsInstance(_find_tuple_or_parallel(body_twice), e.TupleExpression)
