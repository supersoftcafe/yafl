cmake_minimum_required(VERSION 3.27)
project(yaflr C)

set(CMAKE_C_STANDARD 17)

add_library(yaflr STATIC src/library.c
        src/fiber.c
        src/mmap.h
        src/mmap.c
        src/blitz.c
        src/settings.h
        src/object.h
        src/object.c
        src/threads.h
        src/platform.c
        src/platform.h
        src/lists.c
        src/lists.h
)

add_executable(yaflr_test test/test.c
        test/test_mmap_alloc.c
        test/test_mmap_protect.c
        test/test_object_create.c
        test/test_object_heap_compact.c
        test/test_object_arrays.c
        test/test_object_nested_heap.c
        test/test_object_virtual_function.c
        test/test_fiber_parallel.c
        test/test_lists.c)
target_link_libraries(yaflr_test PRIVATE yaflr)

enable_testing()

add_test(NAME test_mmap_alloc COMMAND $<TARGET_FILE:yaflr_test> mmap_alloc)
add_test(NAME test_mmap_protect COMMAND $<TARGET_FILE:yaflr_test> mmap_protect)
add_test(NAME test_object_create COMMAND $<TARGET_FILE:yaflr_test> object_create)
add_test(NAME test_object_heap_compact COMMAND $<TARGET_FILE:yaflr_test> object_heap_compact)
add_test(NAME test_object_arrays COMMAND $<TARGET_FILE:yaflr_test> object_arrays)
add_test(NAME test_object_nested_heap COMMAND $<TARGET_FILE:yaflr_test> object_nested_heap)
add_test(NAME test_object_virtual_function COMMAND $<TARGET_FILE:yaflr_test> object_virtual_function)
add_test(NAME test_fiber_parallel COMMAND $<TARGET_FILE:yaflr_test> fiber_parallel)
add_test(NAME test_lists COMMAND $<TARGET_FILE:yaflr_test> lists)
