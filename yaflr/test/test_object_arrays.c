//
// Created by mbrown on 24/03/24.
//

#undef NDEBUG
#include <assert.h>
#include "../src/mmap.h"
#include "../src/object.h"



struct test_object;
typedef struct test_object test_object_t;

typedef struct test_array {
    uint32_t value1;
    test_object_t *p;
    uint32_t value2;
} test_array_t;

struct test_object {
    vtable_t* vtable;
    uint32_t length;
    test_array_t array[0];
};

struct test_layout ;

static struct {
    layout_t l;
    uint32_t p[0];
} test_layout = {
        .l = {
                .size = sizeof(test_object_t),
                .pointer_count = 0,
        },
        .p = { }
};

static struct {
    layout_t l;
    uint32_t p[1];
} test_array_layout = {
        .l = {
                .size = sizeof(test_array_t),
                .pointer_count = 1,
        },
        .p = { offsetof(test_array_t, p) }
};


static struct {
    vtable_t v;
    func_t f[4];
} test_vtable = {
        .v = {
                .object_layout = &test_layout.l,
                .array_layout = &test_array_layout.l,
                .array_len_offset = offsetof(test_object_t, length),
                .functions_mask = 0x3,
        },
        .f = { NULL, NULL, NULL, NULL }
};



static heap_t heap;

static test_object_t *create_child(uint32_t value) {
    // Create some garbage
    for (int index = 0; index < 100; ++index)
        object_create_array(&heap, &test_vtable.v, 0);

    // Then create the one we want to return
    // It has elements, but they are NULL
    test_object_t * obj = (test_object_t*)object_create_array(&heap, &test_vtable.v, 2);
    assert(obj->length == 2);
    assert(obj->array[0].p == NULL);
    assert(obj->array[1].p == NULL);

    for (int index = 0; index < 2; ++index)
        obj->array[index].value1 = value;

    return obj;
}

void test_object_arrays() {
    mmap_init();
    object_init();

    object_heap_create(&heap);

    uint32_t length = 10;
    test_object_t *obj = (test_object_t*)object_create_array(&heap, &test_vtable.v, length);
    assert(length == obj->length);
    for (int index = 0; index < obj->length; ++index)
        obj->array[index].p = create_child(index);

    object_heap_compact(&heap, 1, (object_t**)&obj);

    for (int index = 0; index < obj->length; ++index)
        assert(index == obj->array[index].p->array[0].value1);
}
