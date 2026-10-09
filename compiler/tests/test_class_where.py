"""A class may carry a `where` clause, and a construction site discharges it.

`class Wrap<S, E>(inner: S) where Stream<S, Int, E>` has a phantom error param `E`
that the constructor holds no value of — it is pinned by the class's `where`
against the trait instances in scope. So `Wrap(One(false))` infers BOTH `S` (from
the argument) and `E` (`= Never`, discharged from `Stream<One, Int, E>`), with no
explicit type arguments, and the whole thing survives monomorphisation.

This is the mechanism a stream-combinator redesign would lean on (a combinator
type carrying its error channel even though structurally it only needs its inner
source). It needs two things wired: a class `where` compiles under the class's own
generic-type scope, and that `where` is carried onto the synthesised constructor.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


_SRC = """
namespace Test
import System

class [final] One(done: System::Bool)
instance [ambient] System::Stream<One, System::Int, System::Never>
  fun next(self: One): (stream: One, value: System::Result<System::Int | System::None, System::Never>)
    ret self.done
      ? (self, System::Ok<System::Int | System::None, System::Never>(None))
      : (One(true), System::Ok<System::Int | System::None, System::Never>(5))

# Combinator with a PHANTOM error param `E`, pinned at construction by the class `where`.
class [final] Wrap<S, E>(inner: S) where System::Stream<S, System::Int, E>
instance [ambient] <S, E> System::Stream<Wrap<S, E>, System::Int, E> where System::Stream<S, System::Int, E>
  fun next(self: Wrap<S, E>): (stream: Wrap<S, E>, value: System::Result<System::Int | System::None, E>)
    let r = System::streamNext<S, System::Int, E>(self.inner)
    ret match(r.value)
      (ok: System::Ok<System::Int | System::None, E>) => (Wrap<S, E>(r.stream), ok)
      (er: System::Error<System::Int | System::None, E>) => (Wrap<S, E>(r.stream), er)

fun [tail] drain<S, E>(s: S, acc: System::Int): System::Int | E where System::Stream<S, System::Int, E>
  let r = System::streamNext<S, System::Int, E>(s)
  ret match(r.value)
    (ok: System::Ok<System::Int | System::None, E>) => match(ok.value)
      (v: System::Int)  => drain<S, E>(r.stream, acc + v)
      (x: System::None) => acc
    (er: System::Error<System::Int | System::None, E>) => er.error

fun main(): System::Int
  # No type args: S from the argument, E discharged from the class `where`.
  ret match(drain(Wrap(One(false)), 0))
    (n: System::Int) => n
    ()               => 98
"""


class TestClassWhere(TestCase):
    def test_class_where_discharges_phantom_param_at_construction(self):
        rc, _out = compile_and_run_stdlib_capture(_SRC, timeout=120)
        self.assertEqual(5, rc)
