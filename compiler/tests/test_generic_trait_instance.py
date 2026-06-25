"""Generic trait instances: a generic type registered as a trait instance,
conditional on a `where` constraint over its own type parameter.

This is the language feature underpinning fusible stream transducers (see
TODO.md "Fusible stream transformers via generic trait instances"): a wrapping
combinator `Wrap<S>` is a `Box` *whenever* its inner `S` is, declared once and
monomorphised per concrete carrier.

The pieces exercised end to end:
  * `let [trait] _w<S,T>: _W<S,T> where Box<S,T>`  — a generic trait instance,
    registered by the `[trait]` let alone (no `typealias [where]`, so the
    instance is NOT ambiently in scope — callers declare `where Box<S,T>`).
  * constraint-driven instantiation in lowering/generics.py: discharging a
    concrete `Box<Wrap<Leaf,Int>,Int>` instantiates the witness (and, by
    recursion through the witness's own `where`, every inner instance).

Two ergonomic work-arounds appear in the source below; both are pre-existing,
separately-tracked compiler limitations, NOT part of this feature:
  * the recursive unwrap is routed through a free helper `_unwrapInner` because a
    same-named call inside the witness method binds to the enclosing method
    (member shadowing);
  * `Wrap<...>` and `_unwrapInner<...>` are given explicit type args because `T`
    appears only in the return/`where`, so it can't be inferred from arguments.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib


_PRELUDE = """namespace Main
import System

interface Box<S, T>
  fun unwrap(self: S): T

class [final] Leaf(v: System::Int)
class _BoxLeaf() : Box<Leaf, System::Int>
  fun unwrap(self: Leaf): System::Int
    ret self.v
let [trait] _box_leaf: _BoxLeaf = _BoxLeaf()

class [final] Wrap<S, T>(inner: S)
class _BoxWrap<S, T>() : Box<Wrap<S, T>, T>
  fun unwrap(self: Wrap<S, T>): T where Box<S, T>
    ret _unwrapInner<S, T>(self.inner)
fun _unwrapInner<S, T>(b: S): T where Box<S, T>
  ret unwrap(b)
let [trait] _box_wrap<S, T>: _BoxWrap<S, T> = _BoxWrap<S, T>() where Box<S, T>

fun useBox<S, T>(b: S): T where Box<S, T>
  ret unwrap(b)

"""


class TestGenericTraitInstance(TestCase):
    def test_single_wrap(self):
        # Box<Wrap<Leaf,Int>,Int> is discharged by instantiating the generic
        # witness at S=Leaf,T=Int; its `where Box<Leaf,Int>` is met by _box_leaf.
        src = _PRELUDE + (
            "fun main(): System::Int\n"
            "  let w = Wrap<Leaf, System::Int>(Leaf(7))\n"
            "  ret useBox(w)\n")
        self.assertEqual(7, compile_and_run_stdlib(src))

    def test_nested_wrap_recurses(self):
        # Box<Wrap<Wrap<Leaf>>> instantiates the witness at S=Wrap<Leaf,Int>,
        # whose own `where Box<Wrap<Leaf,Int>,Int>` instantiates the next witness
        # at S=Leaf — recursion through the instance constraint.
        src = _PRELUDE + (
            "fun main(): System::Int\n"
            "  let inner = Wrap<Leaf, System::Int>(Leaf(5))\n"
            "  let outer = Wrap<Wrap<Leaf, System::Int>, System::Int>(inner)\n"
            "  ret useBox(outer)\n")
        self.assertEqual(5, compile_and_run_stdlib(src))


# Exercises the STDLIB transducers (System::Stream / System::Map / System::Filter
# in stdlib/stream.yafl), which are built on generic trait instances. Each
# combinator is a dedicated generic type that wraps its source and is itself a
# `Stream`; a pipeline is the static type `Map<Filter<Count>>`, every `next`
# monomorphic. The test supplies only a concrete leaf (`Count`) — its own
# Stream instance — plus a consumer; the combinators come from the library.
#
# The combinators are spelled as direct constructions `System::Map<S,A,B>(…)` /
# `System::Filter<S,T>(…)`: the library offers no `map`/`filter` constructor
# functions yet (a param appearing only in the function value can't be inferred,
# and a free `map` would clash with `System::map` over List), and the consumer
# drives the stream with `System::streamNext` rather than a member `next`
# (member shadowing). All pre-existing limits, not the library's fault.
_STREAM_LEAF = """namespace Main
import System

# A leaf source that counts cur..hi and cannot fail — its error type is Never,
# so it only ever yields Ok(value) or Ok(None) (Error is unconstructable).
class [final] Count(cur: System::Int, hi: System::Int)
class _StreamCount() : System::Stream<Count, System::Int, System::Never>
  fun next(self: Count): (stream: Count, value: System::Result<System::Int|System::None, System::Never>)
    ret self.cur > self.hi
      ? (self, System::Ok<System::Int|System::None, System::Never>(None))
      : (Count(self.cur + 1, self.hi), System::Ok<System::Int|System::None, System::Never>(self.cur))
let [trait] _stream_count: _StreamCount = _StreamCount()

# Sum the values into Ok(total), forwarding an Error of type E if one occurs.
fun [tail] sumStream<S, E>(s: S, acc: System::Int): System::Result<System::Int, E> where System::Stream<S, System::Int, E>
  let r = System::streamNext<S, System::Int, E>(s)
  ret match(r.value)
    (ok: System::Ok<System::Int|System::None, E>) => match(ok.value)
      (x: System::Int)  => sumStream<S, E>(r.stream, acc + x)
      (n: System::None) => System::Ok<System::Int, E>(acc)
    (er: System::Error<System::Int|System::None, E>) => System::Error<System::Int, E>(er.error)

