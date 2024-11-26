//
// Created by mbrown on 26/03/24.
//


#undef NDEBUG
#include <assert.h>
#include "../src/blitz.h"
#include "../src/mmap.h"
#include "../src/object.h"


struct test_object;
typedef struct test_object test_object_t;

struct test_object{
    vtable_t* vtable;
    test_object_t* pointer;
};

static vtable_t test_vtable = {
    .object_size = sizeof(test_object_t),
    .array_el_size = sizeof(test_object_t*),
    .object_pointer_locations = 1<<indexof(test_object_t, pointer),
    .array_el_pointer_locations = 0,
    .array_len_index = 0,
    .functions_mask = 0,
    .functions = {  }
};

static test_object_t* create(test_object_t* pointer) {
    test_object_t *o = object_create(test_object_t);
    o->vtable = &test_vtable;
    o->pointer = pointer;
    return o;
}

static void create_objects(int count) {
    while (--count >= 0) {
        create(NULL);
    }
}

void test_object_nested_heap() {
    mmap_init();
    object_init();

    heap_t heap1;
    object_heap_create(&heap1);
    object_heap_select(&heap1);
    create_objects(50);
    test_object_t *object1 = create(NULL);
    create_objects(50);

    heap_t heap2;
    object_heap_create(&heap2);
    object_heap_select(&heap2);
    create_objects(50);
    test_object_t *object2 = create(object1);
    object2->pointer = object1;
    create_objects(50);

    object_heap_compact(&heap2, &object2, NULL);

    assert(object2->pointer == object1);    // object1 hasn't moved...  check this

    object_heap_append(&heap1, &heap2);

    object_heap_compact(&heap1, &object1, &object2, NULL);

    assert(object2->pointer == object1);    // still pointing at object1, which has probably moved
}
