//
// Created by mbrown on 26/03/24.
//


#undef NDEBUG
#include <assert.h>
#include "../src/mmap.h"
#include "../src/object.h"




struct test_object;
typedef struct test_object test_object_t;
struct test_object {
    object_t parent;
    uint32_t call_count1;
    uint32_t call_count2;
    uint32_t call_count3;
};

static void function1(test_object_t *o) {
    o->call_count1 ++;
}
static void function2(test_object_t *o) {
    o->call_count2 ++;
}
static void function3(test_object_t *o) {
    o->call_count3 ++;
}

static layout_t layout = {
        .size = sizeof(test_object_t),
        .pointer_count = 0,
        .pointer_offsets = { }
};

enum {
    FUNC1_ID = 889832,
    FUNC2_ID = 992,
    FUNC3_ID = 9198221
};

static struct {
    vtable_t v;
    vtable_entry_t e[4];
} vtable = {
        .v = {
                .object_layout = &layout,
                .array_layout = NULL,
                .array_len_offset = 0,
                .functions_mask = 0, // Because this isn't a proper hash map, always start at index 0
        },
        .e = {
                { FUNC1_ID, (func_t)function1 },
                { FUNC2_ID, (func_t)function2 },
                { FUNC3_ID, (func_t)function3 },
                { 0, NULL }
        }
};



void test_object_virtual_function() {
    mmap_init();
    object_init();

    heap_t heap;
    object_heap_create(&heap);
    test_object_t *obj = (test_object_t*) object_create(&heap, &vtable.v);

    func_t func1 = object_function_lookup(&obj->parent, FUNC1_ID);
    func_t func2 = object_function_lookup(&obj->parent, FUNC2_ID);
    func_t func3 = object_function_lookup(&obj->parent, FUNC3_ID);

    assert(obj->call_count1 == 0);
    assert(obj->call_count2 == 0);
    assert(obj->call_count3 == 0);

    func1(obj);

    assert(obj->call_count1 == 1);
    assert(obj->call_count2 == 0);
    assert(obj->call_count3 == 0);

    func2(obj);

    assert(obj->call_count1 == 1);
    assert(obj->call_count2 == 1);
    assert(obj->call_count3 == 0);

    func3(obj);

    assert(obj->call_count1 == 1);
    assert(obj->call_count2 == 1);
    assert(obj->call_count3 == 1);
}

