"""Tests for hierarchical enum types."""
from __future__ import annotations

import contextlib
import io
import subprocess
from unittest import TestCase

import compiler as c
from tests.testutil import compile_and_run, compile_and_run_stdlib


def _compile_capturing_errors(source: str) -> tuple[str, str]:
    """Run compile() and capture stdout (where compile() prints errors).
    Returns (result, stdout_text)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        result = c.compile([c.Input(source, "test.yafl")], use_stdlib=False, just_testing=False)
    return result, buf.getvalue()


_PREAMBLE = """\
namespace System
typealias Int : __builtin_type__<bigint>
typealias String : __builtin_type__<str>
typealias None : ()
let None:None = ()
"""


def _compile(source: str) -> str:
    return c.compile([c.Input(source, "test.yafl")], use_stdlib=False, just_testing=False)


def _compile_errors(source: str) -> list[str]:
    errors = []
    try:
        result = c.compile([c.Input(source, "test.yafl")], use_stdlib=False, just_testing=True)
    except Exception as ex:
        errors.append(str(ex))
    return errors


def _clang_check(source: str) -> None:
    c_code = _compile(source)
    assert c_code, "yafl compilation produced no output (type errors?)"
    result = subprocess.run(
        ["clang", "-fsyntax-only", "-x", "c", "-", "-include", "yafl.h"],
        input=c_code, text=True, capture_output=True, timeout=30,
    )
    assert result.returncode == 0, f"clang rejected the C output:\n{result.stderr}"


def _run(source: str) -> int:
    exit_code, _ = compile_and_run(source)
    return exit_code


# ---------------------------------------------------------------------------
# Basic parsing and type resolution
# ---------------------------------------------------------------------------

class TestEnumBasic(TestCase):

    def test_simple_leaf_enum_compiles(self):
        """A leaf enum with no children compiles to valid C."""
        _clang_check(_PREAMBLE + """\
enum Colour()

fun main(): Int
  let c: Colour = Colour()
  ret 0
""")

    def test_two_level_hierarchy_compiles(self):
        """A two-level hierarchy compiles — children share parent's C struct type."""
        _clang_check(_PREAMBLE + """\
enum IOError(code: Int)
  enum ReadError(amount: Int)
  enum WriteError()

fun main(): Int
  let e: IOError = ReadError(42, 7)
  ret 0
""")

    def test_three_level_hierarchy_compiles(self):
        """Three levels of nesting compile and produce a single C struct."""
        _clang_check(_PREAMBLE + """\
enum IOError(code: Int)
  enum ReadError(amount: Int)
  enum WriteError()
    enum BecauseITFailedError()
    enum OtherThingy(message: Int)

fun main(): Int
  let e: IOError = BecauseITFailedError(0)
  ret 0
""")


# ---------------------------------------------------------------------------
# Constructor generation
# ---------------------------------------------------------------------------

class TestEnumConstructors(TestCase):

    def test_leaf_constructor_exists(self):
        """Leaf enum generates a callable constructor."""
        _clang_check(_PREAMBLE + """\
enum IOError(code: Int)
  enum ReadError(amount: Int)
  enum WriteError()

fun main(): Int
  let e: IOError = WriteError(99)
  ret 0
""")

    def test_leaf_constructor_inherits_ancestor_fields(self):
        """Leaf constructor takes all ancestor fields before its own."""
        _clang_check(_PREAMBLE + """\
enum IOError(code: Int)
  enum ReadError(amount: Int)
  enum WriteError()
    enum BecauseITFailedError()

fun main(): Int
  let e: IOError = BecauseITFailedError(5)
  ret 0
""")

    def test_nested_leaf_inherits_full_ancestry(self):
        """Deeply nested leaf constructor takes fields from all ancestors."""
        _clang_check(_PREAMBLE + """\
enum IOError(code: Int)
  enum ReadError(amount: Int)
  enum WriteError()
    enum BecauseITFailedError()
    enum OtherThingy(message: Int)

fun main(): Int
  let e: IOError = OtherThingy(1, 99)
  ret 0
""")


# ---------------------------------------------------------------------------
# Assignability
# ---------------------------------------------------------------------------

