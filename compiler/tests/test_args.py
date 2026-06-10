"""End-to-end tests for `System::args()` — CLI-args access.

`args()` returns the user-supplied positional arguments as a
`List<String>`, dropping the program path (argv[0]) so user code doesn't
have to. Backed by two foreign helpers (`sys_argc`, `sys_argv_at`) that
expose the raw process argv, set by the emitted `main()` shim before
`thread_start`.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib


_LEN_PROG = (
    "import System\n"
    "fun main(): System::Int\n"
    "    ret System::fold<System::String, System::Int>(System::args(), 0, (a: System::Int, x: System::String) => a + 1)\n"
)


class TestArgsLength(TestCase):

    def test_no_args(self):
        """Run with only the program path — args() is empty."""
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
            "fun main(): System::Int\n"
            "    ret match(System::head<System::String>(System::args()))\n"
            "        (s: System::String) => Int(System::byteAt(s, 0))\n"
            "        (n: System::None)   => 0\n"
        )
        self.assertEqual(ord('Z'), compile_and_run_stdlib(src, args=["Z"]))

    def test_first_arg_length(self):
        """A multi-byte arg's String length matches the C string length."""
        src = (
            "import System\n"
            "fun main(): System::Int\n"
            "    ret match(System::head<System::String>(System::args()))\n"
            "        (s: System::String) => System::length(s)\n"
            "        (n: System::None)   => 0\n"
        )
        self.assertEqual(11, compile_and_run_stdlib(src, args=["hello world"]))

    def test_program_path_dropped(self):
        """argv[0] is the program path, NOT included in args(). Verified
        by checking that args() with one user arg has length 1, not 2."""
        self.assertEqual(1, compile_and_run_stdlib(_LEN_PROG, args=["only"]))
