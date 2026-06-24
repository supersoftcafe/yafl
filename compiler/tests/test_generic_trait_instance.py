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

class [final] Count(cur: System::Int, hi: System::Int)
class _StreamCount() : System::Stream<Count, System::Int>
  fun next(self: Count): (stream: Count, value: System::Int|System::None)
    ret self.cur > self.hi ? (self, None) : (Count(self.cur + 1, self.hi), self.cur)
let [trait] _stream_count: _StreamCount = _StreamCount()

fun [tail] sumStream<S>(s: S, acc: System::Int): System::Int where System::Stream<S, System::Int>
  let r = System::streamNext<S, System::Int>(s)
  ret match(r.value)
    (n: System::None) => acc
    (x: System::Int)  => sumStream<S>(r.stream, acc + x)

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
            "  let m = System::Map<Count, System::Int, System::Int>(Count(1, 5), dbl)\n"
            "  ret sumStream(m, 0)\n")
        self.assertEqual(150, compile_and_run_stdlib(src))

    def test_filter_map_pipeline(self):
        # 1..5 |> filter odd (1,3,5) |> map *10 (10,30,50), summed = 90.
        # The pipeline is the static type Map<Filter<Count>>; two distinct
        # generic Stream instances from the stdlib composed.
        # The consumer's type arg is spelled explicitly here — a nested generic
        # closing on `>>` — to exercise the close-angle parser end to end.
        src = _STREAM_LEAF + (
            "fun main(): System::Int\n"
            "  let f = System::Filter<Count, System::Int>(Count(1, 5), isOdd)\n"
            "  let m = System::Map<System::Filter<Count, System::Int>, System::Int, System::Int>(f, dbl)\n"
            "  ret sumStream<System::Map<System::Filter<Count, System::Int>, System::Int, System::Int>>(m, 0)\n")
        self.assertEqual(90, compile_and_run_stdlib(src))
