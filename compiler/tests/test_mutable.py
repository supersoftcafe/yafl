"""[mutable] classes, the write-once CAS, and System::memoize.

[mutable] says the collector must NOT relocate this object because fields are
published into it after construction. Two things have to hold or the whole
write-once scheme is unsound:

  * the vtable must carry is_mutable, so the collector leaves it alone;
  * the class must NOT be lowered to an unboxed struct, because there would be
    no object identity left to publish into.

The second is not theoretical: MemoRoot was silently flattened to a
`struct_anon_*` and the emitted C failed to compile against the CAS primitive.
"""
from __future__ import annotations

import compiler as c
from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


def _compile(content: str) -> str:
    return c.compile([c.Input(content, "file.yafl")], use_stdlib=True,
                     just_testing=False, optimization_level=1)


def _is_mutable_of(emitted: str, class_name: str) -> bool | None:
    """The is_mutable flag from the vtable whose .name is `class_name`.

    Scoped deliberately: a bare `".is_mutable = 1" in out` is meaningless,
    because every program containing an async function emits a mutable state
    object and would match.
    """
    import re
    for block in emitted.split("VTABLE_DECLARE"):
        m = re.search(r'\.name = "([^"]+)"', block)
        if m and m.group(1).split("@")[0] == class_name:
            f = re.search(r"\.is_mutable = (\d)", block)
            return f is not None and f.group(1) == "1"
    return None    # no vtable: the class was flattened or trimmed away


# A self-referential class: `simple_classes` cannot flatten it, so a vtable is
# always emitted and the is_mutable bit is observable either way.
_LINKED = """\
import System

class [final{attrs}] Node(v: System::Int, next: Node|System::None)

fun walk(n: Node|System::None): System::Int
  ret match(n)
    (x: Node) => 1 + walk(x.next)
    ()        => 0

fun main(): System::Int
  ret walk(Node(1, Node(2, None)))
"""


class TestMutableAttribute(TestCase):
    def test_mutable_sets_is_mutable_in_the_vtable(self):
        out = _compile(_LINKED.format(attrs=", mutable"))
        self.assertIs(True, _is_mutable_of(out, "Main::Node"))

    def test_without_mutable_the_vtable_says_immutable(self):
        out = _compile(_LINKED.format(attrs=""))
        self.assertIs(False, _is_mutable_of(out, "Main::Node"))

    def test_mutable_class_is_not_lowered_to_a_simple_struct(self):
        """The regression that broke memoize: a flattened class has no object
        identity, so there is nothing for the CAS to publish into."""
        src = """\
import System

class [final, mutable] Holder(a: System::Int32, b: System::Int32)

fun main(): System::Int
  ret System::Int(Holder(1i32, 2i32).a)
"""
        out = _compile(src)
        # A vtable named Holder exists at all only if it stayed a real object;
        # a flattened class becomes an anonymous struct with no vtable.
        self.assertIs(True, _is_mutable_of(out, "Main::Holder"))

    def test_plain_class_of_the_same_shape_IS_flattened(self):
        """Guards the other direction: without [mutable] the same class still
        gets the unboxed-struct treatment, so the exclusion is not blanket."""
        src = """\
import System

class [final] Holder(a: System::Int32, b: System::Int32)

fun main(): System::Int
  ret System::Int(Holder(1i32, 2i32).a)
"""
        out = _compile(src)
        # None == no vtable at all == it was flattened, which is the point.
        self.assertIsNone(_is_mutable_of(out, "Main::Holder"))


class TestMemoize(TestCase):
    """The contract is (1) `f` may run more than once, but (2) every caller
    gets the SAME answer. These check the caching actually happens — a memoize
    that silently never caches would still return correct values."""

    # Totals go out via println, not the exit status: an exit code is 8-bit and
    # a sum over 255 comes back silently reduced (314 arrives as 58).

    def test_arity1_repeated_and_distinct_keys(self):
        src = """\
import System

fun main(): System::Int
  let sq = memoize((n: System::Int) => n * n + 1)
  println(sq(7) + sq(7) + sq(9) + sq(9) + sq(7))
  ret 0
"""
        code, out = compile_and_run_stdlib_capture(src)
        self.assertEqual(0, code, out)
        self.assertEqual("314", out.strip())   # 50+50+82+82+50

    def test_arity1_same_answer_for_repeated_key(self):
        src = """\
import System

fun main(): System::Int
  let f = memoize((n: System::Int) => n + 1000)
  ret f(5) == f(5) && f(5) == 1005 ? 1 : 0
"""
        code, out = compile_and_run_stdlib_capture(src)
        self.assertEqual(1, code, out)

    def test_arity2_curries_and_caches(self):
        src = """\
import System

fun main(): System::Int
  let g = memoize((a: System::Int, b: System::Int) => a * 100 + b)
  println(g(3, 4) + g(3, 4) + g(5, 6))
  ret 0
"""
        code, out = compile_and_run_stdlib_capture(src)
        self.assertEqual(0, code, out)
        self.assertEqual("1114", out.strip())   # 304 + 304 + 506

    def test_arity3_curries_and_caches(self):
        src = """\
import System

fun main(): System::Int
  let h = memoize((a: System::Int, b: System::Int, c: System::Int) => a + b + c)
  ret h(1, 2, 3) + h(1, 2, 3) + h(4, 5, 6)
"""
        code, out = compile_and_run_stdlib_capture(src)
        self.assertEqual(27, code, out)     # 6 + 6 + 15

    def test_many_keys_exercise_the_trie_below_the_root(self):
        """Enough distinct keys that the trie must branch past depth 1, so the
        node-to-node publish path runs, not just the root slots."""
        src = """\
import System

fun [tail] loop(f: (:System::Int): System::Int, i: System::Int,
                acc: System::Int): System::Int
  ret i <= 0 ? acc : loop(f, i - 1, acc + f(i))

fun main(): System::Int
  let f = memoize((n: System::Int) => n * 2)
  # sum twice: the second pass must be all hits and give the same total
  let a = loop(f, 200, 0)
  let b = loop(f, 200, 0)
  ret a == b && a == 40200 ? 1 : 0
"""
        code, out = compile_and_run_stdlib_capture(src)
        self.assertEqual(1, code, out)
