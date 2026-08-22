"""--profile end to end: exact call counters, sampled CPU time, and the two
output files (callgrind + folded), over ONE instrumented program.

Shape: one module-level compile+run for every runtime fixture (the profile
FILE is the per-fixture channel — each test asserts its own rows out of the
parsed result), plus cheap compile-only tests for the instrumentation's
structure and the off-guard.

Flakiness policy: everything numeric asserted here is either EXACT (the
counters are deterministic) or floored with a wide margin on a THREAD-CPU-TIME
basis (the sampling clock is CLOCK_THREAD_CPUTIME_ID, so a loaded machine
slows the wall but not the assertion).
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile

import compiler as c
import codegen.param as e
import codegen.ops as o
import codegen.typedecl as t
from codegen.ir import Function
from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_to_binary, _RUN_ENV

# ── the one profiled program ─────────────────────────────────────────────────
# Counted fixtures are deliberately CHUNKY: big enough that the AST inliner's
# size heuristic (which runs at every level and is structurally load-bearing)
# leaves them alone, so their counters exist in the binary. Sub-threshold
# functions are invisible in profiles BY DESIGN — they exist in no binary at
# any -O level (see docs/profiling-design.md).
_SOURCE = """\
namespace Prof

import System

fun leaf(x: System::Int): System::Int
  let a: System::Int = x * 3 + 1
  let b: System::Int = a * a + x
  let c: System::Int = b / 7 + a
  let d: System::Int = c * 2 + b
  ret d + c + b + a + x

fun [tail] driver(i: System::Int, acc: System::Int): System::Int
  ret i <= 0 ? acc : driver(i - 1, acc + leaf(i))

fun fib(n: System::Int): System::Int
  let pad1: System::Int = n * 2 + 3
  let pad2: System::Int = pad1 * pad1 + n
  let pad3: System::Int = pad2 / 5 + pad1
  ret n <= 1 ? n + pad3 - pad3 : fib(n - 1) + fib(n - 2)

fun double(x: System::Int): System::Int
  let a: System::Int = x * 5 + 2
  let b: System::Int = a * a + x
  ret x * 2 + b - b + a - a

fun futureUser(): System::Int
  let [future] a = double(21)
  let [future] b = double(33)
  ret a + b

fun indirect(n: System::Int): System::Int
  let base: System::Int = n * 2 + 1
  let f = (x: System::Int) => x * base + x * x + x / 3 + base * 2 + 1
  fun [tail] go(i: System::Int, acc: System::Int): System::Int
    ret i <= 0 ? acc : go(i - 1, acc + f(i))
  ret go(50, 0)

fun [tail] burn(i: System::Int, acc: System::Int): System::Int
  ret i <= 0 ? acc : burn(i - 1, acc + i)

fun main(): System::Int
  let r1: System::Int = driver(1000, 0)
  let r2: System::Int = fib(20)
  let r3: System::Int = indirect(9)
  let r4: System::Int = futureUser()
  let r5: System::Int = burn(5000000, 0)
  println(r1)
  println(r2)
  println(r3)
  println(r4)
  println(r5)
  ret 0
