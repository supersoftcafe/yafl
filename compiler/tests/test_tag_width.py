"""Union tag fields must be wide enough for their GLOBAL discriminator values.

compute_union_slots sized `$tag` by the union's own variant count (2 members
-> int8_t), but tagged combinations store globally-numbered discriminators —
in a program with >127 distinct union member types the stored value overflows
the comparison and clang (rightly, -Werror) rejects the generated C. Found
when the bootstrap compiler's enum count crossed the line.
"""
from tests.testutil import TimedTestCase, compile_and_run_stdlib


def _big_program() -> str:
    # 140 distinct two-field tuple types used as union members drive the
    # global discriminator numbering past 127.
    parts = ["namespace Main", "import System", ""]
    for i in range(140):
        parts.append(f"fun f{i}(n: System::Int): (a{i}: System::Int, b{i}: System::Int)|System::None")
        parts.append(f"  ret n > 0 ? (n, {i}) : None")
        parts.append("")
    for i in (0, 77, 139):
        parts.append(f"fun c{i}(): System::Int")
        parts.append(f"  ret match(f{i}(1))")
        parts.append(f"    (t: (a{i}: System::Int, b{i}: System::Int)) => t.a{i}")
        parts.append(f"    ()                                          => 0")
        parts.append("")
    parts.append("fun main(): System::Int")
    parts.append("  ret c0() + c77() + c139()")
    return "\n".join(parts) + "\n"


class TestTagWidth(TimedTestCase):
    _TIMEOUT = 240

    def test_wide_discriminators_compile_and_run(self):
        self.assertEqual(3, compile_and_run_stdlib(_big_program()))
