"""[mutable] classes, the write-once CAS, and System::memoize.

[mutable] says the collector must NOT relocate this object because fields are
published into it after construction. Two things have to hold or the whole
write-once scheme is unsound:

  * the vtable must carry is_mutable, so the collector leaves it alone;
  * the class must NOT be lowered to an unboxed struct, because there would be
    no object identity left to publish into.

The second is not theoretical: MemoRoot was silently flattened to a
`struct_anon_*` and the emitted C failed to compile against the CAS primitive.

System::memoize's behaviour is checked by compiler/yafl_tests/mutable.yafl.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_c


def _compile(content: str) -> str:
    return compile_c(content, "file.yafl", optimization_level=1)


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
