//
// Created by mbrown on 23/03/24.
//

#undef NDEBUG
#include <assert.h>
#include "../src/mmap.h"
#include "../src/object.h"



typedef struct {
    vtable_t* vtable;
    uint32_t value;
} test_object_t;

static vtable_t test_vtable = {
    .object_size = sizeof(test_object_t),
    .array_el_size = 0,
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0,
    .array_len_index = 0,
    .functions_mask = 0,
    .functions = {  } };


void test_object_create() {
    mmap_init();
    object_init();

    heap_t heap;

    object_heap_create(&heap);
    object_heap_select(&heap);

    test_object_t* obj = object_create(test_object_t);
    obj->vtable = &test_vtable;
    obj->value = 123456;

    object_heap_compact(&heap, 1, (object_t**)&obj);
    assert(obj->value == 123456);

    object_heap_destroy(&heap);
}
