"""A block whose VALUE is Convert(Block(...)) must flatten like value-of-block.

Statement-level inlining of a class CONSTRUCTOR at a `ret` in a UNION-returning
function produces exactly that shape: the ctor body block gets wrapped in the
union conversion. _flatten_block_values used to look only through a bare
nested block, so the inner block survived to codegen as the outer block's
VALUE — which generates with no `s{i}` prefix, letting the inner block's
statement paths collide with the outer's (SSA: "body/s1/expr/result defined
2 times"). Found compiling bootstrap/ast_inline.yafl at -O1.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture

_PROGRAM = """namespace Test
import System

# [tail]-recursive: excluded from the inline catalog, so its call sites keep
# their call temps (the colliding path needs a real temp at s1).
fun [tail] big(x: Int, acc: Int): Int
  if x <= 0
    ret acc
  ret big(x - 1, acc + x)

class Pair(pa: Int, pb: Int)

fun f(x: Int): Pair|None
  let u = big(x, 0)
  let v = big(u, 1)
  if v < 0
    ret None
  # The Pair ctor inlines here; the union return wraps its block in a
  # Convert. Inner statement paths must not collide with u/v's.
  ret Pair(big(v, 2), big(v, 3))

fun main(): Int
  ret match(f(3))
    (p: Pair) => p.pa == 255 && p.pb == 256 ? 0 : 1
    ()        => 2
"""


class TestInlineFlattenConvert(TestCase):
    _TIMEOUT = 300

    def test_ctor_inline_under_union_convert(self):
        # big(3,0)=6; big(6,1)=22; pa=big(22,2)=255; pb=big(22,3)=256.
        # The point is compiling at -O1 at all — the bug was an
        # SSAValidationError during codegen.
        code, _out = compile_and_run_stdlib_capture(_PROGRAM,
                                                    optimization_level=1)
        self.assertEqual(0, code)
