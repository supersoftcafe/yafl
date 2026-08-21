"""A generic placeholder is a real type in its defining scope and a HOLE outside it.

Hole-ness is contextual: at the point a suggested type is used, a resolved generic
placeholder `N@hash` counts as a real type iff it resolves in the current scope,
and as a hole otherwise. So a call-site suggestion carries its generic parts only
into scopes where they mean something; its concrete parts travel everywhere.
"""
from __future__ import annotations

import contextlib
import io

import compiler as c
from tests.testutil import BatchedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


def _compile_capture(source: str) -> tuple[str, str]:
    """Compile with stdlib; return (c_code, captured diagnostics on stdout)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = c.compile([c.Input(source, "test.yafl")], use_stdlib=True, just_testing=False)
    return code, buf.getvalue()


# A nested function's un-annotated param is inferred from a call that passes the
# enclosing generic's `N`. `N` IS in scope where `doIt` is declared, so the
# suggestion `(N)` is kept and `doIt`'s `x` becomes `N` — `doIt(a)` returns `N`,
# `thingy` returns `N`.
_NESTED_KEEPS_GENERIC = """
namespace Test
import System

fun thingy<N>(a: N): N
  fun doIt(x) => x
  ret doIt(a)

fun main(): System::Int
  ret thingy<System::Int>(5)
"""


# A GLOBAL function called from a generic context with a generic arg AND a literal:
# the `27` pins `q = Int` (concrete part survives), but `a : N` is out of scope for
# the global `glob`, so its hint for `p` is a hole — `p` stays untyped and is
# reported. The point: the error is about `p`, NOT `q` — the concrete suggestion
# crossed the scope boundary, the generic one did not.
_GLOBAL_DROPS_GENERIC = """
namespace Test
import System

fun glob(p, q) => q

fun gen<N>(a: N): System::Int
  ret glob(a, 27)

fun main(): System::Int
  ret gen<System::Bool>(true)
"""


class TestContextualHoles(TestCase):
    def test_nested_param_keeps_enclosing_generic(self):
        rc, _out = compile_and_run_stdlib_capture(_NESTED_KEEPS_GENERIC, timeout=120)
        self.assertEqual(5, rc)

    def test_global_param_drops_out_of_scope_generic_keeps_concrete(self):
        # Compilation must fail naming `p` (its only hint, `N`, is a hole in the
        # global scope) but NOT `q` (the literal `27` pinned it to Int). The error
        # mentioning `p` and not `q` is the proof the concrete suggestion crossed
        # the scope boundary while the generic one did not.
        code, diagnostics = _compile_capture(_GLOBAL_DROPS_GENERIC)
        self.assertEqual("", code, "expected a compile error for the untyped 'p'")
        self.assertIn("'p'", diagnostics)
        self.assertNotIn("'q'", diagnostics)