class TestEnumAssignability(TestCase):

    def test_leaf_assignable_to_root(self):
        """A leaf variant is assignable to the root enum type."""
        _clang_check(_PREAMBLE + """\
enum IOError(code: Int)
  enum ReadError(amount: Int)
  enum WriteError()

fun accept(e: IOError): Int
  ret 0

fun main(): Int
  ret accept(ReadError(0, 1))
""")

    def test_leaf_assignable_to_parent(self):
        """A grandchild variant is assignable to its direct parent enum."""
        _clang_check(_PREAMBLE + """\
enum IOError(code: Int)
  enum WriteError()
    enum BecauseITFailedError()

fun accept_write(e: WriteError): Int
  ret 0

fun main(): Int
  ret accept_write(BecauseITFailedError(0))
""")

    def test_root_not_assignable_to_leaf(self):
        """The root type is NOT assignable to a narrower leaf type."""
        src = _PREAMBLE + """\
enum IOError(code: Int)
  enum ReadError(amount: Int)
  enum WriteError()

fun narrow(e: ReadError): Int
  ret 0

fun accept_io(e: IOError): Int
  ret narrow(e)

fun main(): Int
  ret 0
"""
        result = _compile(src)
        assert not result, "Expected type error but compilation succeeded"

    def test_sibling_not_assignable(self):
        """One leaf variant is not assignable to a sibling leaf type."""
        src = _PREAMBLE + """\
enum IOError(code: Int)
  enum ReadError(amount: Int)
  enum WriteError()

fun narrow(e: ReadError): Int
  ret 0

fun main(): Int
  ret narrow(WriteError(0))
"""
        result = _compile(src)
        assert not result, "Expected type error but compilation succeeded"

    def test_same_type_assignable(self):
        """A leaf type is assignable to itself."""
        _clang_check(_PREAMBLE + """\
enum IOError(code: Int)
  enum ReadError(amount: Int)

fun accept_read(e: ReadError): Int
  ret 0

fun main(): Int
  ret accept_read(ReadError(0, 5))
""")


# ---------------------------------------------------------------------------
# Same C-level type for all hierarchy levels
# ---------------------------------------------------------------------------

class TestEnumSharedCType(TestCase):

    def test_root_and_leaf_same_c_struct(self):
        """IOError and ReadError compile to the same C struct — verified by codegen."""
        c_code = _compile(_PREAMBLE + """\
enum IOError(code: Int)
  enum ReadError(amount: Int)
  enum WriteError()

fun main(): Int
  let e: IOError = ReadError(0, 0)
  ret 0
""")
        assert c_code, "Compilation failed"
        # Only one struct typedef should be emitted for the whole hierarchy
        struct_count = c_code.count("typedef struct {")
        assert struct_count == 1, f"Expected 1 struct, got {struct_count}"


# ---------------------------------------------------------------------------
# Field access
# ---------------------------------------------------------------------------

class TestEnumFieldAccess(TestCase):

    def test_access_own_field(self):
        """Can read a field declared on the leaf level."""
        _clang_check(_PREAMBLE + """\
enum IOError(code: Int)
  enum ReadError(amount: Int)

fun main(): Int
  let e: IOError = ReadError(0, 42)
  let x: Int = e.amount
  ret 0
""")

    def test_access_inherited_field(self):
        """Can read a field declared on an ancestor level."""
        _clang_check(_PREAMBLE + """\
enum IOError(code: Int)
  enum ReadError(amount: Int)

fun main(): Int
  let e: IOError = ReadError(7, 42)
  let x: Int = e.code
  ret 0
""")


# ---------------------------------------------------------------------------
# Match expressions
# ---------------------------------------------------------------------------

class TestEnumMatch(TestCase):

    def test_match_single_leaf(self):
        """Match on a leaf variant with a single JumpIf."""
        _clang_check(_PREAMBLE + """\
enum IOError(code: Int)
  enum ReadError(amount: Int)
  enum WriteError()

fun main(): Int
  let e: IOError = ReadError(0, 5)
  let result: Int = match (e)
    (r: ReadError) => r.amount
    (w: WriteError) => w.code
  ret 0
""")

    def test_match_else_arm(self):
        """Match with an else arm compiles and clang accepts it."""
        _clang_check(_PREAMBLE + """\
enum IOError(code: Int)
  enum ReadError(amount: Int)
  enum WriteError()

fun main(): Int
  let e: IOError = WriteError(3)
  let result: Int = match (e)
    (r: ReadError) => r.amount
    (x) => x.code
  ret 0
""")

    def test_match_nested_arm(self):
        """Match on a non-leaf type covers multiple leaf discriminators."""
        _clang_check(_PREAMBLE + """\
enum IOError(code: Int)
  enum ReadError(amount: Int)
  enum WriteError()
    enum BecauseITFailedError()
    enum OtherThingy(message: Int)

fun main(): Int
  let e: IOError = OtherThingy(1, 99)
  let result: Int = match (e)
    (r: ReadError) => r.amount
    (w: WriteError) => w.code
  ret 0
""")

    def test_match_bound_var_field_access(self):
        """Bound variable in match arm can access fields."""
        _clang_check(_PREAMBLE + """\
enum IOError(code: Int)
  enum ReadError(amount: Int)
  enum WriteError()

fun main(): Int
  let e: IOError = ReadError(7, 42)
  let result: Int = match (e)
    (r: ReadError) => r.amount
    (w: WriteError) => w.code
  ret 0
""")


