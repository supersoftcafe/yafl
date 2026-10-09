"""The vtable hash is NEAR-perfect, not perfect (user ruling): it re-assigns
colliding methods for a bounded number of rounds, and whatever still collides
overflows — lookups walk. So the contract is the shape of the result, not the
absence of collisions."""
from tests.testutil import TimedTestCase as TestCase

import random
from codegen.perfecthash import create_perfect_lookups


class Test(TestCase):
    def __valid(self, vtables: dict[str, list[str]], global_ids: dict[str, int], vtable_sizes: dict[str, int]):
        methods = {m for ms in vtables.values() for m in ms}
        self.assertEqual(methods, set(global_ids), "every method has an id")
        self.assertEqual(len(methods), len(set(global_ids.values())), "method ids are distinct")
        for name, methods in vtables.items():
            size = vtable_sizes[name]
            self.assertTrue(size == 0 or size.bit_count() == 1, "Vtable size is wrong")
            self.assertTrue(size >= len(methods), "Vtable size is too small")

    def test_create_perfect_lookups(self):
        vtables = {"one": ["method1", "method2"], "two": ["method2", "method3"]}
        global_ids, vtable_sizes = create_perfect_lookups(vtables)
        self.__valid(vtables, global_ids, vtable_sizes)
        for name, methods in vtables.items():
            mask = vtable_sizes[name] - 1
            self.assertEqual(len(methods), len({global_ids[m] & mask for m in methods}),
                             "a small input resolves without collisions")

    def test_big_data(self):
        NUM_METHODS = 1000
        NUM_CLASSES = 100
        MIN_METHODS_PER_VTABLE = 5
        MAX_METHODS_PER_VTABLE = 50

        rng = random.Random(20261009)    # fixed: the same input every run
        method_names = ["method_%d" % i for i in range(NUM_METHODS)]

        vtables = {}
        for i in range(NUM_CLASSES):
            class_name = "class_%d" % i
            num_methods = rng.randint(MIN_METHODS_PER_VTABLE, MAX_METHODS_PER_VTABLE)
            methods = rng.sample(method_names, num_methods)
            vtables[class_name] = methods

        global_ids, vtable_sizes = create_perfect_lookups(vtables)
        self.__valid(vtables, global_ids, vtable_sizes)
