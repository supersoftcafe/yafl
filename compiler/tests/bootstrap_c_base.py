"""Shared fixture + corpus comparison for the bootstrap C-emission tests.

NOT a test module — the filename deliberately does not match `test*.py`, so
discovery skips it and the base class is not collected twice. The five
test_bootstrap_c_*.py modules each subclass this and contribute ONE test.

Split into separate MODULES rather than methods or classes because
unittest-parallel shards by module: as one module this was 24-37 minutes in
a single worker while the other four idled, and it set the floor for the
whole suite. --level=test would split it but does not preserve setUpClass;
--level=class cannot split a single-class module.

Original description follows.

bootstrap C emission — mode `c` must produce BYTE-IDENTICAL C to Python's
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
import lowering.instances
import lowering.hashed
import lowering.derive_eq
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
import lowering.linearity
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
_DIAGNOSE = c.__dict__["__collect_diagnostics"]
_CREATE_C = c.__dict__["__create_c_code"]
_IS_MAIN = c.__dict__["__is_main_function"]


class BootstrapCBase(TestCase):
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

    def _compare_corpus(self, optimization_level: int, mode: str,
                        profile: bool = False):
        # Every corpus file is independent, and per file the two compiles
        # are independent — a bounded pool takes BOTH job kinds (Python
        # mirrors need processes for the GIL; port runs are subprocess
        # wrappers), capped so memory stays sane. Results compare in corpus
        # order, so the first diff reported is always the simplest file's.
        # Under a parallel test runner this process is daemonic and cannot
        # fork a pool — compute serially instead.
        import multiprocessing
        if multiprocessing.current_process().daemon:
            py = {path: _python_c_text(path.name, optimization_level, profile)
                  for path in _CORPUS}
            port = {path: _run_port_c(self.binary, _port_stream(path), mode)
                    for path in _CORPUS}
        else:
            from concurrent.futures import ProcessPoolExecutor
            with ProcessPoolExecutor(max_workers=4) as pool:
                py_futs = {path: pool.submit(_python_c_text, path.name,
                                             optimization_level, profile)
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


def _python_c_text(target_name: str, optimization_level: int = 0,
                   profile: bool = False) -> str:
    from tests.testutil import cached_reference
    target = next(p for p in _CORPUS if p.name == target_name)
    return cached_reference("c", target.read_text(),
                            lambda: _python_c_text_uncached(target_name, optimization_level, profile),
                            extra=f"{target_name}|O{optimization_level}" + ("|p" if profile else ""))


def _python_c_text_uncached(target_name: str, optimization_level: int = 0,
                            profile: bool = False) -> str:
    target = next(p for p in _CORPUS if p.name == target_name)
    statements = []
    # Same canonical order as compiler.__tokenize_and_parse and the port's
    # parseMulti — this helper drives the pipeline directly, so it has to
    # impose the order itself.
    for p in sorted(_STDLIB + [target], key=lambda q: q.name):
        result = parse(tokenize(p.read_text(), p.name))
        assert not result.errors, f"python parse errors in {p.name}"
        statements = statements + list(result.value)
    statements, _resolver, _passes = _CONVERGE(statements)
    statements = lowering.lambda_globals.lower_lambda_globals(statements)
    statements, dropped = lowering.drops.insert_drops(statements)
    if dropped:
        statements, _resolver, _p2 = _CONVERGE(statements)
    # The CHECK PHASE, at compiler.py's position — after the drops
    # re-convergence, before derive_equality.
    #
    # This mirror used to telescope straight past it, and so did the port's C
    # path, so the two agreed by both skipping. They no longer can: the port
    # now runs diagnostics before emitting C (postmonoRes2's `gated`), which
    # is the whole point — a compiler that emits C for a program with an
    # undefined name is the worst failure class there is. Skipping it here
    # would compare two different pipelines.
    #
    # It bites on the corpus_converge files because they are self-contained
    # preludes — drop_balancing.yafl declares `namespace System` and its own
    # `typealias Int`, `+`, `true`, `false` — and this harness prepends the
    # real stdlib, so the combined program genuinely IS ambiguous. Both
    # compilers say so, identically (1879 diagnostics, verified equal); only
    # the old telescoping hid it.
    # sorted(set(errors)) over Error OBJECTS, exactly as compiler.py's
    # __print_errors does — Error is @dataclass(order=True), so this orders by
    # line_ref NUMERICALLY. Sorting the formatted strings instead puts
    # `[19:28]` before `[19:9]`, which is the same 1879 diagnostics in a
    # different order and diffs against the port on line 2.
    _failures, _warnings = _DIAGNOSE(statements, _resolver)
    # __collect_diagnostics always adds "No main function found", but the C
    # path reports a missing main SEPARATELY and in a different spelling — the
    # bare string returned below, which the port's cStage emits too. Drop it
    # here so both sides decide identically (the port passes requireMain=false
    # for the same reason). Python's rule then applies unchanged: a real error
    # prints ALL diagnostics, warnings included; warnings alone are not a
    # failure.
    _failures = [e for e in _failures if e.message != "No main function found"]
    if any(e.severity != "warning" for e in _failures):
        return "".join(f"{e}\n" for e in sorted(set(_failures)))
    _lin = lowering.linearity.check_linearity(statements, _resolver)
    if _lin:
        return "".join(f"{e}\n" for e in sorted(set(_lin)))
    # Derived enum equality, then the [hashed] split, as compiler.py does.
    statements, _derived = lowering.derive_eq.derive_equality(statements)
    if _derived:
        statements, _resolver, _pd = _CONVERGE(statements)
    # [hashed] split before instance lowering, as compiler.py does.
    statements, _herrs, _hchanged = lowering.hashed.lower_hashed(statements)
    if _herrs:
        return "".join(f"{e}\n" for e in sorted(set(str(x) for x in _herrs)))
    if _hchanged:
        statements, _resolver, _ph = _CONVERGE(statements)
    statements, lowered = lowering.instances.lower_trait_instances(statements)
    if lowered:
        statements, _resolver, _p2b = _CONVERGE(statements)
    statements, poly_errors = lowering.generics.convert_generic_to_concrete(statements)
    if poly_errors:
        return "".join(f"{e}\n" for e in sorted(set(poly_errors)))
    unresolved = lowering.generics.report_unresolved_generic_calls(statements)
    if unresolved:
        return "".join(f"{e}\n" for e in sorted(set(unresolved)))
    statements, resolver3, _p3 = _CONVERGE(statements)
    statements, _enum_ref_errors = lowering.complex_enums.mark_complex_enums(statements)
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
                             union_discriminators=discs, headers=("yafl.h",),
                             profile=profile))
