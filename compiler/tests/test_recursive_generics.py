"""Self-referential generics that a compiler-sized AST needs, pinned green.

These are the shapes the yaflc self-hosting assessment identified as
load-bearing: a generic enum containing collections of itself (the AST
shape), mutually recursive generic enums, a recursive generic class, and a
self-recursive generic function. Divergent POLYMORPHIC recursion is the one
self-referential shape that cannot work — tests/test_polymorphic_recursion.py
covers its error path.
"""
from tests.testutil import TimedTestCase, compile_and_run_stdlib


class TestRecursiveGenerics(TimedTestCase):
    def test_generic_enum_tree_with_list_of_self(self):
        # The AST shape: Tree<T> whose Node holds List<Tree<T>>, folded generically.
        self.assertEqual(7, compile_and_run_stdlib("""
namespace Main
import System

enum Tree<T>
  enum Leaf(v: T)
  enum Node(kids: List<Tree<T> >)

fun total(t: Tree<System::Int>): System::Int
  ret match(t)
    (lf: Leaf) => lf.v
    (nd: Node) => fold(nd.kids, 0, (acc: System::Int, k: Tree<System::Int>) => acc + total(k))

fun main(): System::Int
  let t = Node(prepend(Leaf(3), prepend(Node(prepend(Leaf(4), List<Tree<System::Int> >())), List<Tree<System::Int> >())))
  ret total(t)
"""))

    def test_mutually_recursive_generic_enums(self):
        self.assertEqual(1, compile_and_run_stdlib("""
namespace Main
import System

enum EvenL<T>
  enum ENil()
  enum ECons(ev: T, erest: OddL<T>)
enum OddL<T>
  enum OCons(ov: T, orest: EvenL<T>)

fun main(): System::Int
  let x = OCons(1, ECons(2, OCons(3, ENil())))
  ret match(x)
    (o: OCons) => o.ov
"""))

    def test_recursive_generic_class(self):
        self.assertEqual(11, compile_and_run_stdlib("""
namespace Main
import System

class [final] Box<T>(bv: T, bnext: Box<T>|System::None)

fun sumBoxes(b: Box<System::Int>|System::None): System::Int
  ret match(b)
    (x: Box<System::Int>) => x.bv + sumBoxes(x.bnext)
    ()                    => 0

fun main(): System::Int
  ret sumBoxes(Box(5, Box(6, None)))
"""))

    def test_self_recursive_generic_explicit_args(self):
        # Once crashed the compiler with a Python RecursionError (recorded in
        # the inference notes); pinned green.
        self.assertEqual(7, compile_and_run_stdlib("""
namespace Main
import System

fun loop<T>(x: T, n: System::Int): T
  ret n == 0 ? x : loop<T>(x, n - 1)

fun main(): System::Int
  ret loop<System::Int>(7, 3)
"""))

    def test_self_recursive_generic_function(self):
        self.assertEqual(2, compile_and_run_stdlib("""
namespace Main
import System

fun count<T>(l: List<T>): System::Int
  ret match(head(l))
    (x: T) => 1 + count(tail(l))
    ()     => 0

fun main(): System::Int
  ret count(prepend(5, prepend(6, List<System::Int>())))
"""))
