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

Runtime behaviour is checked by compiler/yafl_tests/generic_instance_identity.yafl.
"""
from __future__ import annotations


import pyast.typespec as t
from parsing.tokenizer import LineRef
from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_c_result


_lr = LineRef("f", 0, 0)
_INT = t.BuiltinSpec(_lr, "bigint")
_STR = t.BuiltinSpec(_lr, "str")
_LEAVES = ("System::ListEmpty@1", "System::ListFull@1")


def _list(arg: t.TypeSpec) -> t.EnumSpec:
    return t.EnumSpec(_lr, "System::List@1", frozenset(_LEAVES), _LEAVES, type_params=(arg,))


def _errors(src: str) -> tuple[str, str]:
    """(generated C, printed diagnostics) for a program expected to fail."""
    r = compile_c_result(src)
    return r.c, r.stdout


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


class TestShapeFillsFromUnionMembers(TestCase):
    def test_shape_beside_a_union_takes_the_member_it_instantiates(self):
        # A branch's type is the SET union of its arms, so `List<T>` beside
        # `List<Int> | None` is `List<Int>` beside `List<Int>` and `None`.
        # Comparing whole arms only left the shape standing as a third
        # member, a hole the stored type then latched.
        import pyast.resolver as g
        free = t.GenericPlaceholderSpec(_lr, "T@free")
        unit = t.TupleSpec(_lr, ())
        sibling = t.CombinationSpec(_lr, (_list(_INT), unit))
        result = t.branch_type([_list(free), sibling], g.Resolver())
        self.assertEqual({_list(_INT), unit}, set(result.repr_members()))


class TestDistinctInstantiationsStayDistinct(TestCase):

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
