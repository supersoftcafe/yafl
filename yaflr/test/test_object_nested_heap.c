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

static struct {
    layout_t l;
    field_index_t o[1];
} test_layout = {
        .l = {
                .size = sizeof(test_object_t),
                .pointer_count = 1
        },
        .o = {
                indexof(test_object_t, pointer)
        }
};

static vtable_t test_vtable = {
        .object_layout = &test_layout.l,
        .array_layout = NULL,
        .array_len_index = 0,
        .functions_mask = 0,
        .functions = {  } };


static void create_objects(heap_t* heap, int count) {
    while (--count >= 0) {
        test_object_t *o = (test_object_t*)object_create(heap, NULL, &test_vtable);
        o->pointer = NULL;
    }
}

void test_object_nested_heap() {
    mmap_init();
    object_init(1);

    heap_t heap1;
    object_heap_create(&heap1);
    create_objects(&heap1, 50);
    test_object_t *object1 = (test_object_t*) object_create(&heap1, NULL, &test_vtable);
    object1->pointer = NULL;
    create_objects(&heap1, 50);

    heap_t heap2;
    object_heap_create(&heap2);
    create_objects(&heap2, 50);
    test_object_t *object2 = (test_object_t*) object_create(&heap2, NULL, &test_vtable);
    object2->pointer = object1;
    create_objects(&heap2, 50);

    assert(heap1.object_count == 101);
    assert(heap2.object_count == 101);

    object_heap_compact(&heap2, 1, (object_t**)&object2);

    assert(heap1.object_count == 101);      // heap1 is untouched
    assert(heap2.object_count == 1);        // heap2 is compacted
    assert(object2->pointer == object1);    // object1 hasn't moved...  check this

    object_heap_append(&heap1, &heap2);

    assert(heap1.object_count == 102);      // heap1 has grown

    object_t *roots[2] = { (object_t*)object1, (object_t*)object2 };
    object_heap_compact(&heap1, 2, roots);
    object1 = (test_object_t*)roots[0];
    object2 = (test_object_t*)roots[1];

    assert(heap1.object_count == 2);        // heap1 is compacted
    assert(object2->pointer == object1);    // still pointing at object1, which has probably moved
}
