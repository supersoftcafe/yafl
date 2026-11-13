"""End-to-end tests for `System::args()` — CLI-args access.

`args()` returns the user-supplied positional arguments as a
`List<String>`, dropping the program path (argv[0]) so user code doesn't
have to. Backed by two foreign helpers (`sys_argc`, `sys_argv_at`) that
expose the raw process argv, set by the emitted `main()` shim before
`thread_start`.

Runtime behaviour is checked by compiler/yafl_tests/args.yafl.
"""
from __future__ import annotations

import os
import subprocess
import unittest

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import _RUN_ENV, compile_and_run_stdlib, compile_to_binary


_LEN_PROG = (
    "import System\n"
    "import System::Containers\n"
    "fun main(): System::Int\n"
    "    ret System::Containers::fold<System::String, System::Int>(System::args(), 0, (a: System::Int, x: System::String) => a + 1)\n"
)


class TestArgsLength(TestCase):

    def test_no_args(self):
        """Run with only the program path — args() is empty. (Not a [test]: the
        runner always gives its child `--run-raw <id>`.)"""
        self.assertEqual(0, compile_and_run_stdlib(_LEN_PROG))

    def test_single_arg(self):
        self.assertEqual(1, compile_and_run_stdlib(_LEN_PROG, args=["x"]))

    def test_several_args(self):
        self.assertEqual(5, compile_and_run_stdlib(
            _LEN_PROG, args=["a", "b", "c", "d", "e"]))


class TestArgsContent(TestCase):
    """Exercise the actual string content, not just count."""

    def test_first_arg_byte(self):
        """The first user arg becomes head of args(); its first byte
        is what we passed in."""
        src = (
            "import System\n"
            "import System::Containers\n"
            "fun main(): System::Int\n"
            "    ret match(System::Containers::head<System::String>(System::args()))\n"
            "        (s: System::String) => Int(System::byteAt(s, 0))\n"
            "        (n: System::None)   => 0\n"
        )
        self.assertEqual(ord('Z'), compile_and_run_stdlib(src, args=["Z"]))

    def test_first_arg_length(self):
        """A multi-byte arg's String length matches the C string length."""
        src = (
            "import System\n"
            "import System::Containers\n"
            "fun main(): System::Int\n"
            "    ret match(System::Containers::head<System::String>(System::args()))\n"
            "        (s: System::String) => System::length(s)\n"
            "        (n: System::None)   => 0\n"
        )
        self.assertEqual(11, compile_and_run_stdlib(src, args=["hello world"]))

    def test_program_path_dropped(self):
        """argv[0] is the program path, NOT included in args(). Verified
        by checking that args() with one user arg has length 1, not 2."""
        self.assertEqual(1, compile_and_run_stdlib(_LEN_PROG, args=["only"]))


class TestEnv(TestCase):
    """`System::env` is None when a variable is unset OR empty — never "" —
    so `env(name) ?? default` is the whole idiom."""

    _PROG = (
        "import System\n"
        "import System::Containers\n"
        "fun main(): System::Int\n"
        "    ret System::length(System::env(\"YAFL_TEST_ENV\") ?? \"dflt\")\n"
    )

    def test_set_value_is_returned(self):
        self.assertEqual(3, compile_and_run_stdlib(self._PROG, env={"YAFL_TEST_ENV": "abc"}))

    def test_empty_value_is_none(self):
        self.assertEqual(4, compile_and_run_stdlib(self._PROG, env={"YAFL_TEST_ENV": ""}))


# A declaration System::Args cannot read is a mistake in the PROGRAM, not in
# its command line: `parse`, `help` and `message` end the process, naming it,
# rather than tell the user something they could not have caused. A [test]
# cannot expect its own process to end, so this one compiles one program
# and runs it once per mistake, the first argument choosing which.
_BAD_DECLARATIONS = """\
namespace Main

import System
import System::Args
import System::Containers

fun twice() => Args("tool", "", List<Arg<Bool>>(
  Flag(List("-v", "--verbose"), "", (b: Bool) => true),
  Flag(List("-q", "-v"), "", (b: Bool) => true)))

fun nameless() => Args("tool", "", List<Arg<Bool>>(
  Flag(List<String>(), "Say less", (b: Bool) => true)))

fun undashed() => Args("tool", "", List<Arg<Bool>>(
  Flag(List("verbose"), "", (b: Bool) => true)))

fun dashes() => Args("tool", "", List<Arg<Bool>>(
  Flag(List("--"), "", (b: Bool) => true)))

fun dashedPositional() => Args("tool", "", List<Arg<Bool>>(
  Positional("-file", ExactlyOne(), "", (b: Bool, vs: List<String>) => true)))

fun sound() => Args("tool", "", List<Arg<Bool>>(
  Flag(List("-v", "--verbose"), "", (b: Bool) => true),
  Positional("file", AtMostOne(), "", (b: Bool, vs: List<String>) => true)))

fun outcome(spec: Args<Bool>): Int => match(parse(spec, List<String>(), false))
  (e: ArgError) => 3
  (b: Bool)     => 0

fun main(): Int => match(head(args()))
  (which: String) => which == "twice" ? outcome(twice())
    : which == "nameless" ? outcome(nameless())
    : which == "undashed" ? outcome(undashed())
    : which == "dashes" ? outcome(dashes())
    : which == "dashedPositional" ? outcome(dashedPositional())
    : which == "help" ? length(help(twice(), 80, false))
    : outcome(sound())
  ()              => outcome(sound())
"""


class TestBadDeclarations(TestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.binary = compile_to_binary(_BAD_DECLARATIONS)

    @classmethod
    def tearDownClass(cls):
        try:
            os.unlink(cls.binary)
        except OSError:
            pass
        super().tearDownClass()

    def _run(self, which: str) -> tuple[int, str]:
        r = subprocess.run([self.binary, which], capture_output=True, text=True,
                           timeout=10, env=_RUN_ENV, stdin=subprocess.DEVNULL)
        return r.returncode, r.stderr

    def _assert_ends(self, which: str, why: str):
        rc, err = self._run(which)
        self.assertEqual(1, rc, err)
        self.assertIn("System::Args: " + why, err)

    def test_sound_declaration_parses(self):
        self.assertEqual((0, ""), self._run("sound"))

    def test_option_string_declared_twice(self):
        self._assert_ends("twice", "option string '-v' is declared twice")

    def test_option_with_no_names(self):
        self._assert_ends("nameless", "an option is declared with no names")

    def test_option_string_without_a_dash(self):
        self._assert_ends("undashed", "option string 'verbose' does not start with '-'")

    def test_option_string_of_dashes_alone(self):
        self._assert_ends("dashes", "option string '--' is dashes alone")

    def test_positional_named_like_an_option(self):
        self._assert_ends("dashedPositional", "positional '-file' is named like an option")

    def test_help_checks_too(self):
        self._assert_ends("help", "option string '-v' is declared twice")
