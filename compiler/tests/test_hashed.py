"""`[hashed]` — the compiler caches a structural hash in the value.

Two-part mechanism (docs/derived-equality-plan.md §3b):

  * `[hashed]` on an ENUM: every leaf object gains a hidden `$hash: Int32`
    slot directly after the vtable pointer — a fixed offset shared by all
    `[hashed]` types. The enum is forced complex (boxed): a by-value copy has
    nowhere to keep a cache. Does NOT imply [mutable]: a lost racy store is a
    benign recompute, and pinning the graph from compaction would be harmful.
  * `[hashed]` on a FUNCTION `(v: T): Int32`, T the hashed enum or a variant:
    the body is wrapped — slot hit returns it; miss computes, remaps 0 to 1,
    stores, returns.

The wrap is the ONLY door to the slot. No peek/store primitives are exposed,
so user code cannot observe the empty-versus-filled nondeterminism.
"""
from __future__ import annotations

import compiler as c
from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


def _diagnostics(content: str) -> str:
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        out = c.compile([c.Input(content, "file.yafl")], use_stdlib=True,
                        just_testing=False, optimization_level=0)
    return buf.getvalue() if not out else ""


_TREE = """\
import System

enum [hashed] Tree
  enum Leaf2(val: System::Int)
  enum Node2(left: Tree, right: Tree)

fun [hashed] treeHash(t: Tree): System::Int32
  ret match(t)
    (l: Leaf2) => hashOf(l.val)
    (n: Node2) => (treeHash(n.left) * 31i32 + treeHash(n.right)) & 2147483647i32
"""


class TestHashedCaching(TestCase):
    def test_hash_value_is_correct_and_stable(self):
        src = _TREE + """\

fun main(): System::Int
  let t = Node2(Leaf2(3), Leaf2(4))
  ret treeHash(t) == treeHash(t) && treeHash(t) >= 0i32 ? 1 : 0
"""
        code, out = compile_and_run_stdlib_capture(src, timeout=30)
        self.assertEqual(1, code, out)

    def test_compute_runs_once_per_object(self):
        """The point of the feature. The compute body prints; hashing the same
        object twice must compute once. The nested Leaf2 hashes are cached in
        THEIR slots on the first pass, so the second outer call touches no
        compute at all."""
        src = """\
import System

enum [hashed] Tree
  enum Leaf2(val: System::Int)
  enum Node2(left: Tree, right: Tree)

fun [hashed, impure] treeHash(t: Tree): System::Int32
  print("C")
  ret match(t)
    (l: Leaf2) => hashOf(l.val)
    (n: Node2) => (treeHash(n.left) * 31i32 + treeHash(n.right)) & 2147483647i32

fun main(): System::Int
  let t = Node2(Leaf2(3), Leaf2(4))
  let a = treeHash(t)
  let b = treeHash(t)
  ret a == b ? 0 : 1
"""
        code, out = compile_and_run_stdlib_capture(src, timeout=30)
        self.assertEqual(0, code, out)
        # 3 computes on the first call (node + two leaves), 0 on the second.
        self.assertEqual("CCC", out.strip(), out)

    def test_distinct_objects_cache_independently(self):
        src = """\
import System

enum [hashed] Box2
  enum B2(v: System::Int)

fun [hashed, impure] boxHash(b: Box2): System::Int32
  print("C")
  ret match(b)
    (x: B2) => hashOf(x.v)

fun main(): System::Int
  let p = B2(7)
  let q = B2(7)
  ret boxHash(p) == boxHash(q) ? 0 : 1
"""
        code, out = compile_and_run_stdlib_capture(src, timeout=30)
        self.assertEqual(0, code, out)
        self.assertEqual("CC", out.strip(), out)   # equal content, two slots

    def test_zero_hash_is_remapped_to_one(self):
        """0 is reserved for "not computed"; a compute returning 0 caches and
        returns 1, deterministically — the reservation String documents."""
        src = """\
import System

enum [hashed] Z
  enum Z0(v: System::Int)

fun [hashed] zHash(z: Z): System::Int32
  ret 0i32

fun main(): System::Int
  let z = Z0(1)
  ret zHash(z) == 1i32 && zHash(z) == 1i32 ? 1 : 0
"""
        code, out = compile_and_run_stdlib_capture(src, timeout=30)
        self.assertEqual(1, code, out)


class TestHashedValidation(TestCase):
    def test_hashed_class_is_rejected(self):
        src = """\
import System

class [final, hashed] P(a: System::Int)

fun main(): System::Int
  ret 0
"""
        diag = _diagnostics(src)
        self.assertIn("hashed", diag, diag)
        self.assertIn("enum", diag, diag)

    def test_hashed_fun_on_unhashed_type_is_rejected(self):
        src = """\
import System

enum Plain
  enum P1(v: System::Int)

fun [hashed] pHash(p: Plain): System::Int32
  ret 1i32

fun main(): System::Int
  ret 0
"""
        diag = _diagnostics(src)
        self.assertIn("hashed", diag, diag)

    def test_hashed_fun_must_return_int32(self):
        src = """\
import System

enum [hashed] H
  enum H1(v: System::Int)

fun [hashed] hHash(h: H): System::Int
  ret 1

fun main(): System::Int
  ret 0
"""
        diag = _diagnostics(src)
        self.assertIn("Int32", diag, diag)
