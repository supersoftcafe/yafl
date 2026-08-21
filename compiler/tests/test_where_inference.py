"""Call-site type inference through a `where` clause.

`drain<S, E> ... where Stream<S, Int, E>` has `E` only in the constraint and the
return type — never in a value parameter. The source argument pins `S`, and then
`E` is determined by `S`'s `Stream` instance. The call site must infer it with no
type arguments written: argument inference binds `S`, then the `where` constraint
`Stream<S, Int, E>` matched against the concrete `Stream<One, Int, Never>`
instance binds `E = Never`.

Before this, a bare `drain(...)` crashed ("could not cast None object to
CallableSpec") because `E` stayed unbound and the call never resolved.
"""
from __future__ import annotations

from tests.testutil import BatchedTestCase as TestCase
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

fun [tail] drain<S, E>(s: S, acc: System::Int): System::Int | E where System::Stream<S, System::Int, E>
  let r = System::streamNext<S, System::Int, E>(s)
  ret match(r.value)
    (ok: System::Ok<System::Int | System::None, E>) => match(ok.value)
      (v: System::Int)  => drain<S, E>(r.stream, acc + v)
      (x: System::None) => acc
    (er: System::Error<System::Int | System::None, E>) => er.error

fun main(): System::Int
  # No type arguments: S infers from the argument, E from the `where` clause.
  ret match(drain(One(false), 0))
    (n: System::Int) => n
    ()               => 98
"""


class TestWhereDirectedInference(TestCase):
    def test_where_only_param_inferred_at_call_site(self):
        rc, _out = compile_and_run_stdlib_capture(_SRC, timeout=120)
        self.assertEqual(5, rc)
