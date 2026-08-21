"""Affine drops: a never-referenced `[linear]` binding auto-releases at scope
exit through its `Drop` instance (lowering/drops.py inserts the call; the
linearity checker then sees ordinary consumption).

The prelude defines a linear `Res` whose Drop instance prints "dropped", so a
test observes exactly when (and how many times) a drop fires. Without a Drop
instance in scope, the old linearity error stands.
"""
from __future__ import annotations

import contextlib
import io

import compiler as c
from tests.testutil import BatchedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


_PRELUDE = """namespace Main
import System

class [linear,final] Res(x: System::Int)
  fun [terminal] fin(): System::None
    ret None

instance [ambient] System::Drop<Res>
  fun drop(self: Res): System::None
    System::print("dropped")
    ret self.fin()

fun sink(r: Res): System::Int
  let _ = r.fin()
  ret 4

"""


class TestAffineDrop(TestCase):
    def test_unused_let_drops_once(self):
        rc, out = compile_and_run_stdlib_capture(_PRELUDE + (
            "fun main(): System::Int\n"
            "  let r = Res(5)\n"
            "  ret 7\n"))
        self.assertEqual(7, rc)
        self.assertEqual(1, out.count("dropped"))

    def test_unused_param_drops(self):
        rc, out = compile_and_run_stdlib_capture(_PRELUDE + (
            "fun eat(r: Res): System::Int\n"
            "  ret 3\n"
            "fun main(): System::Int\n"
            "  ret eat(Res(1))\n"))
        self.assertEqual(3, rc)
        self.assertEqual(1, out.count("dropped"))

    def test_pipe_lambda_param_drops(self):
        # The shape the drop feature exists for: `resource |> (r, v) => use v`,
        # the unused resource half dropping at the lambda's scope exit.
        rc, out = compile_and_run_stdlib_capture(_PRELUDE + (
            "fun main(): System::Int\n"
            "  ret (Res(1), 9) |> (r, v) => v\n"))
        self.assertEqual(9, rc)
        self.assertEqual(1, out.count("dropped"))

    def test_explicit_consumption_does_not_drop(self):
        rc, out = compile_and_run_stdlib_capture(_PRELUDE + (
            "fun main(): System::Int\n"
            "  let r = Res(5)\n"
            "  ret sink(r)\n"))
        self.assertEqual(4, rc)
        self.assertEqual(0, out.count("dropped"))

    def test_without_instance_the_linearity_error_stands(self):
        # Res2 is linear with NO Drop instance: an unused binding is still the
        # old hard error, not a silent leak.
        src = (_PRELUDE
               + "class [linear,final] Res2(y: System::Int)\n"
               + "fun main(): System::Int\n"
               + "  let q = Res2(3)\n"
               + "  ret 0\n")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = c.compile([c.Input(src, "test.yafl")], use_stdlib=True, just_testing=True)
        self.assertFalse(code, "an undroppable linear leak must still fail")
        self.assertIn("never used; it must be consumed once", buf.getvalue())

    def test_io_handle_drops_and_closes(self):
        # End-to-end over the real Drop<IO> instance: asStream splits handle
        # from stream; the handle half is never referenced and auto-closes at
        # scope exit — after the stream is drained (scope-exit timing).
        rc, _out = compile_and_run_stdlib_capture(
            "namespace Main\n"
            "import System\n"
            "import System::IO\n"
            "fun [tail] count(s: StreamIO, n: System::Int): System::Int\n"
            "  let r = System::streamNext<StreamIO, System::String, IOError>(s)\n"
            "  ret match(r.value)\n"
            "    (ok: System::Ok<System::String|System::None, IOError>) => match(ok.value)\n"
            "      (chunk: System::String) => count(r.stream, n + System::length(chunk))\n"
            "      (x: System::None)       => n\n"
            "    (er: System::Error<System::String|System::None, IOError>) => 0 - 1\n"
            "fun main(): System::Int\n"
            "  ret stdin().asStream() |> (i, s) => count(s, 0)\n",
        )
        self.assertEqual(0, rc)
