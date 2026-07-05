"""Monomorphising an error-GROWING stream combinator.

A combinator whose output error type is a union that ADDS a member to its
source's error — `_Grow<S,E> : Stream<Grow<S>, Int, E|Bool> where Stream<S,Int,E>`
— has `E` only in that output union, so unifying the implemented interface
against a concrete constraint can't pin it (`E|Bool ~ Bool` is ambiguous). The
monomorphiser must solve the instance's `where` constraint to bind `E` from the
source instance, and must not treat `E|Bool` (a placeholder nested in a union)
as a concrete type argument.

This is the compiler capability the streaming-JSON tokenizer needs (its tokens
carry `E | JsonParseError`). Here we only assert monomorphisation succeeds —
`compile` runs the Python pipeline through codegen and returns the C source;
that path used to crash with "GenericPlaceholderSpec should be replaced with a
concrete type".

The `One` source cannot fail (`E = Never`), so the grown stream's error channel
is `Never | Bool` — NOT `Bool`: a union keeps every member, uninhabited ones
included. The driver therefore asks for `Never | Bool`, and `main` covers the
unreachable `Never` arm with an `()` else.
"""
from __future__ import annotations

import compiler as c
from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


_SRC = """
namespace Test
import System

class [final] One(done: System::Bool)
class _OneStream() : System::Stream<One, System::Int, System::Never>
  fun next(self: One): (stream: One, value: System::Result<System::Int | System::None, System::Never>)
    ret self.done
      ? (self, System::Ok<System::Int | System::None, System::Never>(None))
      : (One(true), System::Ok<System::Int | System::None, System::Never>(5))
let [trait] _one: _OneStream = _OneStream()

class [final] Grow<S>(inner: S)
class _GrowStream<S, E>() : System::Stream<Grow<S>, System::Int, E | System::Bool>
  fun next(self: Grow<S>): (stream: Grow<S>, value: System::Result<System::Int | System::None, E | System::Bool>) where System::Stream<S, System::Int, E>
    let r = System::streamNext<S, System::Int, E>(self.inner)
    ret match(r.value)
      (ok: System::Ok<System::Int | System::None, E>) => match(ok.value)
        (v: System::Int)  => (Grow<S>(r.stream), System::Ok<System::Int | System::None, E | System::Bool>(v))
        (x: System::None) => (Grow<S>(r.stream), System::Ok<System::Int | System::None, E | System::Bool>(None))
      (er: System::Error<System::Int | System::None, E>) => (Grow<S>(r.stream), System::Error<System::Int | System::None, E | System::Bool>(er.error))
let [trait] _grow<S, E>: _GrowStream<S, E> = _GrowStream<S, E>() where System::Stream<S, System::Int, E>

fun [tail] drain<S, E>(s: S, acc: System::Int): System::Int | E where System::Stream<S, System::Int, E>
  let r = System::streamNext<S, System::Int, E>(s)
  ret match(r.value)
    (ok: System::Ok<System::Int | System::None, E>) => match(ok.value)
      (v: System::Int)  => drain<S, E>(r.stream, acc + v)
      (x: System::None) => acc
    (er: System::Error<System::Int | System::None, E>) => er.error

fun main(): System::Int
  ret match(drain<Grow<One>, System::Never | System::Bool>(Grow<One>(One(false)), 0))
    (n: System::Int)  => n
    (b: System::Bool) => 99
    ()                => 98
"""


class TestErrorGrowingStream(TestCase):
    def test_monomorphises_to_c(self):
        # The `where`-directed discharge binds E=Never for the One source, so the
        # grown stream's error channel is `Never | Bool`; the driver names that
        # type exactly and codegen produces valid C.
        result = c.compile([c.Input(_SRC, "test.yafl")], use_stdlib=True)
        self.assertNotEqual("", result)

    def test_compiles_and_runs(self):
        # End to end: clang-compiles and runs. `drain` sums One's single value 5;
        # the unreachable Error/Never arm coerces to a zero of the target repr.
        rc, _out = compile_and_run_stdlib_capture(_SRC, timeout=120)
        self.assertEqual(5, rc)