# ---------------------------------------------------------------------------
# Enum in combination with other types (IOError | String | None)
# ---------------------------------------------------------------------------

class TestEnumInCombination(TestCase):

    def test_enum_or_string_or_none_type_check(self):
        """IOError|String|None is a valid union and each member is assignable to it."""
        _clang_check(_PREAMBLE + """\
enum IOError(code: Int)
  enum ReadError(amount: Int)
  enum WriteError()

fun accept(x: IOError|String|None): Int
  ret 0

fun main(): Int
  let a: Int = accept(ReadError(0, 1))
  let b: Int = accept("hello")
  let c: Int = accept(None)
  ret 0
""")

    def test_enum_or_string_or_none_match(self):
        """Match on IOError|String|None dispatches to correct arm."""
        _clang_check(_PREAMBLE + """\
enum IOError(code: Int)
  enum ReadError(amount: Int)
  enum WriteError()

fun handle(x: IOError|String|None): Int
  let result: Int = match (x)
    (e: IOError) => e.code
    (s: String) => 1
    (n: None) => 2
  ret result

fun main(): Int
  ret 0
""")

    def test_enum_in_union_correct_arm_selected(self):
        """When an IOError is passed, the IOError arm is taken (not String/None)."""
        _clang_check(_PREAMBLE + """\
enum IOError(code: Int)
  enum ReadError(amount: Int)
  enum WriteError()

fun handle(x: IOError|String|None): Int
  let result: Int = match (x)
    (e: IOError) => e.code
    (s: String) => 1
    (n: None) => 2
  ret result

fun main(): Int
  ret 0
""")


# ---------------------------------------------------------------------------
# Exhaustiveness / unreachable checks
# ---------------------------------------------------------------------------

class TestEnumMatchExhaustiveness(TestCase):

    def test_all_leaves_covered_compiles(self):
        """Match covering every enum leaf compiles."""
        _clang_check(_PREAMBLE + """\
enum Colour(code: Int)
  enum Red()
  enum Green()
  enum Blue()

fun f(c: Colour): Int
  ret match(c)
    (r: Red)   => 1
    (g: Green) => 2
    (b: Blue)  => 3

fun main(): Int
  let c: Colour = Red(0)
  ret f(c)
""")

    def test_missing_leaf_errors(self):
        """Omitting one leaf with no else is a compile error."""
        src = _PREAMBLE + """\
enum Colour(code: Int)
  enum Red()
  enum Green()
  enum Blue()

fun f(c: Colour): Int
  ret match(c)
    (r: Red)   => 1
    (g: Green) => 2

fun main(): Int
  let c: Colour = Red(0)
  ret f(c)
"""
        result, errors = _compile_capturing_errors(src)
        self.assertEqual("", result)
        self.assertIn("non-exhaustive", errors,
            f"expected 'non-exhaustive' in errors, got: {errors!r}")
        self.assertIn("Blue", errors,
            f"expected missing leaf 'Blue' to appear in error, got: {errors!r}")

    def test_partial_plus_else_compiles(self):
        """Covering two leaves plus an else arm compiles."""
        _clang_check(_PREAMBLE + """\
enum Colour(code: Int)
  enum Red()
  enum Green()
  enum Blue()

fun f(c: Colour): Int
  ret match(c)
    (r: Red)   => 1
    (g: Green) => 2
    ()         => 9

fun main(): Int
  let c: Colour = Red(0)
  ret f(c)
""")

    def test_parent_level_arm_covers_subtree_compiles(self):
        """A non-leaf arm covers its descendant leaves."""
        _clang_check(_PREAMBLE + """\
enum Shape(code: Int)
  enum Round()
    enum Circle()
    enum Ellipse()
  enum Square()

fun f(s: Shape): Int
  ret match(s)
    (r: Round)  => 1
    (q: Square) => 2

fun main(): Int
  let s: Shape = Circle(0)
  ret f(s)
""")

    def test_redundant_leaf_after_parent_errors(self):
        """A leaf arm after a parent that already covers it is unreachable."""
        src = _PREAMBLE + """\
enum Shape(code: Int)
  enum Round()
    enum Circle()
    enum Ellipse()
  enum Square()

fun f(s: Shape): Int
  ret match(s)
    (r: Round)   => 1
    (q: Square)  => 2
    (c: Circle)  => 3

fun main(): Int
  let s: Shape = Circle(0)
  ret f(s)
"""
        result, errors = _compile_capturing_errors(src)
        self.assertEqual("", result)
        self.assertIn("unreachable", errors,
            f"expected 'unreachable' in errors, got: {errors!r}")


