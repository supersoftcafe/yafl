from __future__ import annotations

from itertools import chain, groupby
from typing import Iterable, Callable, Iterator, Mapping


def flatten(lst):
    return list(chain.from_iterable(lst))

def checked_cast[_T](the_type: type[_T], the_object: object|None) -> _T:
    """Runtime-checked cast: raises on None or type mismatch. Deliberately NOT
    typing.cast (which asserts nothing) — a failed cast here is a compiler bug
    surfacing at the earliest point it can be observed."""
    if the_object is None:
        raise TypeError(f"could not cast None object to {the_type}")
    if not isinstance(the_object, the_type):
        raise TypeError(f"could not cast {type(the_object)} to {the_type}")
    return the_object

def unique(lst):
    return list(dict.fromkeys(lst))

def group_by_key[_T, _K, _V](objects: Iterable[_T], key_func: Callable[[_T], _K], value_func: Callable[[list[_T]], _V] = lambda t: t) -> dict[_K, _V]:
    sorted_objects = sorted(objects, key=key_func)  # Sorting is required
    result = {key: value_func(list(group)) for key, group in groupby(sorted_objects, key=key_func)}
    return result

def partition[_T](items: Iterable[_T], predicate: Callable[[_T], bool]) -> list[list[_T]]:
    result: list[list[_T]] = []
    group: list[_T] = []

    for item in items:
        group.append(item)
        if predicate(item):
            result.append(group)
            group = []

    if group:
        result.append(group)

    return result

def strongly_connected_components(nodes: Iterable[str], edges: Mapping[str, Iterable[str]]) -> list[list[str]]:
    """Tarjan's SCC algorithm. Roots are tried in `nodes` order and
    neighbours in sorted order, so the result never depends on string
    hashing (the bootstrap reproduces it byte for byte). SCCs come out in
    reverse topological order (callees before callers), each listing its
    members in pop order: latest-discovered first, the SCC's root last.

    Iterative: a whole program's call graph runs deeper than Python's stack.
    Each work entry is a node and the iterator over its remaining
    neighbours; a child's lowlink folds into its parent when the child's
    entry is popped, exactly where the recursive form would return."""
    index: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    result: list[list[str]] = []

    def discover(v: str) -> tuple[str, Iterator[str]]:
        index[v] = lowlink[v] = len(index)
        stack.append(v)
        on_stack.add(v)
        return v, iter(sorted(edges.get(v, ())))

    for root in nodes:
        if root in index:
            continue
        work = [discover(root)]
        while work:
            v, neighbours = work[-1]
            for w in neighbours:
                if w not in index:
                    work.append(discover(w))
                    break
                if w in on_stack:
                    lowlink[v] = min(lowlink[v], index[w])
            else:
                work.pop()
                if work:
                    parent = work[-1][0]
                    lowlink[parent] = min(lowlink[parent], lowlink[v])
                if lowlink[v] == index[v]:
                    scc: list[str] = []
                    while True:
                        w = stack.pop()
                        on_stack.discard(w)
                        scc.append(w)
                        if w == v:
                            break
                    result.append(scc)
    return result
