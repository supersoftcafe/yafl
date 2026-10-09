"""Fully-inferred pipeline over THREADED combinators — single-step, no recursion.

Two nested generic combinator builders with NO type arguments, where the element
type changes at each level (Int -> Tok -> Int) and each combinator type carries
its error channel `E` (threaded), pinned at construction by the class `where`:

    One        : Stream<One,        Int, Never>
    Lex<S,E>   : Stream<Lex<S,E>,   Tok, E | Bool>  where Stream<S, Int, E>
    Pty<S,E>   : Stream<Pty<S,E>,   Int, E>         where Stream<S, Tok, E>

`drain<S,E>(s, acc): Int | E where Stream<S, Int, E>` over `Pty<Lex<One,…>,…>`
reads its `E` straight off the combinator type in ONE step — no chain recursion.
The innermost argument is a FIELD ACCESS off a let (`src.one`), which is the
nested-inference trigger that `meet` handles: the inner builder first latches a
hole, and the outer call must refresh once it fills. Exercises threading +
meet + class-`where` construction discharge end to end.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


_SRC = """
namespace Test
import System

class [final] Tok(v: System::Int)

class [final] One(done: System::Bool)
instance [ambient] System::Stream<One, System::Int, System::Never>
  fun next(self: One): (stream: One, value: System::Result<System::Int | System::None, System::Never>)
    ret self.done
      ? (self, System::Ok<System::Int | System::None, System::Never>(None))
      : (One(true), System::Ok<System::Int | System::None, System::Never>(5))

class [final] Lex<S, E>(inner: S) where System::Stream<S, System::Int, E>
instance [ambient] <S, E> System::Stream<Lex<S, E>, Tok, E | System::Bool> where System::Stream<S, System::Int, E>
  fun next(self: Lex<S, E>): (stream: Lex<S, E>, value: System::Result<Tok | System::None, E | System::Bool>)
    let r = System::streamNext<S, System::Int, E>(self.inner)
    ret match(r.value)
      (ok: System::Ok<System::Int | System::None, E>) => match(ok.value)
        (v: System::Int)  => (Lex<S, E>(r.stream), System::Ok<Tok | System::None, E | System::Bool>(Tok(v)))
        (x: System::None) => (Lex<S, E>(r.stream), System::Ok<Tok | System::None, E | System::Bool>(None))
      (er: System::Error<System::Int | System::None, E>) => (Lex<S, E>(r.stream), System::Error<Tok | System::None, E | System::Bool>(er.error))

fun wrapLex<S, E>(s: S): Lex<S, E> where System::Stream<S, System::Int, E>
  ret Lex<S, E>(s)

class [final] Pty<S, E>(inner: S) where System::Stream<S, Tok, E>
instance [ambient] <S, E> System::Stream<Pty<S, E>, System::Int, E> where System::Stream<S, Tok, E>
  fun next(self: Pty<S, E>): (stream: Pty<S, E>, value: System::Result<System::Int | System::None, E>)
    let r = System::streamNext<S, Tok, E>(self.inner)
    ret match(r.value)
      (ok: System::Ok<Tok | System::None, E>) => match(ok.value)
        (v: Tok)          => (Pty<S, E>(r.stream), System::Ok<System::Int | System::None, E>(v.v))
        (x: System::None) => (Pty<S, E>(r.stream), System::Ok<System::Int | System::None, E>(None))
      (er: System::Error<Tok | System::None, E>) => (Pty<S, E>(r.stream), System::Error<System::Int | System::None, E>(er.error))

fun wrapPty<S, E>(s: S): Pty<S, E> where System::Stream<S, Tok, E>
  ret Pty<S, E>(s)

class [final] Holder(one: One)
fun mkOne(): Holder
  ret Holder(One(false))

fun [tail] drain<S, E>(s: S, acc: System::Int): System::Int | E where System::Stream<S, System::Int, E>
  let r = System::streamNext<S, System::Int, E>(s)
  ret match(r.value)
    (ok: System::Ok<System::Int | System::None, E>) => match(ok.value)
      (v: System::Int)  => drain<S, E>(r.stream, acc + v)
      (x: System::None) => acc
    (er: System::Error<System::Int | System::None, E>) => er.error

fun main(): System::Int
  # No type args anywhere: builders inferred from src.one (field access trigger),
  # drain's S from the nested result Pty<Lex<One, Never>, Never | Bool>, drain's E
  # read off that type in one step.
  let src = mkOne()
  ret match(drain(wrapPty(wrapLex(src.one)), 0))
    (n: System::Int) => n
    ()               => 98
"""


class TestFullyInferredPipeline(TestCase):
    def test_nested_generic_call_feeds_where_constrained_call(self):
        rc, _out = compile_and_run_stdlib_capture(_SRC, timeout=120)
        self.assertEqual(5, rc)