# Drive an infallible (Never) Int stream to its sum. S is inferred from the
# argument; the Error arm is unreachable (Never is uninhabited).
fun drain<S>(s: S): System::Int where System::Stream<S, System::Int, System::Never>
  ret match(sumStream<S, System::Never>(s, 0))
    (ok: System::Ok<System::Int, System::Never>)  => ok.value
    (er: System::Error<System::Int, System::Never>) => 0

fun isOdd(x: System::Int): System::Bool
  ret x % 2 == 1
fun dbl(x: System::Int): System::Int
  ret x * 10

"""


class TestStreamTransducers(TestCase):
    def test_map_over_leaf(self):
        # 1..5 mapped *10, summed: 10+20+30+40+50 = 150.
        src = _STREAM_LEAF + (
            "fun main(): System::Int\n"
            "  ret drain(System::Map<Count, System::Int, System::Int>(Count(1, 5), dbl))\n")
        self.assertEqual(150, compile_and_run_stdlib(src))

    def test_filter_map_pipeline(self):
        # 1..5 |> filter odd (1,3,5) |> map *10 (10,30,50), summed = 90.
        # The pipeline is the static type Map<Filter<Count>>; two distinct
        # generic Stream instances from the stdlib composed.
        src = _STREAM_LEAF + (
            "fun main(): System::Int\n"
            "  let f = System::Filter<Count, System::Int>(Count(1, 5), isOdd)\n"
            "  ret drain(System::Map<System::Filter<Count, System::Int>, System::Int, System::Int>(f, dbl))\n")
        self.assertEqual(90, compile_and_run_stdlib(src))

    def test_generic_lines_splitter(self):
        # The generic System::Lines<S> line-splitter — a stateful, many-to-many
        # transducer — over a pure chunk source ("ab\\nc" + "d\\nef" -> lines
        # "ab","cd","ef": 3 lines, 6 chars). Constructed directly as
        # Lines<Feed>(source, ""); the |>-chain form of generic transformers
        # awaits a generic-inference improvement (see TODO).
        src = (
            "namespace Main\nimport System\n"
            "class [final] Feed(idx: System::Int)\n"
            "class _SF() : System::Stream<Feed, System::String, System::Never>\n"
            "  fun next(self: Feed): (stream: Feed, value: System::Result<System::String|System::None, System::Never>)\n"
            "    ret self.idx == 0 ? (Feed(1), System::Ok<System::String|System::None, System::Never>(\"ab\\nc\"))\n"
            "      : self.idx == 1 ? (Feed(2), System::Ok<System::String|System::None, System::Never>(\"d\\nef\"))\n"
            "                      : (self, System::Ok<System::String|System::None, System::Never>(None))\n"
            "let [trait] _sf: _SF = _SF()\n"
            "fun [tail] tally<S>(s: S, ln: System::Int, ch: System::Int): System::Int where System::Stream<S, System::String, System::Never>\n"
            "  let r = System::streamNext<S, System::String, System::Never>(s)\n"
            "  ret match(r.value)\n"
            "    (ok: System::Ok<System::String|System::None, System::Never>) => match(ok.value)\n"
            "      (line: System::String) => tally<S>(r.stream, ln + 1, ch + System::length(line))\n"
            "      (n: System::None)       => ln * 10 + ch\n"
            "    (er: System::Error<System::String|System::None, System::Never>) => 0 - 1\n"
            "fun main(): System::Int\n"
            "  ret tally<System::Lines<Feed>>(System::Lines<Feed>(Feed(0), \"\"), 0, 0)\n")
        self.assertEqual(36, compile_and_run_stdlib(src))  # 3 lines, 6 chars

    def test_error_propagates_through_pipeline(self):
        # A leaf that faults partway must surface its Error through map — the
        # transformers carry the generic E channel, they don't interpret it.
        src = ("namespace Main\nimport System\n"
               "enum Boom(code: System::Int)\n"
               "class [final] Src(cur: System::Int)\n"
               "class _S() : System::Stream<Src, System::Int, Boom>\n"
               "  fun next(self: Src): (stream: Src, value: System::Result<System::Int|System::None, Boom>)\n"
               "    ret self.cur == 3\n"
               "      ? (self, System::Error<System::Int|System::None, Boom>(Boom(42)))\n"
               "      : (Src(self.cur + 1), System::Ok<System::Int|System::None, Boom>(self.cur))\n"
               "let [trait] _s: _S = _S()\n"
               "fun dbl(x: System::Int): System::Int\n  ret x * 10\n"
               "fun [tail] run<S, E>(s: S, acc: System::Int): System::Result<System::Int, E> where System::Stream<S, System::Int, E>\n"
               "  let r = System::streamNext<S, System::Int, E>(s)\n"
               "  ret match(r.value)\n"
               "    (ok: System::Ok<System::Int|System::None, E>) => match(ok.value)\n"
               "      (x: System::Int)  => run<S, E>(r.stream, acc + x)\n"
               "      (n: System::None) => System::Ok<System::Int, E>(acc)\n"
               "    (er: System::Error<System::Int|System::None, E>) => System::Error<System::Int, E>(er.error)\n"
               "fun main(): System::Int\n"
               "  let m = System::Map<Src, System::Int, System::Int>(Src(1), dbl)\n"
               "  ret match(run<System::Map<Src, System::Int, System::Int>, Boom>(m, 0))\n"
               "    (ok: System::Ok<System::Int, Boom>)  => ok.value\n"
               "    (er: System::Error<System::Int, Boom>) => er.error.code\n")
        # values 1,2 mapped to 10,20 then Error(Boom(42)) surfaces -> exit 42.
        self.assertEqual(42, compile_and_run_stdlib(src))
