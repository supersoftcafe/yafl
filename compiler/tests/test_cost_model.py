"""Unit tests for the cost-model pass.

These tests drive small yafl programs through tokenize+parse, then construct
a CostModel directly from the parsed statements (without running the full
compile/lowering pipeline). The cost model only needs:

  - FunctionStatement.name
  - FunctionStatement.body
  - FunctionStatement.attributes (for [impure])
  - Names in NamedExpression to match function names

…all of which the parser populates.
"""
from tests.testutil import TimedTestCase as TestCase

from parsing.tokenizer import tokenize
from parsing.parser import parse
import pyast.resolver as g
from lowering.cost_model import (
    CostModel, Weight,
    LITERAL_W, OP_W, ALLOC_W, INDIRECT_DEFAULT,
    FOREIGN_IMPURE_W, FOREIGN_PLAIN_W,
    CAP_CPU, CAP_IO, SPAWN_W,
)


def _statements(source: str):
    """Tokenize, parse, then iterate compile() to convergence — mirrors the
    relevant prefix of compiler.__iterate_and_compile so names get resolved
    to the same qualified form callers and callees share."""
    tokens = tokenize(source, "t.yafl")
    result = parse(tokens)
    assert not result.errors, f"parse errors: {result.errors}"
    statements = result.value

    for _ in range(100):
        resolver = g.ResolverRoot(statements)
        new_statements = []
        for stmt in statements:
            scoped = resolver
            if hasattr(stmt, "imports"):
                from pyast.statement import NamedStatement
                if isinstance(stmt, NamedStatement):
                    scopes = set(x.path for x in stmt.imports.imports) if stmt.imports else set()
                    own_ns = stmt.name.rpartition("::")[0]
                    if own_ns:
                        scopes.add(own_ns)
                    scoped = g.AddScopeResolution(resolver, scopes)
            compiled, extras = stmt.compile(scoped, None)
            new_statements.append(compiled)
            new_statements.extend(extras)
        if new_statements == statements:
            break
        statements = new_statements
    return statements


def _summary(cm, name_part: str) -> Weight:
    """Look up a summary by simple name fragment (parser emits qualified
    names like 'Main::leaf@xxxxx')."""
    matches = [(k, v) for k, v in cm.summaries.items() if f"::{name_part}@" in k]
    if len(matches) != 1:
        raise AssertionError(
            f"Expected unique summary for {name_part!r}; got: "
            f"{[k for k, _ in matches]}")
    return matches[0][1]


class TestForeignSeed(TestCase):
    def test_impure_foreign_seeded_with_io(self):
        src = (
            'fun [foreign("rt_read"),impure] _read(n: System::Int): System::Int\n'
            'fun [foreign("rt_const"),sync]  _const(): System::Int\n'
        )
        cm = CostModel(_statements(src))
        self.assertEqual(_summary(cm, "_read"), FOREIGN_IMPURE_W)
        self.assertEqual(_summary(cm, "_const"), FOREIGN_PLAIN_W)

    def test_unmarked_foreign_uses_plain_seed(self):
        src = 'fun [foreign("rt_x")] _x(): System::Int\n'
        cm = CostModel(_statements(src))
        self.assertEqual(_summary(cm, "_x"), FOREIGN_PLAIN_W)


class TestSummaries(TestCase):
    def test_leaf_function_returns_literal(self):
        src = "fun leaf(): System::Int  ret 42\n"
        cm = CostModel(_statements(src))
        self.assertEqual(_summary(cm, "leaf"), LITERAL_W)

    def test_caller_includes_callee_summary(self):
        src = (
            "fun leaf(): System::Int  ret 42\n"
            "fun caller(): System::Int  ret leaf()\n"
        )
        cm = CostModel(_statements(src))
        leaf = _summary(cm, "leaf")
        caller = _summary(cm, "caller")
        # caller body = CallExpression(NamedExpression('leaf'), TupleExpression([]))
        # weight = LITERAL_W (named) + 0 (empty tuple) + leaf
        expected = LITERAL_W + leaf
        self.assertEqual(caller, expected)

    def test_io_propagates_through_call_chain(self):
        src = (
            'fun [foreign("rt_read"),impure] _read(n: System::Int): System::Int\n'
            "fun wrapper(): System::Int  ret _read(7)\n"
        )
        cm = CostModel(_statements(src))
        self.assertGreater(_summary(cm, "wrapper").io, 0,
                           "IO weight should propagate from _read up to wrapper")

    def test_indirect_call_uses_default(self):
        src = (
            "fun viaParam(f: (): System::Int): System::Int  ret f()\n"
        )
        cm = CostModel(_statements(src))
        self.assertGreaterEqual(_summary(cm, "viaParam").cpu, INDIRECT_DEFAULT.cpu)


class TestRecursion(TestCase):
    def test_self_recursion_capped(self):
        src = "fun rec(): System::Int  ret rec()\n"
        cm = CostModel(_statements(src))
        w = _summary(cm, "rec")
        self.assertLessEqual(w.cpu, CAP_CPU)
        self.assertLessEqual(w.io, CAP_IO)

    def test_mutual_recursion_capped(self):
        src = (
            "fun aa(): System::Int  ret bb()\n"
            "fun bb(): System::Int  ret aa()\n"
        )
        cm = CostModel(_statements(src))
        for name in ("aa", "bb"):
            w = _summary(cm, name)
            self.assertLessEqual(w.cpu, CAP_CPU, f"{name} cpu exceeded cap")
            self.assertLessEqual(w.io, CAP_IO, f"{name} io exceeded cap")


class TestParallelExpression(TestCase):
    def test_parallel_collapses_to_max(self):
        # Manually construct: weigh a ParallelExpression directly. Its weight
        # should be SPAWN_W + max-of-children, not sum-of-children. Lambda
        # bodies are walked in place.
        from parsing.tokenizer import LineRef
        import pyast.expression as e
        # Build: __parallel__(() => 1, () => 2)
        lr = LineRef("t.yafl", 1, 0)
        lambda1 = e.LambdaExpression(lr, parameters=None, expression=e.IntegerExpression(lr, 1))  # type: ignore[arg-type]
        lambda2 = e.LambdaExpression(lr, parameters=None, expression=e.IntegerExpression(lr, 2))  # type: ignore[arg-type]
        par = e.ParallelExpression(lr, exprs=[lambda1, lambda2])

        cm = CostModel([])
        w = cm.weigh(par)
        # ParallelExpression contributes SPAWN_W + max(child_weights).
        # Each child is a LambdaExpression (as-value) → ALLOC_W.
        self.assertEqual(w, SPAWN_W + ALLOC_W)
