"""Two instantiations of one generic are two types — in a branch's union too.

A type's identity is its name plus ALL its type arguments. The union
machinery reads identity through `as_unique_id_str`, which used to spell a
generic class/enum by its ROOT alone: `List<Int>` and `List<String>` shared
one id, so a branch joining them deduped to whichever arm came FIRST. That
made branch typing order-dependent and lossy:

- `n > 0 ? List() : prepend("x", List())` settled on `List<T>` — List's own,
  out-of-scope parameter — and failed at monomorphisation, while the same
  function with its arms swapped compiled.
- `n > 0 ? prepend(1, List()) : prepend("hello", List())` settled on
  `List<Int>`, silently discarding the String arm; the binary read a String as
  an Int and aborted at runtime.

The second rule these tests pin: an arm whose type still holds a placeholder
that is not in scope (a generic call that bound nothing, like `List()`) is
only a SHAPE. When exactly one grounded sibling is an instantiation of that
shape, the arm is that sibling's type — whatever the arm order.
"""
from __future__ import annotations

import contextlib
import io

import compiler as c
import pyast.typespec as t
from parsing.tokenizer import LineRef
from tests.testutil import BatchedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


_lr = LineRef("f", 0, 0)
_INT = t.BuiltinSpec(_lr, "bigint")
_STR = t.BuiltinSpec(_lr, "str")
_LEAVES = ("System::ListEmpty@1", "System::ListFull@1")


def _list(arg: t.TypeSpec) -> t.EnumSpec:
    return t.EnumSpec(_lr, "System::List@1", frozenset(_LEAVES), _LEAVES, type_params=(arg,))


def _errors(src: str) -> tuple[str, str]:
    """(generated C, printed diagnostics) for a program expected to fail."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        c_code = c.compile([c.Input(src, "test.yafl")], use_stdlib=True, just_testing=True)
    return c_code, buf.getvalue()


class TestInstantiationIdentity(TestCase):
    def test_instantiations_have_distinct_ids(self):
        self.assertNotEqual(_list(_INT).as_unique_id_str(), _list(_STR).as_unique_id_str())

    def test_placeholder_argument_is_not_ground(self):
        # Not yet a type: its identity is unknown, exactly like a bare placeholder.
        self.assertIsNone(_list(t.GenericPlaceholderSpec(_lr, "T@1")).as_unique_id_str())

    def test_join_keeps_both_instantiations_in_either_order(self):
        for a, b in ((_list(_INT), _list(_STR)), (_list(_STR), _list(_INT))):
            joined = t.join(a, b)
            self.assertIsInstance(joined, t.CombinationSpec)
            self.assertEqual({_list(_INT), _list(_STR)}, set(joined.repr_members()))


class TestUnboundArmTakesItsSiblingsType(TestCase):
    def test_unbound_arm_first(self):
        rc, _ = compile_and_run_stdlib_capture("""
namespace Test
import System

fun pick(n: Int) => n > 0 ? List() : prepend("x", List())

fun main(): System::Int
  ret isEmpty(pick(1)) && !isEmpty(pick(0)) ? 7 : 3
""", timeout=120)
        self.assertEqual(7, rc)

    def test_unbound_arm_last(self):
        rc, _ = compile_and_run_stdlib_capture("""
namespace Test
import System

fun pick(n: Int) => n > 0 ? prepend("x", List()) : List()

fun main(): System::Int
  ret !isEmpty(pick(1)) && isEmpty(pick(0)) ? 7 : 3
""", timeout=120)
        self.assertEqual(7, rc)

    def test_unbound_arm_beside_recursive_call_and_local(self):
        # The port's llParallelGet shape: the grounded arm is a local binder's
        # field; the other arms are `List()` and the function's own recursion.
        rc, _ = compile_and_run_stdlib_capture("""
namespace Test
import System

fun [tail] pget(ns: Chain<String>, vs: Chain<List<String>>,
                name: String) => match(ns)
  (nil: ChainEnd) => List()
  (n: ChainLink)  => match(vs)
    (nil2: ChainEnd) => List()
    (v: ChainLink)   => n.value == name
      ? v.value
      : pget(n.next, v.next, name)

fun main(): System::Int
  let names = prepend("a", prepend("b", List<String>()))
  let values = prepend(List<String>(), prepend(prepend("hit", List<String>()), List<List<String>>()))
  ret !isEmpty(pget(chain(names), chain(values), "b"))
      && isEmpty(pget(chain(names), chain(values), "a"))
      && isEmpty(pget(chain(names), chain(values), "zz")) ? 7 : 3
""", timeout=120)
        self.assertEqual(7, rc)

    def test_arms_that_are_all_shapes_collapse(self):
        # The port's rpFlatten shape: `n`'s type is inferred from the body, so
        # on early passes EVERY arm is an unbound shape — `List<T>` of List,
        # prepend and concat. They are one partial type, not a union of holes
        # that no later answer could refine.
        rc, _ = compile_and_run_stdlib_capture("""
namespace Test
import System

enum Node
  enum Leaf(v: Int)
  enum Pair(l: Node, r: Node)

fun collect(n, keep: Bool) => match(n)
  (p: Pair)  => concat(collect(p.l, keep), collect(p.r, keep))
  (lf: Leaf) => keep ? prepend(n, List()) : List()

fun main(): System::Int
  let tree = Pair(Leaf(1), Pair(Leaf(2), Leaf(3)))
  ret !isEmpty(collect(tree, true)) && isEmpty(collect(tree, false)) ? 7 : 3
""", timeout=120)
        self.assertEqual(7, rc)

    def test_unbound_arm_beside_template_parameter(self):
        # Inside a generic, `List<U>` is a real type: the unbound arm fits it.
        rc, _ = compile_and_run_stdlib_capture("""
namespace Test
import System

fun orEmpty<U>(xs: List<U>, n: Int): List<U>
  let picked = n > 0 ? List() : xs
  ret picked

fun main(): System::Int
  let xs = prepend(1, List<Int>())
  ret isEmpty(orEmpty(xs, 1)) && !isEmpty(orEmpty(xs, 0)) ? 7 : 3
""", timeout=120)
        self.assertEqual(7, rc)


class TestDistinctInstantiationsStayDistinct(TestCase):
    def test_both_instantiations_reach_the_caller(self):
        # `List<Int> | List<String>` is an honest two-member union: each value
        # arrives as the instantiation it was built as.
        rc, _ = compile_and_run_stdlib_capture("""
namespace Test
import System

fun pick(n: Int) => n > 0 ? prepend(1, List()) : prepend("hello", List())

fun kind(v: List<Int>|List<String>): System::Int => match(v)
  (i: List<Int>)    => 1
  (s: List<String>) => 2

fun main(): System::Int
  ret kind(pick(1)) == 1 && kind(pick(0)) == 2 ? 7 : 3
""", timeout=120)
        self.assertEqual(7, rc)

    def test_union_of_instantiations_is_not_one_instantiation(self):
        # Used as a single List, the union is a compile error — never a binary
        # that reads a String as an Int.
        c_code, errs = _errors("""
namespace Test
import System

fun pick(n: Int) => n > 0 ? prepend(1, List()) : prepend("hello", List())

fun main(): System::Int
  let h = chainNext(chain(pick(0))).head
  ret match(h)
    (i: Int)  => i
    (z: None) => 7
""")
        self.assertEqual("", c_code)
        self.assertIn("test.yafl[8:21] - cannot infer the type arguments of generic function `chain`", errs)
