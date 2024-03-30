//
// Created by mbrown on 23/03/24.
//

#include <string.h>

void test_mmap_alloc();
void test_mmap_protect();
void test_object_create();
void test_object_heap_compact();
void test_object_arrays();
void test_object_nested_heap();
void test_object_virtual_function();
void test_fiber_parallel();
void test_lists();

int main(int argc, char** argv) {
    if (strcmp(argv[1], "mmap_alloc") == 0)
        test_mmap_alloc();

    else if (strcmp(argv[1], "mmap_protect") == 0)
        test_mmap_protect();

    else if (strcmp(argv[1], "object_create") == 0)
        test_object_create();

    else if (strcmp(argv[1], "object_heap_compact") == 0)
        test_object_heap_compact();

    else if (strcmp(argv[1], "object_arrays") == 0)
        test_object_arrays();

    else if (strcmp(argv[1], "object_nested_heap") == 0)
        test_object_nested_heap();

    else if (strcmp(argv[1], "object_virtual_function") == 0)
        test_object_virtual_function();

    else if (strcmp(argv[1], "fiber_parallel") == 0)
        test_fiber_parallel();

    else if (strcmp(argv[1], "lists") == 0)
        test_lists();

    else
        return 1;

    return 0;
}