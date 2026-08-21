"""`[hashed]`/`[refeq]` on FUNCTIONS — representation-aware caching.

Every BOXED enum carries a hidden `$hash: Int32` slot by default (no
annotation, no boxing force — the representation stays the compiler's
decision). A `[hashed]` function `(v: T): Int32` is wrapped: slot hit returns
it; miss computes, remaps 0 to 1, stores. A `[refeq]` function
`(l: T, r: T): Bool` gets the identity shortcut. On a VALUE-repr enum the
internals resolve to constants at codegen — no cache, no identity — and the
functions still compute correctly.
"""
from __future__ import annotations

import compiler as c
from tests.testutil import BatchedTestCase as TestCase
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

enum Tree
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

enum Tree
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

enum Box2
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

enum Z
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
    def test_hashed_fun_must_return_int32(self):
        src = """\
import System

enum H
  enum H1(v: System::Int)

fun [hashed] hHash(h: H): System::Int
  ret 1

fun main(): System::Int
  ret 0
"""
        diag = _diagnostics(src)
        self.assertIn("Int32", diag, diag)


class TestRefEq(TestCase):
    """`[refeq]` — the opt-in reference-equality shortcut (plan §3c). On a
    function `(l: T, r: T): Bool` over a [hashed] enum, the body is wrapped:
    same object returns true WITHOUT running the compare. Opt-in is the whole
    NaN answer: a non-reflexive equality simply does not opt in."""

    def test_same_object_skips_the_compare(self):
        src = """\
import System

enum Box2
  enum B2(v: System::Int)
  enum BLink(inner: Box2)

fun [refeq, impure] boxEq(l: Box2, r: Box2): System::Bool
  print("E")
  ret match(l)
    (x: B2) => match(r)
      (y: B2) => x.v == y.v
      (o: Box2) => false
    (bl: BLink) => false

fun main(): System::Int
  let p = B2(7)
  let q = B2(7)
  let sameObject   = boxEq(p, p)     # no compute
  let equalContent = boxEq(p, q)     # computes
  let different    = boxEq(p, B2(8)) # computes
  ret sameObject && equalContent && !different ? 0 : 1
"""
        code, out = compile_and_run_stdlib_capture(src, timeout=30)
        self.assertEqual(0, code, out)
        self.assertEqual("EE", out.strip(), out)   # two computes, not three

    def test_refeq_must_return_bool(self):
        src = """\
import System

enum H2
  enum H21(v: System::Int)

fun [refeq] hEq(l: H2, r: H2): System::Int
  ret 1

fun main(): System::Int
  ret 0
"""
        diag = _diagnostics(src)
        self.assertIn("Bool", diag, diag)
