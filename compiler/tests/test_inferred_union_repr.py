"""A `match` used as an undeclared function's body must infer its return as the
JOIN of every arm — and that inferred type must be free to WIDEN across passes.

`closer` below infers its return from its arms: arm 1 (a nested match) yields
`A`, arm 2 yields `A | None`. The join is `A | None` — the type `use` declares
for its parameter. Two bugs conspired to infer just `A`: `match.get_type`
returned the FIRST arm's type, and undeclared-return inference used `refine`
(a meet) which, having seen `A` early (arm 2 resolves a pass later), can never
widen it to `A | None`. The wider arm's value was then stored into a too-narrow
`A` slot — C that clang rejects at -O2 ("assigning to struct_anon_N from
incompatible type ...").

Minimised from examples/raytracer.yafl, where `nearest`'s fold step `_closer`
had exactly this shape and broke the -O2 build.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib

_SRC = """\
namespace Main
import System

class A(v: System::Int)

fun mk(b: System::Bool): A | System::None => b ? A(1) : None

# Inferred return: arm 1 is `A | (A|None)`, arm 2 is `A|None` → together `A|None`.
fun closer(x: A | System::None, b: System::Bool) => match(x)
  (a: A) => match(mk(b))
    (a2: A)           => a2
    (n: System::None) => a
  (n: System::None) => mk(b)

fun use(x: A | System::None): System::Int => match(x)
  (a: A)            => a.v
  (n: System::None) => 0

fun main(): System::Int => use(closer(A(5), true))
"""


class TestInferredUnionRepr(TestCase):
    def test_inferred_nested_union_matches_declared(self):
        # closer(A(5), true) → A(1); use → 1. Must clang-compile and run to 1;
        # the bug made the generated C fail to compile at all.
        self.assertEqual(1, compile_and_run_stdlib(_SRC, optimization_level=2))
