"""The `with` expression — copy-with-replacements, identity-preserving.

docs/preserving-rewrites-design.md, all rulings applied:

  * `with subject(name = value, …)` — call-shaped, not a call;
  * zero replacements is a CHECK error, not a parse error;
  * subjects are class- and enum-typed (ROOT included: the dynamic leaf is
    preserved, and names must be fields visible at the STATIC type);
  * the lowering returns the ORIGINAL object when every replacement is
    bit-identical to the current field ("SAME"), else a copy whose `$hash`
    slot is zeroed.

Identity preservation is unobservable by design, so the tests observe it
through the sanctioned doors: a `[refeq]` compare skips its compute for the
original-returned case, and `hashOf` must NOT serve a stale cache from a
copy.
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


class TestWithSemantics(TestCase):
    def test_class_subject_replaces_and_carries(self):
        src = """\
import System

class [final] P2(px: System::Int, py: System::Int)

fun main(): System::Int
  let a = P2(3, 4)
  let b = with a(py = 40)
  ret a.px == 3 && a.py == 4 && b.px == 3 && b.py == 40 ? 0 : 1
"""
        code, out = compile_and_run_stdlib_capture(src, timeout=30)
        self.assertEqual(0, code, out)

    def test_variant_subject(self):
        src = """\
import System

enum Tree3
  enum Leaf3(val: System::Int)
  enum Node3(left: Tree3, right: Tree3)

fun main(): System::Int
  ret match(Node3(Leaf3(1), Leaf3(2)))
    (n: Node3) => match(with n(right = Leaf3(9)))
      (m: Node3) => match(m.right)
        (l: Leaf3) => l.val == 9 ? 0 : 1
        (o: Tree3) => 2
    (o3: Tree3)  => 4
"""
        code, out = compile_and_run_stdlib_capture(src, timeout=30)
        self.assertEqual(0, code, out)

    def test_root_typed_subject_preserves_dynamic_leaf(self):
        """The ruling's own example: static type Colour, instance Green —
        the result must still BE a Green, with the covering field adjusted."""
        src = """\
import System

enum Colour3(shade: System::Int)
  enum Red3()
  enum Green3(glow: System::Int)

fun dim(c: Colour3): Colour3
  ret with c(shade = 1)

fun main(): System::Int
  ret match(dim(Green3(9, 7)))
    (g: Green3) => g.shade == 1 && g.glow == 7 ? 0 : 1
    (o: Colour3) => 2
"""
        code, out = compile_and_run_stdlib_capture(src, timeout=30)
        self.assertEqual(0, code, out)

    def test_unchanged_replacement_returns_the_original(self):
        """Observed through [refeq]: comparing the subject with a `with` whose
        replacement equals the current value must take the identity shortcut
        (no compute print) — the with returned the ORIGINAL object."""
        src = """\
import System

enum Box3
  enum B3(v: System::Int)
  enum BL3(inner: Box3)

fun [refeq, impure] boxEq(l: Box3, r: Box3): System::Bool
  print("E")
  ret match(l)
    (x: B3) => match(r)
      (y: B3) => x.v == y.v
      (o: Box3) => false
    (o2: Box3) => false

fun main(): System::Int
  ret match(B3(7))
    (b: B3) => boxEq(b, with b(v = b.v)) ? 0 : 1
    (o: Box3) => 2
"""
        code, out = compile_and_run_stdlib_capture(src, timeout=30)
        self.assertEqual(0, code, out)
        self.assertEqual("", out.strip(), out)   # no compute: same object

    def test_copy_does_not_serve_a_stale_hash(self):
        """The copy's `$hash` slot must be ZEROED: hash the original (fills
        its cache), then hash a changed copy — a stale cache would return the
        original's hash for different content."""
        src = """\
import System

enum H3
  enum H31(v: System::Int)
  enum H32(w: System::Int, x: H3)

fun [hashed] h3Hash(h: H3): System::Int32
  ret match(h)
    (a: H31) => hashOf(a.v)
    (b: H32) => (h3Hash(b.x) * 31i32 + hashOf(b.w)) & 2147483647i32

fun main(): System::Int
  ret match(H31(5))
    (a: H31) => h3Hash(a) != h3Hash(with a(v = 6)) ? 0 : 1
    (o: H3)  => 2
"""
        code, out = compile_and_run_stdlib_capture(src, timeout=30)
        self.assertEqual(0, code, out)


class TestWithValidation(TestCase):
    def test_zero_replacements_is_a_check_error(self):
        src = """\
import System

class [final] P2(px: System::Int)

fun main(): System::Int
  let a = P2(3)
  let b = with a()
  ret 0
"""
        diag = _diagnostics(src)
        self.assertIn("with", diag, diag or "COMPILED CLEAN")

    def test_unknown_field_is_rejected(self):
        src = """\
import System

class [final] P2(px: System::Int)

fun main(): System::Int
  let b = with P2(3)(nope = 1)
  ret 0
"""
        diag = _diagnostics(src)
        self.assertIn("nope", diag, diag or "COMPILED CLEAN")

    def test_subtype_field_invisible_at_root_type(self):
        """glow exists only on Green3; through a Colour3-typed subject it is
        not a visible field and must be rejected."""
        src = """\
import System

enum Colour3(shade: System::Int)
  enum Red3()
  enum Green3(glow: System::Int)

fun dim(c: Colour3): Colour3
  ret with c(glow = 1)

fun main(): System::Int
  ret 0
"""
        diag = _diagnostics(src)
        self.assertIn("glow", diag, diag or "COMPILED CLEAN")
