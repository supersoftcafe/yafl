//
// Created by mbrown on 24/03/24.
//

#undef NDEBUG
#include <assert.h>
#include "../src/blitz.h"
#include "../src/mmap.h"
#include "../src/object.h"


struct test_object;
typedef struct test_object test_object_t;

struct test_object {
    vtable_t* vtable;
    test_object_t* p1;
    test_object_t* p2;
    int value;
    test_object_t* p3;
};

struct test_layout ;

static struct {
    layout_t l;
    field_index_t p[3];
} test_layout = {
        .l = {
                .size = sizeof(test_object_t),
                .pointer_count = 3,
        },
        .p = {
                indexof(test_object_t, p1),
                indexof(test_object_t, p2),
                indexof(test_object_t, p3)
        }
};

static struct {
    vtable_t v;
    func_t f[4];
} test_vtable = {
        .v = {
                .object_layout = &test_layout.l,
                .array_layout = NULL,
                .array_len_index = 0,
                .functions_mask = 0x3,
        },
        .f = { NULL, NULL, NULL, NULL }
};

static heap_t heap;

static test_object_t* create(test_object_t* p1, test_object_t* p2, int value, test_object_t* p3) {
    // Create a bunch of orphaned objects
    for (int count = 0; count < 50; ++count) {
        test_object_t* ptr = (test_object_t*)object_create(&heap, &test_vtable.v);
        ptr->p1 = NULL;
        ptr->p2 = NULL;
        ptr->value = 0;
        ptr->p3 = NULL;
    }

    test_object_t* ptr = (test_object_t*)object_create(&heap, &test_vtable.v);
    ptr->p1 = p1;
    ptr->p2 = p2;
    ptr->value = value;
    ptr->p3 = p3;
    return ptr;
}

static int next_id = 0;
static test_object_t* create_tree(int depth) {
    if (depth <= 0)
        return NULL;

    // Create a branch of the tree
    test_object_t *p1 = create_tree(depth-1);
    test_object_t *p2 = create_tree(depth-2);
    test_object_t *p3 = create_tree(depth-1);
    return create(p1, p2, ++next_id, p3);
}

static void test_tree(test_object_t *obj) {
    if (obj == NULL)
        return;

    test_tree(obj->p1);
    test_tree(obj->p2);
    test_tree(obj->p3);

    next_id++;
    assert(obj->value == next_id);
}

static void complex_compation() {
    object_heap_create(&heap);

    test_object_t* root1 = create_tree(5);
    test_object_t* root2 = create_tree(7);
    test_object_t* root3 = create_tree(3);

    test_object_t *roots[3] = { root1, root2, root3 };
    int root_ids[3] = { root1->value, root2->value, root3->value };
    object_heap_compact(&heap, 3, (object_t**)roots);

    assert(root1 != roots[0]);
    assert(root2 != roots[1]);
    assert(root3 != roots[2]);

    assert(roots[0]->value == root_ids[0]);
    assert(roots[1]->value == root_ids[1]);
    assert(roots[2]->value == root_ids[2]);

    next_id = 0;
    test_tree(roots[0]);
    test_tree(roots[1]);
    test_tree(roots[2]);
}

static void simple_compaction() {
    object_heap_create(&heap);

    test_object_t* ptr3 = (test_object_t*)object_create(&heap, &test_vtable.v);
    ptr3->p1 = NULL;
    ptr3->p2 = NULL;
    ptr3->value = 33;
    ptr3->p3 = NULL;

    test_object_t* ptr2 = (test_object_t*)object_create(&heap, &test_vtable.v);
    ptr2->p1 = NULL;
    ptr2->p2 = NULL;
    ptr2->value = 22;
    ptr2->p3 = ptr3;

    test_object_t* ptr1 = (test_object_t*)object_create(&heap, &test_vtable.v);
    ptr1->p1 = NULL;
    ptr1->p2 = ptr2;
    ptr1->value = 11;
    ptr1->p3 = ptr3;

    object_heap_compact(&heap, 1, (object_t **)&ptr1);

    assert(ptr1->value == 11);
    assert(ptr1->p2->value == 22);
    assert(ptr1->p3->value == 33);
    assert(ptr1->p2->p3 == ptr1->p3);
}

void test_object_heap_compact() {
    mmap_init();
    object_init(0);

    simple_compaction();
    complex_compation();
}
