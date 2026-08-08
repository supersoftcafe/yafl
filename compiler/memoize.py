"""The Python counterpart of System::memoize (stdlib/memoize.yafl).

Same contract, both halves:

  1. `f` MAY be called more than once for the same argument — there is no
     exactly-once guarantee (the port's CAS trie has none either).
  2. EVERY caller receives the SAME answer for a given argument. The first
     value published wins; a caller that loses the race discards what it
     computed and returns the winner's (setdefault is that publish).

The port and this compiler must use the same technique at the same sites
(mechanism parity, user ruling 2026-08-07): where the port wraps a lookup
in System::memoize, the Python side wraps it here, keyed by the same
equivalence relation. Cache lifetime is the closure's lifetime — create the
memoized function at the scope the cache belongs to (a pass, a converge
round), exactly as the port's ctx carries its closure.
"""
from __future__ import annotations

from typing import Callable, TypeVar

A = TypeVar("A")
R = TypeVar("R")

_MISS = object()


def memoize(f: Callable[[A], R]) -> Callable[[A], R]:
    cache: dict = {}

    def memoized(a: A) -> R:
        hit = cache.get(a, _MISS)
        if hit is not _MISS:
            return hit
        return cache.setdefault(a, f(a))

    return memoized
