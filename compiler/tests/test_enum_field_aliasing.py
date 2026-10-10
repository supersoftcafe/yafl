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

The runtime reads are [test]s in compiler/yafl_tests/enum_field_aliasing.yafl.
"""


from tests.testutil import TimedTestCase
from tests.testutil import compile_errors

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
    def test_unnarrowed_ambiguous_field_is_an_error(self):
        out = compile_errors(_AMBIGUOUS).lower()
        self.assertIn("nxt", out)
        self.assertIn("variant", out)
