"""Same bare field name on DIFFERENT enum variants must read the right slot.

`DotExpression.compile` rewrites a bare field name to its @hash-unique form
by scanning the WHOLE enum's all_fields and taking the first bare-name match
— so `sv.nxt` inside a `(sv: Save)` arm resolved to Range's `nxt` and read
Range's slot. A value's members are the fields declared at its own level of
the enum or a parent level (#74): Save's `nxt` and Range's `nxt` are two
different fields, and neither is a member of the root. Found by the regex engine
(worked around there with rNext/sNext/aNext); a compiler-sized AST would
hit it constantly.

The runtime reads are [test]s in compiler/yafl_tests/enum_field_aliasing.yafl.
"""


from tests.testutil import TimedTestCase
from tests.testutil import compile_errors

_ROOT_READ = """
namespace Main
import System

enum Inst
  enum Range(lo: System::Int32, hi: System::Int32, nxt: System::Int32)
  enum Save(slot: System::Int32, nxt: System::Int32)

fun main(): System::Int
  # Annotated at the ROOT: `nxt` is declared on the variants, not on Inst,
  # so it is no member here. (A bare construction is leaf-typed and reads
  # its own `nxt` legally.)
  let s: Inst = Save(0i32, 1i32)
  ret System::Int(s.nxt)
"""


class TestEnumFieldAliasing(TimedTestCase):
    def test_a_variant_field_is_not_a_member_of_the_root(self):
        out = compile_errors(_ROOT_READ).lower()
        self.assertIn("could not find field nxt", out)
