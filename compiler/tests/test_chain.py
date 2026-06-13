"""Chain<T> — the allocation-free consumption view of List<T>.

Covers: chain() ordering with pending appends (front AND rear populated —
the materialise-once path), the zero-copy path (no appends), chainNext
uncons, chainLength, and the List<T>(chain) round-trip.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


_SRC = """\
namespace Main
import System

# Walk a chain via chainNext, rendering "a.b.c." (short lists in this test,
# so plain recursion through the helper is fine).
fun render(c: Chain<String>, acc: String): String
  fun step(nx: (head: String|None, rest: Chain<String>), acc2: String): String
    ret match(nx.head)
      (h: String) => render(nx.rest, acc2 + h + ".")
      (e: None)   => acc2
  ret step(chainNext<String>(c), acc)

fun main(): System::Int
  # Mixed building: prepend then appends — front=[b] rear=[d,c] internally.
  let l0 = prepend<String>(b0(), List<String>())
  let l1 = append<String>(append<String>(l0, "c"), "d")
  let c1 = chain<String>(l1)
  System::print("mixed=[" + render(c1, "") + "] len=" + String(chainLength<String>(c1)) + "\\n")

  # Zero-copy path: built by prepends only (rear empty).
  let p = prepend<String>("x", prepend<String>("y", List<String>()))
  System::print("front=[" + render(chain<String>(p), "") + "]\\n")

  # Empty.
  System::print("empty=[" + render(chain<String>(List<String>()), "") + "] len=" + String(chainLength<String>(chain<String>(List<String>()))) + "\\n")

  # Round-trip: chain -> List -> normal list ops.
  let back = List<String>(c1)
  System::print("back=[" + fold<String, String>(back, "", (a: String, s: String) => a + s + ".") + "]\\n")
  ret 0

fun b0(): String
  ret "b"
"""


class Test(TestCase):
    def test_chain(self):
        code, out = compile_and_run_stdlib_capture(_SRC)
        self.assertEqual(0, code, out)
        self.assertIn("mixed=[b.c.d.] len=3", out)
        self.assertIn("front=[x.y.]", out)
        self.assertIn("empty=[] len=0", out)
        self.assertIn("back=[b.c.d.]", out)
