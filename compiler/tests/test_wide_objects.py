"""Objects wider than the 64-word pointer mask.

A vtable's pointer map used to be a single uint64 (one bit per word), so a
class whose pointer fields pass word 63 could not be described — clang died
with a shift-count overflow in `maskof`. The map is now windowed: the inline
word covers words 0..63 and `object_pointer_masks` extends it, so object
width is bounded only by `object_size` (uint16).

The test builds a 70-pointer-field class whose children are HEAP strings
(built at runtime — static literals would survive a broken mask), churns the
allocator hard enough for several collections, then re-reads every field.
A missed mask bit means unmarked children: collected, compacted over, or
poisoned — any of which fails the equality sweep."""
from __future__ import annotations

from tests.testutil import BatchedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib

N_FIELDS = 70


def _wide_src() -> str:
    fields = ", ".join(f"f{i}: String" for i in range(N_FIELDS))
    args = ", ".join(f"mk({i})" for i in range(N_FIELDS))
    checks = " && ".join(f'w.f{i} == mk({i})' for i in range(N_FIELDS))
    return f"""namespace Main
import System

class Wide({fields})

fun mk(i: Int): String
  ret "value-" + String(i * 7)

fun [tail] churn(n: Int, acc: Int): Int
  ret n == 0 ? acc : churn(n - 1, acc + length("x" + String(n)))

fun main(): System::Int
  let w = Wide({args})
  let g = churn(300000, 0)
  ret ({checks}) && g > 0 ? 0 : 1
"""


class TestWideObjects(TestCase):
    def test_wide_class_survives_gc(self):
        self.assertEqual(0, compile_and_run_stdlib(_wide_src()))
