"""Namespace visibility (USER RULING 2026-08-23): referencing a declaration
in another namespace requires IMPORTING that namespace or using a FULLY
QUALIFIED name. In particular, declaring `namespace A` earlier in a file
must not make A's names visible to a later `namespace B` block in the same
file, and an `import` belongs to the namespace block it is written in.

The bug these tests pin: parser.py's fix-up pooled one file-wide
ImportGroup and converted every `namespace X` declaration into `import X`,
so every block saw every other block in the file (and all of its imports).
"""
from __future__ import annotations

import unittest

import compiler as c
from tests.testutil import compile_and_run_stdlib_capture


def _compiles(sources: "list[tuple[str, str]]") -> bool:
    out = c.compile([c.Input(text, name) for name, text in sources],
                    use_stdlib=True, just_testing=False)
    return bool(out)


class TestNamespaceScoping(unittest.TestCase):

    def test_same_file_cross_namespace_requires_import(self):
        # namespace B references namespace A's function unqualified with no
        # import: must FAIL to resolve even though A is declared in the same
        # file.
        src = """namespace NsProbeA
import System
fun nsHelperA(x: Int): Int
  ret x + 1
namespace NsProbeB
import System
fun main(): System::Int
  ret nsHelperA(1) - 2
"""
        self.assertFalse(_compiles([("ab.yafl", src)]),
                         "cross-namespace unqualified reference without an "
                         "import must not resolve (same file is not scope)")

    def test_import_grants_access(self):
        src = """namespace NsGrantA
import System
fun nsHelperB(x: Int): Int
  ret x + 1
namespace NsGrantB
import System
import NsGrantA
fun main(): System::Int
  ret nsHelperB(1) - 2
"""
        rc, _ = compile_and_run_stdlib_capture(src)
        self.assertEqual(0, rc, "an explicit import must grant access")

    def test_fully_qualified_needs_no_import(self):
        src = """namespace NsQualA
import System
fun nsHelperC(x: Int): Int
  ret x + 1
namespace NsQualB
import System
fun main(): System::Int
  ret NsQualA::nsHelperC(1) - 2
"""
        rc, _ = compile_and_run_stdlib_capture(src)
        self.assertEqual(0, rc, "a fully qualified reference needs no import")

    def test_import_scopes_to_its_own_block(self):
        # The first block imports System; the second block imports nothing,
        # so its unqualified use of println must fail — imports do not pool
        # per file. (System::Int in the signature is fully qualified, which
        # needs no import.)
        src = """namespace NsBlockA
import System
fun nsUseA(): Int
  println("a")
  ret 0
namespace NsBlockB
fun main(): System::Int
  println("b")
  ret 0
"""
        self.assertFalse(_compiles([("blocks.yafl", src)]),
                         "an import in one namespace block must not leak "
                         "into a later block")

    def test_ambiguity_between_imported_namespaces_is_an_error(self):
        # Both candidates genuinely in scope via imports: ambiguity stays an
        # error (no tie-breaks — USER RULING), unchanged by the scoping fix.
        src = """namespace NsAmbA
import System
fun nsClash(x: Int): Int
  ret x + 1
namespace NsAmbB
import System
fun nsClash(x: Int): Int
  ret x + 2
namespace NsAmbC
import System
import NsAmbA
import NsAmbB
fun main(): System::Int
  ret nsClash(1)
"""
        self.assertFalse(_compiles([("amb.yafl", src)]),
                         "two in-scope candidates must stay an ambiguity error")


if __name__ == "__main__":
    unittest.main()
