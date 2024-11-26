//
// Created by mbrown on 24/03/24.
//

#undef NDEBUG
#include <assert.h>
#include <string.h>
#include "../src/blitz.h"
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


static struct {
    vtable_t v;
    func_t f[4];
} test_vtable = {
    .v = {
        .object_size = offsetof(test_object_t, array[0]),
        .array_el_size = sizeof(test_array_t),
        .object_pointer_locations = 0,
        .array_el_pointer_locations = 1<<indexof(test_array_t, p),
        .array_len_index = indexof(test_object_t, length),
        .functions_mask = 0x3,
    },
    .f = { NULL, NULL, NULL, NULL }
};



static heap_t heap;

static test_object_t* create(uint32_t length) {
    test_object_t* obj = object_create_array(test_object_t, array, length);
    obj->vtable = &test_vtable.v;
    obj->length = length;
    memset(obj->array, 0, sizeof(test_array_t) * length);
    return obj;
}

static test_object_t* create_child(uint32_t value) {
    // Create some garbage
    for (int index = 0; index < 100; ++index) {
        create(0);
    }

    // Then create the one we want to return
    // It has elements, but they are NULL
    test_object_t* obj = create(2);
    for (uint32_t index = 0; index < 2; ++index) {
        obj->array[index].value1 = value;
    }

    return obj;
}

void test_object_arrays() {
    mmap_init();
    object_init();

    object_heap_create(&heap);
    object_heap_select(&heap);

    uint32_t length = 10;
    test_object_t *obj = create(length);
    for (int index = 0; index < obj->length; ++index) {
        obj->array[index].p = create_child(index);
    }

    object_heap_compact(&heap, &obj, NULL);

    for (int index = 0; index < obj->length; ++index) {
        assert(index == obj->array[index].p->array[0].value1);
    }
}

