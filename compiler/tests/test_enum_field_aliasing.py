"""Same bare field name on DIFFERENT enum variants must read the right slot.

`DotExpression.compile` rewrites a bare field name to its @hash-unique form
by scanning the WHOLE enum's all_fields and taking the first bare-name match
— so `sv.nxt` inside a `(sv: Save)` arm resolved to Range's `nxt` and read
Range's slot. The narrowed subject type says exactly which variants are
possible; the lookup must prefer the field those variants actually declare,
and reading a name that several possible variants declare differently is a
compile error, not a silent garbage read. Found by the regex engine
(worked around there with rNext/sNext/aNext); a compiler-sized AST would
hit it constantly.
"""
import contextlib
import io

import compiler as c

from tests.testutil import TimedTestCase, compile_and_run_stdlib

_FLAT = """
namespace Main
import System

enum Inst
  enum Range(lo: System::Int32, hi: System::Int32, nxt: System::Int32)
  enum Save(slot: System::Int32, nxt: System::Int32)

fun main(): System::Int
  # Annotated at the ROOT: a bare construction is leaf-typed now, which
  # would make the else arms provably dead and the field reads unambiguous.
  let s: Inst = Save(0i32, 1i32)
  let r: Inst = Range(7i32, 8i32, 9i32)
  let a = match(s)
    (sv: Save) => System::Int(sv.nxt)
    ()         => 99
  let b = match(r)
    (rg: Range) => System::Int(rg.nxt)
    ()          => 99
  ret a * 10 + b
"""

# The recursive variant forces the complex (heap-object) representation,
# covering the other read_field implementation.
_COMPLEX = """
namespace Main
import System

enum Node
  enum Leaf(tag: System::Int, val: System::Int)
  enum Pair(val: System::Int, rest: Node)

fun main(): System::Int
  # Annotated at the ROOT (see _FLAT).
  let l: Node = Leaf(7, 3)
  let p: Node = Pair(4, l)
  let a = match(l)
    (lf: Leaf) => lf.val
    ()         => 99
  let b = match(p)
    (pr: Pair) => pr.val
    ()         => 99
  ret a * 10 + b
"""

_AMBIGUOUS = """
namespace Main
import System

enum Inst
  enum Range(lo: System::Int32, hi: System::Int32, nxt: System::Int32)
  enum Save(slot: System::Int32, nxt: System::Int32)

fun main(): System::Int
  # Annotated at the ROOT: un-narrowed, so both variants' differently-
  # positioned `nxt` fields stay in play — this cannot be a silent read of
  # either slot. (A bare construction is leaf-typed and reads its own
  # `nxt` legally.)
  let s: Inst = Save(0i32, 1i32)
  ret System::Int(s.nxt)
"""


class TestEnumFieldAliasing(TimedTestCase):
    def test_flat_enum_reads_own_variant_slot(self):
        self.assertEqual(19, compile_and_run_stdlib(_FLAT))

    def test_complex_enum_reads_own_variant_field(self):
        self.assertEqual(34, compile_and_run_stdlib(_COMPLEX))

    def test_unnarrowed_ambiguous_field_is_an_error(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            c.compile([c.Input(_AMBIGUOUS, "test.yafl")], use_stdlib=True, just_testing=True)
        out = buf.getvalue().lower()
        self.assertIn("nxt", out)
        self.assertIn("variant", out)