"""

# ── Python mirrors of the fixture arithmetic (all operands positive, so C
# truncating division and Python floor division agree) ──────────────────────
def _leaf(x: int) -> int:
    a = x * 3 + 1
    b = a * a + x
    cc = b // 7 + a
    d = cc * 2 + b
    return d + cc + b + a + x

def _fib_counting(n: int, counter: list[int]) -> int:
    counter[0] += 1
    if n <= 1:
        return n
    return _fib_counting(n - 1, counter) + _fib_counting(n - 2, counter)

def _indirect(n: int) -> int:
    base = n * 2 + 1
    f = lambda x: x * base + x * x + x // 3 + base * 2 + 1
    return sum(f(i) for i in range(1, 51))

_EXPECT_R1 = sum(_leaf(i) for i in range(1, 1001))
_FIB_CALLS: list[int] = [0]
_EXPECT_R2 = _fib_counting(20, _FIB_CALLS)
_EXPECT_R3 = _indirect(9)
_EXPECT_R4 = 21 * 2 + 33 * 2
_EXPECT_R5 = 5000000 * 5000001 // 2

# ── one compile + run for the whole module ──────────────────────────────────
_RESULTS: dict | None = None


def _parse_callgrind(text: str) -> dict[str, tuple[int, int]]:
    """fn name -> (self_ns, calls)."""
    rows: dict[str, tuple[int, int]] = {}
    for m in re.finditer(r"^fn=(.+)\n(-?\d+) (\d+) (\d+)$", text, re.M):
        rows[m.group(1)] = (int(m.group(3)), int(m.group(4)))
    return rows


def _parse_folded(text: str) -> dict[str, int]:
    """stack (semicolon-joined names) -> summed weight."""
    stacks: dict[str, int] = {}
    for line in text.splitlines():
        stack, _, weight = line.rpartition(" ")
        if stack and weight.isdigit():
            stacks[stack] = stacks.get(stack, 0) + int(weight)
    return stacks


def _parse_edges(text: str) -> dict[tuple[str, str], int]:
    """(caller fn, callee fn) -> exact calls= count."""
    edges: dict[tuple[str, str], int] = {}
    caller = callee = None
    for line in text.splitlines():
        if line.startswith("fn="):
            caller = line[3:]
        elif line.startswith("cfn="):
            callee = line[4:]
        elif line.startswith("calls=") and caller and callee:
            n = int(line[len("calls="):].split()[0])
            edges[(caller, callee)] = edges.get((caller, callee), 0) + n
    return edges


def _edge(caller_prefix: str, callee_prefix: str) -> int:
    """Summed exact count over edges matching the two name prefixes."""
    return sum(n for (c, k), n in _RESULTS["edges"].items()
               if c.startswith(caller_prefix) and k.startswith(callee_prefix))


def setUpModule():
    global _RESULTS
    binary = compile_to_binary(_SOURCE, profile=True)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            prof_path = os.path.join(tmp, "prof.callgrind")
            run = subprocess.run(
                [binary], capture_output=True, timeout=60,
                env={**_RUN_ENV, "YAFL_PROF_FILE": prof_path})
            assert run.returncode == 0, (
                f"profiled program failed rc={run.returncode}\n{run.stderr.decode()}")
            with open(prof_path, encoding="utf-8") as f:
                cg_text = f.read()
            with open(prof_path + ".folded", encoding="utf-8") as f:
                folded_text = f.read()
    finally:
        os.unlink(binary)
    summary = re.search(r"^summary: (\d+) (\d+)$", cg_text, re.M)
    _RESULTS = {
        "stdout": run.stdout.decode(),
        "stderr": run.stderr.decode(),
        "rows": _parse_callgrind(cg_text),
        "folded": _parse_folded(folded_text),
        "edges": _parse_edges(cg_text),
        "summary": (int(summary.group(1)), int(summary.group(2))) if summary else None,
    }


def _row(prefix: str) -> tuple[str, int, int]:
    """The single callgrind row whose name starts `prefix` (fails if 0 or 2+)."""
    hits = [(name, ns, calls) for name, (ns, calls) in _RESULTS["rows"].items()
            if name.startswith(prefix)]
    assert len(hits) == 1, f"expected exactly one row for {prefix!r}, got {hits}"
    return hits[0]


class TestProfiledRun(TestCase):
    def test_program_output_is_correct(self):
        # Instrumentation must not change semantics.
        self.assertEqual(
            [str(v) for v in (_EXPECT_R1, _EXPECT_R2, _EXPECT_R3, _EXPECT_R4, _EXPECT_R5)],
            _RESULTS["stdout"].split())

    def test_exact_counts_direct_and_tail(self):
        # A [tail] function counts ONCE per logical call (the back edge is a
        # goto); its callee counts once per iteration.
        self.assertEqual(1000, _row("Prof::leaf@")[2])
        self.assertEqual(1, _row("Prof::driver@")[2])
        self.assertEqual(1, _row("Prof::burn@")[2])
        self.assertEqual(1, _row("Prof::main@")[2])

    def test_exact_counts_recursion(self):
        self.assertEqual(_FIB_CALLS[0], _row("Prof::fib@")[2])

    def test_exact_counts_async_hot_path(self):
        # The async hot path is entered exactly once per LOGICAL call — the
        # $async state machine (resumptions) is a separate row whose count
        # depends on scheduling and is deliberately not asserted.
        self.assertEqual(2, _row("Prof::double@")[2])
        self.assertEqual(1, _row("Prof::futureUser@")[2])

    def test_exact_counts_closure(self):
        # `f` is the program's only `=>` lambda; hoisting may synthesise more
        # $lambdas:: helpers (the capturing nested `go`), so assert that the
        # 50-call lambda exists rather than that it is alone.
        lambda_counts = sorted(calls for name, (ns, calls) in _RESULTS["rows"].items()
                               if name.startswith("$lambdas::"))
        self.assertIn(50, lambda_counts,
                      f"no $lambdas:: row with exactly 50 calls: {lambda_counts}")

    def test_exact_edges(self):
        # Call-graph edges carry exact per-(caller,callee) counts: one probe
        # in yafl_prof_enter, covering direct, indirect and musttail calls.
        self.assertEqual(1000, _edge("Prof::driver@", "Prof::leaf@"))
        self.assertEqual(1, _edge("Prof::main@", "Prof::driver@"))
        self.assertEqual(1, _edge("Prof::main@", "Prof::burn@"))
        self.assertEqual(1, _edge("Prof::main@", "Prof::fib@"))
        # Recursion: every fib call except main's root came from fib itself.
        self.assertEqual(_FIB_CALLS[0] - 1, _edge("Prof::fib@", "Prof::fib@"))

    def test_edges_are_consistent_with_counters(self):
        # KCachegrind's core invariant: a function's incoming calls= sum
        # equals its exact Calls counter (roots aside — these fixtures all
        # have callers).
        for prefix in ("Prof::leaf@", "Prof::fib@", "Prof::driver@"):
            incoming = sum(n for (c, k), n in _RESULTS["edges"].items()
                           if k.startswith(prefix))
            self.assertEqual(_row(prefix)[2], incoming,
                             f"incoming edges != Calls for {prefix}")

    def test_sampled_time_lands_on_the_burn(self):
        # 5M iterations is ~300ms of thread CPU at -O0; demand only 50ms
        # worth of samples. No allocation in `burn` — samples arriving at all
        # proves the sampler needs no safe points.
        name, ns, calls = _row("Prof::burn@")
        self.assertGreaterEqual(ns, 50_000_000,
                                f"burn self-time implausibly low: {ns}ns")

    def test_folded_stacks_attribute_the_burn(self):
        burn_weight = sum(w for stack, w in _RESULTS["folded"].items()
                          if "Prof::burn@" in stack)
        self.assertGreaterEqual(burn_weight, 20,
                                f"folded burn weight implausibly low: {burn_weight}")
        # Hierarchy: burn's samples sit under main under the entrypoint.
        self.assertTrue(any("__entrypoint__" in s and "Prof::main@" in s
                            and "Prof::burn@" in s for s in _RESULTS["folded"]),
                        "no entrypoint;main;burn stack in the folded output")

    def test_summary_totals_are_consistent(self):
        self.assertIsNotNone(_RESULTS["summary"], "summary line missing")
        total_ns, total_calls = _RESULTS["summary"]
        self.assertEqual(total_ns, sum(ns for ns, _ in _RESULTS["rows"].values()))
        self.assertEqual(total_calls, sum(cs for _, cs in _RESULTS["rows"].values()))

    def test_profile_announced_on_stderr(self):
        self.assertIn("profile written to", _RESULTS["stderr"])


class TestInstrumentationShape(TestCase):
    """Compile-only structural checks — no binary, no run."""

    _SMALL = """\
