from unittest import TestCase

import random
from codegen.perfecthash import create_perfect_lookups


class Test(TestCase):
    def __no_collisions(self, vtables: dict[str, list[str]], global_ids: dict[str, int], vtable_sizes: dict[str, int]):
        for name, methods in vtables.items():
            size = vtable_sizes[name]
            self.assertTrue(size == 0 or size.bit_count() == 1, "Vtable size is wrong")
            self.assertTrue(size >= len(methods), "Vtable size is too small")

            mask = size - 1
            ids = set(global_ids[method] & mask for method in methods)
            self.assertEqual(len(methods), len(ids), "Vtable collisions detected")

    def test_create_perfect_lookups(self):
        vtables = {"one": ["method1", "method2"], "two": ["method2", "method3"]}
        global_ids, vtable_sizes = create_perfect_lookups(vtables)
        self.__no_collisions(vtables, global_ids, vtable_sizes)

    def test_big_data(self):
        NUM_METHODS = 1000
        NUM_CLASSES = 100
        MIN_METHODS_PER_VTABLE = 5
        MAX_METHODS_PER_VTABLE = 50

        method_names = ["method_%d" % i for i in range(NUM_METHODS)]

        vtables = {}
        for i in range(NUM_CLASSES):
            class_name = "class_%d" % i
            num_methods = random.randint(MIN_METHODS_PER_VTABLE, MAX_METHODS_PER_VTABLE)
            methods = random.sample(method_names, num_methods)
            vtables[class_name] = methods

        global_ids, vtable_sizes = create_perfect_lookups(vtables)
        self.__no_collisions(vtables, global_ids, vtable_sizes)


