"""Bool equality instance + Dict keys/values + String find.

Three stdlib gaps found porting the compiler to YAFL:
- `==`/`!=` on Bool had NO BasicEquality instance — and an undischargeable
  `where` reaches codegen as a crash (see memory: undischarged-where-crash),
  so `aBool != bBool` took the whole build down with no source pointer.
- Dict had no key/value iteration, forcing parallel key-lists on every user.
- String had findByte but no substring find.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture

_PROGRAM = """namespace Test
import System

fun boolChecks(): Int
  let t = true
  let f = false
  # ==, != and the derived operators all discharge BasicEquality<Bool> now.
  ret (t == t ? 1 : 0) + (t != f ? 10 : 0) + (f == t ? 100 : 0)

fun dictChecks(): Int
  let d = put(put(put(Dict<String, Int>(), "a", 1), "b", 2), "c", 3)
  let ks = keys(d)
  let vs = values(d)
  # Every key resolves through get, so the walk really visited the tree.
  fun [tail] sumVals(c: Chain<String>, acc: Int): Int
    ret match(c)
      (nil: ChainEnd) => acc
      (l: ChainLink)  => match(get(d, l.value))
        (v: Int) => sumVals(l.next, acc + v)
        ()       => sumVals(l.next, acc - 1000)
  ret chainLength(chain(ks)) * 100 + chainLength(chain(vs)) * 10
      + sumVals(chain(ks), 0)

fun findChecks(): Int
  let s = "the quick brown fox"
  ret (find(s, "quick") == 4 ? 1 : 0)
      + (find(s, "fox") == 16 ? 10 : 0)
      + (find(s, "wolf") == -1 ? 100 : 0)
      + (find(s, "o", 13) == 17 ? 1000 : 0)
      + (find(s, "") == 0 ? 10000 : 0)

fun main(): Int
  print(String(boolChecks()) + "|" + String(dictChecks()) + "|"
        + String(findChecks()) + "\\n")
  ret 0
"""


class TestStdlibAdditions(TestCase):
    _TIMEOUT = 300

    def test_bool_eq_dict_iteration_string_find(self):
        code, out = compile_and_run_stdlib_capture(_PROGRAM)
        self.assertEqual(0, code)
        self.assertEqual("11|336|11111\n", out)