namespace T

import System

fun main(): System::Int
  ret 0
"""

    def test_every_function_gets_exactly_one_enter_and_the_table_matches(self):
        c_code = c.compile([c.Input(self._SMALL, "t.yafl")], use_stdlib=True,
                           just_testing=False, profile=True)
        n = int(re.search(r"yafl_prof_fns\[(\d+)\]", c_code).group(1))
        self.assertEqual(n, c_code.count("yafl_prof_enter("),
                         "one ProfEnter per instrumented function")
        self.assertEqual(n, len(re.findall(r'^    \{ ".*", \d+ \},?$', c_code, re.M)),
                         "descriptor rows must match the declared table size")
        self.assertIn(f"yafl_prof_init(yafl_prof_fns, {n}u);", c_code)
        # Every function body has at least one exit hook.
        self.assertGreaterEqual(c_code.count("yafl_prof_leave();"), n)

    def test_off_is_byte_identical_and_clean(self):
        args = ([c.Input(self._SMALL, "t.yafl")],)
        kwargs = dict(use_stdlib=True, just_testing=False)
        default = c.compile(*args, **kwargs)
        explicit_off = c.compile(*args, **kwargs, profile=False)
        self.assertEqual(default, explicit_off,
                         "profile=False must be byte-identical to the default")
        self.assertNotIn("yafl_prof", default,
                         "unprofiled output must not reference the profiler")


class TestInstrumentProfileOpRewrite(TestCase):
    """Function.instrument_profile: enter first; leave before every Return,
    ReturnVoid and musttail Call; Abort NOT bracketed (abort() skips the
    atexit dump — nothing to balance)."""

    def _fn(self, ops: tuple) -> Function:
        return Function(
            name="probe",
            params=t.Struct(fields=(("this", t.DataPointer()),)),
            result=t.DataPointer(),
            stack_vars=t.Struct(fields=()),
            ops=ops,
        )

    def test_enter_leave_placement(self):
        sv = e.StackVar(t.DataPointer(), "$v")
        ops = (
            o.Label("a"),
            o.JumpIf(label="b", condition=sv),
            o.Return(sv),
            o.Label("b"),
            o.Call(function=e.GlobalFunction("tailee"),
                   parameters=e.NewStruct(()), musttail=True),
            o.Label("c"),
            o.Abort(reason="unreachable"),
            o.Label("d"),
            o.ReturnVoid(),
        )
        got = self._fn(ops).instrument_profile(7).ops

        self.assertIsInstance(got[0], o.ProfEnter)
        self.assertEqual(7, got[0].fn_id)
        self.assertEqual(1, sum(isinstance(op, o.ProfEnter) for op in got))
        for i, op in enumerate(got):
            if isinstance(op, (o.Return, o.ReturnVoid)) or (
                    isinstance(op, o.Call) and op.musttail):
                self.assertIsInstance(got[i - 1], o.ProfLeave,
                                      f"exit at {i} not preceded by ProfLeave")
            if isinstance(op, o.Abort):
                self.assertNotIsInstance(got[i - 1], o.ProfLeave,
                                         "Abort must not be preceded by ProfLeave")
        self.assertEqual(3, sum(isinstance(op, o.ProfLeave) for op in got))

    def test_to_c_shapes(self):
        self.assertEqual("    yafl_prof_enter(9u);\n", o.ProfEnter(9).to_c({}))
        self.assertEqual("    yafl_prof_leave();\n", o.ProfLeave().to_c({}))
