"""bootstrap C emission — mode `c` must produce BYTE-IDENTICAL C to Python's
__create_c_code at -O0 over the corpus: the full pipeline through codegen —
per-statement global codegen, entry point, lazy machinery, ssa_validate,
trim, globalfuncs, flat-init resolution, sync inference, branch threading +
copy propagation, sroa, phi removal, async lowering, uninit check, and the
final Application.gen assembly (perfect-hash vtables, extends-ordered
emission, GC roots, main).

Telescopes on the exits contract: same corpus, same error-printing rule, the
whole back half further. PYTHONHASHSEED=0 is asserted hard — Python's C
output is only deterministic under it (the known codegen-nondeterminism bug),
and a flaky byte contract is worse than none.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import compiler as c
import lowering.complex_enums
import lowering.constants
import lowering.drops
import lowering.generics
import lowering.ast_inline
import lowering.integers
import lowering.block_exits
import lowering.lambdas
import lowering.simple_classes
import lowering.lower_lazy_lets
import lowering.strings
import lowering.hoist_nested
import lowering.lambda_globals
import lowering.lambda_lift
import lowering.tail_loop
import lowering.unions
import pyast.statement as s
from parsing.tokenizer import tokenize
from parsing.parser import parse

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import _RUN_ENV

_REPO = Path(__file__).parent.parent.parent

# Whole-program corpus: every file compiles WITH the stdlib (fed to the port
# as a multi-file stream, parsed part-wise by the mirror), so the contract
# diffs real emitted C rather than error text. Main-less stdlib members are
# exercised as the stdlib of every other run.
_STDLIB = sorted((_REPO / "compiler" / "stdlib").glob("*.yafl"))
_CORPUS = sorted((_REPO / "examples").glob("*.yafl")) \
    + sorted((Path(__file__).parent / "corpus_converge").glob("*.yafl"))

_CONVERGE = c.__dict__["__converge"]
_CREATE_C = c.__dict__["__create_c_code"]
_IS_MAIN = c.__dict__["__is_main_function"]


class TestBootstrapC(TestCase):
    _TIMEOUT = 3600

    @classmethod
    def setUpClass(cls):
        assert os.environ.get("PYTHONHASHSEED") == "0", (
            "test_bootstrap_c requires PYTHONHASHSEED=0 — Python's C output "
            "is only deterministic under it")
        from tests.testutil import shared_bootstrap_binary
        cls.binary = shared_bootstrap_binary()

    @classmethod
    def tearDownClass(cls):
        pass  # the shared binary is cache-owned

    def test_c_matches_python(self):
        self._compare_corpus(0, "c")

    def test_c_matches_python_O1(self):
        # The same whole-program byte-compare at -O1: bounds_elim, dead
        # stores, static-object promotion, and the pre-async collapse
        # fixpoint (struct/tag/discriminator folds, string concat/
        # accumulation) plus stack promotion all run on both sides.
        self._compare_corpus(1, "c1")

    def test_c_matches_python_O2(self):
        # -O2 adds the bounded small-function inline fixpoint (IR inliner +
        # trim to shape stability) on both sides.
        self._compare_corpus(2, "c2")

    def test_c_matches_python_O3(self):
        # -O3 adds [inline(always)] fusion and the single-caller fold with
        # vtable-slot trimming.
        self._compare_corpus(3, "c3")

    def _compare_corpus(self, optimization_level: int, mode: str):
        # Every corpus file is independent, and per file the two compiles
        # are independent — a bounded pool takes BOTH job kinds (Python
        # mirrors need processes for the GIL; port runs are subprocess
        # wrappers), capped so memory stays sane. Results compare in corpus
        # order, so the first diff reported is always the simplest file's.
        # Under a parallel test runner this process is daemonic and cannot
        # fork a pool — compute serially instead.
        import multiprocessing
        if multiprocessing.current_process().daemon:
            py = {path: _python_c_text(path.name, optimization_level)
                  for path in _CORPUS}
            port = {path: _run_port_c(self.binary, _port_stream(path), mode)
                    for path in _CORPUS}
        else:
            from concurrent.futures import ProcessPoolExecutor
            with ProcessPoolExecutor(max_workers=4) as pool:
                py_futs = {path: pool.submit(_python_c_text, path.name,
                                             optimization_level)
                           for path in _CORPUS}
                port_futs = {path: pool.submit(_run_port_c, self.binary,
                                               _port_stream(path), mode)
                             for path in _CORPUS}
                py = {path: py_futs[path].result() for path in _CORPUS}
                port = {path: port_futs[path].result() for path in _CORPUS}
        tag = "" if optimization_level == 0 else f"-O{optimization_level} "
        for path in _CORPUS:
            with self.subTest(file=path.name):
                expected = py[path].splitlines()
                got = port[path].splitlines()
                for i, (e, gg) in enumerate(zip(expected, got)):
                    self.assertEqual(e, gg,
                                     f"{path.name}: {tag}C differs at line {i + 1}")
                self.assertEqual(len(expected), len(got),
                                 f"{path.name}: {tag}C length differs "
                                 f"(python {len(expected)}, port {len(got)})")


def _port_stream(target: Path) -> str:
    # Each part must END WITH A NEWLINE or the next "#FILE#" marker glues onto
    # the previous file's last line and the port misattributes that file's
    # statements (79 silently re-hashed names, found via the self-host diff).
    parts = [f"#FILE# {p.name}\n{_terminated(p)}" for p in _STDLIB]
    parts.append(f"#FILE# {target.name}\n{_terminated(target)}")
    return "".join(parts)


def _terminated(p: Path) -> str:
    text = p.read_text()
    return text if text.endswith("\n") else text + "\n"


def _run_port_c(binary: str, text: str, mode: str = "c") -> str:
    r = subprocess.run([binary, mode], input=text, capture_output=True,
                       timeout=600, text=True, env=_RUN_ENV)
    return r.stdout


def _python_c_text(target_name: str, optimization_level: int = 0) -> str:
    target = next(p for p in _CORPUS if p.name == target_name)
    statements = []
    for p in _STDLIB + [target]:
        result = parse(tokenize(p.read_text(), p.name))
        assert not result.errors, f"python parse errors in {p.name}"
        statements = statements + list(result.value)
    statements, _resolver, _passes = _CONVERGE(statements)
    statements = lowering.lambda_globals.lower_lambda_globals(statements)
    statements, dropped = lowering.drops.insert_drops(statements)
    if dropped:
        statements, _resolver, _p2 = _CONVERGE(statements)
    statements, poly_errors = lowering.generics.convert_generic_to_concrete(statements)
    if poly_errors:
        return "".join(f"{e}\n" for e in sorted(set(poly_errors)))
    unresolved = lowering.generics.report_unresolved_generic_calls(statements)
    if unresolved:
        return "".join(f"{e}\n" for e in sorted(set(unresolved)))
    statements, resolver3, _p3 = _CONVERGE(statements)
    statements = lowering.complex_enums.mark_complex_enums(statements)
    statements = lowering.constants.inline_constants(statements)
    statements = lowering.lambda_lift.lift_captured_calls(statements)
    statements = lowering.hoist_nested.hoist_nested_functions(statements)
    statements, tail_errors = lowering.tail_loop.lower_tail_loops(statements, resolver3)
    if tail_errors:
        return "".join(f"{e}\n" for e in sorted(set(tail_errors)))
    statements = lowering.ast_inline.inline_ast(statements, 1)
    statements = lowering.strings.fix_global_strings(statements)
    statements = lowering.integers.fix_global_integers(statements)
    fwd = lowering.lower_lazy_lets.check_lazy_forward_refs(statements)
    if fwd:
        return "".join(f"{e}\n" for e in sorted(set(fwd)))
    statements = lowering.lower_lazy_lets.lower_lazy_lets(statements)
    statements = lowering.lambdas.convert_lambdas_to_functions(statements)
    statements = lowering.simple_classes.lower_simple_classes(statements)
    statements = lowering.block_exits.assign_block_exits(statements)
    mains = [st for st in statements
             if isinstance(st, s.FunctionStatement) and _IS_MAIN(st)]
    if not mains:
        return "No main function found\n"
    discs = lowering.unions.collect_discriminator_ids(statements)
    return "".join(_CREATE_C(statements, mains[0], just_testing=True,
                             optimization_level=optimization_level,
                             union_discriminators=discs, headers=("yafl.h",)))
