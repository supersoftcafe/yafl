from __future__ import annotations

from itertools import chain, groupby
from typing import Iterable, Callable, Iterator


def flatten(lst):
    return list(chain.from_iterable(lst))

def cast[_T](the_type: type[_T], the_object: object|None) -> _T:
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
