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

static layout_t test_layout = {
        .size = sizeof(test_object_t),
        .pointer_count = 0 };

static vtable_t test_vtable = {
        .object_layout = &test_layout,
        .array_layout = NULL,
        .array_len_index = 0,
        .functions_mask = 0,
        .functions = {  } };


void test_object_create() {
    mmap_init();
    object_init(0);

    heap_t heap;

    object_heap_create(&heap);
    test_object_t* obj = (test_object_t*)object_create(&heap, NULL, &test_vtable);
    obj->value = 123456;
    object_heap_compact(&heap, 1, (object_t**)&obj);
    assert(obj->value == 123456);
    object_heap_destroy(&heap);
}
