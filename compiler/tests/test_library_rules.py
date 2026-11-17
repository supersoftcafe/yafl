"""The rules that let each library converge as a layer of its own (#136).

A library is settled before anything above it compiles, so nothing above it
may change how it compiles:

  1. NAMESPACE OWNERSHIP — a library declares only into the namespaces its
     manifest lists, and a program declares into none that a library lists.
  2. NO ORPHAN INSTANCES — Rust's rule: an `instance` of `Iface<T1..Tn>` must
     own the interface, or some Ti whose OUTERMOST type is its own with no
     bare type parameter before it. "Own" is by namespace: a library owns its
     manifest's namespaces, a program every namespace no library lists.
  3. NO CYCLES — libraries that depend on each other could never converge
     one before the other.

Every case runs on BOTH compilers: the rules are the language, not one
implementation's.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_c_result, python_compiler_command, port_compiler_command


def _library(root: Path, name: str, namespaces: list[str], source: str) -> None:
    lib = root / name
    lib.mkdir()
    listed = ", ".join(f'"{ns}"' for ns in namespaces)
    (lib / "yafl.toml").write_text(f'name = "{name}"\nnamespaces = [{listed}]\n')
    (lib / f"{name}.yafl").write_text(source)


class TestLibraryRules(TestCase):
    _TIMEOUT = 600

    def _compile(self, program: str, libraries=()):
        """(compiler label, Compiled) for each compiler, the libraries on -L."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for name, namespaces, source in libraries:
                _library(root, name, namespaces, source)
            return [(label, compile_c_result(program, "prog.yafl", command=command,
                                             args=["-L", str(root)]))
                    for label, command in (("python", python_compiler_command()),
                                           ("port", port_compiler_command()))]

    def _rejected(self, program: str, message: str, libraries=()):
        for label, r in self._compile(program, libraries):
            with self.subTest(compiler=label):
                self.assertTrue(not r.c, f"{label}: compiled, but should not have")
                self.assertIn(message, r.stdout)

    def _accepted(self, program: str, libraries=()):
        for label, r in self._compile(program, libraries):
            with self.subTest(compiler=label):
                self.assertTrue(r.c, f"{label}: rejected:\n{r.stdout}")

    # ── rule 1: namespace ownership ─────────────────────────────────────────

    def test_library_declares_outside_its_manifest(self):
        acme = ("namespace Acme\nfun one(): System::Int => 1\n"
                "namespace Elsewhere\nfun two(): System::Int => 2\n")
        self._rejected("fun main(): System::Int => Acme::one()\n",
                       "'Elsewhere' is not a namespace of library 'acme'",
                       [("acme", ["Acme"], acme)])

    def test_program_declares_into_a_library_namespace(self):
        self._rejected("namespace System\nfun mine(): Int => 1\n"
                       "namespace Main\nfun main(): System::Int => System::mine()\n",
                       "namespace 'System' belongs to library 'system'")

    # ── rule 3: no cycles ───────────────────────────────────────────────────

    def test_libraries_that_depend_on_each_other(self):
        self._rejected("fun main(): System::Int => Alpha::a()\n",
                       "libraries depend on each other: alpha, beta",
                       [("alpha", ["Alpha"], "namespace Alpha\nfun a(): System::Int => Beta::b()\n"
                                             "fun c(): System::Int => 3\n"),
                        ("beta", ["Beta"], "namespace Beta\nfun b(): System::Int => Alpha::c()\n")])

    # ── rule 2: no orphan instances ─────────────────────────────────────────

    def test_instance_of_a_foreign_interface_for_a_foreign_type(self):
        self._rejected("namespace Main\nimport System\n"
                       "instance [ambient] Show<Int>\n  fun show(value: Int): String => \"int\"\n"
                       "fun main(): Int => 0\n",
                       "orphan instance of 'System::Show': the program owns neither "
                       "the interface nor the type it is implemented for")

    def test_own_type_inside_a_foreign_one_does_not_count(self):
        self._rejected("namespace Main\nimport System\nimport System::Containers\n"
                       "class Mine(v: Int)\n"
                       "instance [ambient] Show<List<Mine>>\n"
                       "  fun show(value: List<Mine>): String => \"mine\"\n"
                       "fun main(): Int => 0\n",
                       "orphan instance of 'System::Show'")

    # A foreign interface with two type arguments, for the ORDER rule.
    _PAIR = ("acme", ["Acme"],
             "namespace Acme\nimport System\n"
             "interface Pair<A, B>\n  fun first(a: A, b: B): A\n")

    def test_uncovered_type_parameter_before_an_own_type(self):
        self._rejected("namespace Main\nimport System\n"
                       "class Mine(v: Int)\n"
                       "instance<T> Acme::Pair<T, Mine>\n"
                       "  fun first(a: T, b: Mine): T => a\n"
                       "fun main(): Int => 0\n",
                       "orphan instance of 'Acme::Pair'",
                       [self._PAIR])

    def test_own_type_before_a_type_parameter(self):
        self._accepted("namespace Main\nimport System\n"
                       "class Mine(v: Int)\n"
                       "instance<T> Acme::Pair<Mine, T>\n"
                       "  fun first(a: Mine, b: T): Mine => a\n"
                       "fun main(): Int => 0\n",
                       [self._PAIR])

    def test_foreign_interface_for_an_own_type(self):
        self._accepted("namespace Main\nimport System\n"
                       "class Mine(v: Int)\n"
                       "instance [ambient] Show<Mine>\n"
                       "  fun show(value: Mine): String => \"mine\"\n"
                       "fun main(): Int => 0\n")

    def test_own_interface_for_a_foreign_type(self):
        self._accepted("namespace Main\nimport System\n"
                       "interface Describe<T>\n  fun describe(value: T): String\n"
                       "instance [ambient] Describe<Int>\n"
                       "  fun describe(value: Int): String => \"int\"\n"
                       "fun main(): Int => 0\n")

    def test_library_instance_for_its_own_type(self):
        self._accepted("fun main(): System::Int => Acme::count()\n",
                       [("acme", ["Acme"],
                         "namespace Acme\nimport System\n"
                         "class Thing(v: Int)\n"
                         "instance [ambient] Show<Thing>\n"
                         "  fun show(value: Thing): String => \"thing\"\n"
                         "fun count(): Int => 1\n")])

    def test_library_orphan_names_the_library(self):
        self._rejected("fun main(): System::Int => Acme::count()\n",
                       "orphan instance of 'System::Show': library 'acme' owns neither "
                       "the interface nor the type it is implemented for",
                       [("acme", ["Acme"],
                         "namespace Acme\nimport System\n"
                         "instance [ambient] Show<Int>\n"
                         "  fun show(value: Int): String => \"int\"\n"
                         "fun count(): Int => 1\n")])
