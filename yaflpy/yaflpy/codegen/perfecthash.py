from __future__ import annotations

import random
from collections import defaultdict


__SIZE_MULTIPLIER = 2
__MAX_ITERATIONS = 1000


def __next_power_of_two(n):
    return 1 << (int(n) - 1).bit_length()



# Parameters
#   vtables:  Dictionary of object name to a list of function signatures
# Results
#   Dictionary of signature to global id
#   Dictionary of object name to vtable size
def create_perfect_lookups(vtables: dict[str, list[str]]) -> tuple[dict[str, int], dict[str, int]]:
    new_id = 0
    def next_method_id() -> int:
        nonlocal new_id
        id = new_id
        new_id = id + 1
        return id

    # Generate random 32-bit ids for all methods
    method_names = set(name for sublist in vtables.values() for name in sublist)
    method_ids = {name: next_method_id() for name in method_names}

    # Compute vtable sizes
    vtable_sizes = {}
    for class_name, methods in vtables.items():
        size = __next_power_of_two(len(methods) * __SIZE_MULTIPLIER)
        vtable_sizes[class_name] = size

    # Check for collisions and re-randomize minimal set of methods
    collision_found = True
    iteration = 0
    while iteration < __MAX_ITERATIONS and collision_found:
        iteration += 1
        collision_found = False
        collision_methods = set()
        conflict_graph = defaultdict(set)

        # Build conflict graph
        for class_name, methods in vtables.items():
            mask = vtable_sizes[class_name] - 1
            slots = {}
            for method in methods:
                index = method_ids[method] & mask
                if index not in slots:
                    slots[index] = method
                else:
                    collision_found = True
                    collision_methods.update([method, slots[index]])
                    # Add edge in conflict graph
                    conflict_graph[method].add(slots[index])
                    conflict_graph[slots[index]].add(method)

        if collision_found:
            print(f"Iteration {iteration}: {len(collision_methods)} collisions found.")

            # Approximate minimal vertex cover using a greedy algorithm
            cover = set()
            edges = set((min(m1, m2), max(m1, m2)) for m1, neighbors in conflict_graph.items() for m2 in neighbors)
            while edges:
                # Select the node with the highest degree
                degree_count = {method: len(conflict_graph[method]) for method in conflict_graph}
                method = max(degree_count, key=degree_count.get)
                cover.add(method)
                # Remove all edges connected to this method
                for neighbor in conflict_graph[method]:
                    conflict_graph[neighbor].remove(method)
                    edges.discard((min(method, neighbor), max(method, neighbor)))
                conflict_graph[method] = set()
                edges = set((min(m1, m2), max(m1, m2)) for m1, neighbors in conflict_graph.items() for m2 in neighbors if neighbors)

            # Re-randomize IDs of methods in the cover set
            for method in cover:
                method_ids[method] = next_method_id()

    print(f"All collisions resolved after {iteration} iterations.")
    return method_ids, vtable_sizes