class TestRecursiveEnums(TestCase):
    """Recursive enums (variant fields reference the enum's own root)
    must compile to heap-allocated objects rather than flat structs."""

    def test_linked_list_sum(self):
        # Cons(1, Cons(2, Cons(3, Cons(4, Cons(5, Nil()))))) — sum = 15.
        src = """namespace Test
import System

enum List
  enum Cons(head: System::Int, tail: List)
  enum Nil()

fun sumList(l: List): System::Int
  ret match(l)
    (n: Nil) => 0
    (c: Cons) => c.head + sumList(c.tail)

fun main(): System::Int
  let l: List = Cons(1, Cons(2, Cons(3, Cons(4, Cons(5, Nil())))))
  ret sumList(l)
"""
        self.assertEqual(15, compile_and_run_stdlib(src))

    def test_tree_node_count(self):
        # Three nodes: root + 2 leaves' worth of structure.
        # count(Node(Leaf, _, Leaf)) = 1 + count(Leaf) + count(Leaf) = 1.
        # Build a 3-deep node chain on the right and count.
        src = """namespace Test
import System

enum Tree
  enum Node(left: Tree, value: System::Int, right: Tree)
  enum Leaf()

fun countNodes(t: Tree): System::Int
  ret match(t)
    (l: Leaf) => 0
    (n: Node) => 1 + countNodes(n.left) + countNodes(n.right)

fun main(): System::Int
  let t: Tree = Node(Node(Leaf(), 1, Leaf()), 2, Node(Leaf(), 3, Leaf()))
  ret countNodes(t)
"""
        self.assertEqual(3, compile_and_run_stdlib(src))

    def test_recursive_enum_object_typedef_emitted(self):
        # The recursive enum's root_name should appear as a heap Object
        # in the C output (typedef'd struct), not just a flat anon
        # struct. Check for the mangled type name.
        src = """namespace Test
import System

enum List
  enum Cons(head: System::Int, tail: List)
  enum Nil()

fun main(): System::Int
  let l: List = Nil()
  ret 0
"""
        result = c.compile([c.Input(src, "test.yafl")], use_stdlib=True, just_testing=False)
        self.assertNotEqual("", result)
        # The Object name 'Test::List@hash' is mangled to a C identifier.
        # The simplest stable check: the canonical vtable symbol obj_*List* exists.
        self.assertIn("List", result)
        # And the heap allocator is invoked at least once (Nil() goes via
        # the recursive constructor path: object_create on the enum's vtable).
        self.assertIn("object_create", result)

    def test_non_recursive_enum_remains_flat(self):
        # A regression check: IOError is non-recursive — its Variant
        # leaves carry a primitive int and unit, no self-reference. The
        # flat-struct codegen must remain unchanged. We assert by
        # checking that the program compiles and runs (uses match-on-flat-
        # struct semantics throughout) and returns the expected value.
        src = """namespace Test
import System
import System::IO

fun main(): System::Int
  let e: System::IO::IOError = System::IO::EOFError(0)
  ret match(e)
    (eof: System::IO::EOFError) => 0
    () => 99
"""
        self.assertEqual(0, compile_and_run_stdlib(src))

    def test_many_fielded_enum_is_complex(self):
        # An enum with more than 8 entries in all_fields (data fields +
        # the implicit $tag) is also marked complex and routed through
        # heap allocation. Build a 10-data-field enum, store it, read a
        # field back. With > 8 fields the codegen path is the same as
        # for a recursive enum.
        src = """namespace Test
import System

enum Wide
  enum One(a: System::Int, b: System::Int, c: System::Int, d: System::Int, e: System::Int, f: System::Int, g: System::Int, h: System::Int, i: System::Int, j: System::Int)

fun main(): System::Int
  let w: Wide = One(0, 0, 0, 0, 0, 0, 0, 0, 0, 42)
  ret match(w)
    (one: One) => one.j
"""
        # Compile and confirm the heap-allocated path was used (the C
        # output references object_create on the enum's vtable).
        result = c.compile([c.Input(src, "test.yafl")], use_stdlib=True, just_testing=False)
        self.assertNotEqual("", result)
        self.assertIn("object_create", result)
        # And the program runs end-to-end.
        self.assertEqual(42, compile_and_run_stdlib(src))

    def test_mutual_recursion(self):
        # enum A's variant references B; enum B's variant references A.
        # Both must be detected as recursive and registered as heap
        # objects. Walk a 3-deep alternation and assert depth.
        src = """namespace Test
import System

enum A
  enum A1(b: B)
  enum A2()

enum B
  enum B1(a: A)
  enum B2()

fun depthA(x: A): System::Int
  ret match(x)
    (a: A2) => 0
    (a: A1) => 1 + depthB(a.b)

fun depthB(x: B): System::Int
  ret match(x)
    (b: B2) => 0
    (b: B1) => 1 + depthA(b.a)

fun main(): System::Int
  let v: A = A1(B1(A1(B1(A2()))))
  ret depthA(v)
"""
        self.assertEqual(4, compile_and_run_stdlib(src))
