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

static test_object_t* create(shadow_stack_t *pss, test_object_t* p1, test_object_t* p2, int value, test_object_t* p3) {
    // Create a bunch of orphaned objects
    for (int count = 0; count < 50; ++count) {
        test_object_t* ptr = (test_object_t*)object_create(&heap, pss, &test_vtable.v);
        ptr->p1 = NULL;
        ptr->p2 = NULL;
        ptr->value = 0;
        ptr->p3 = NULL;
    }

    test_object_t* ptr = (test_object_t*)object_create(&heap, pss, &test_vtable.v);
    ptr->p1 = p1;
    ptr->p2 = p2;
    ptr->value = value;
    ptr->p3 = p3;
    return ptr;
}

static int next_id = 0;


struct ss__create_tree {
    shadow_stack_t s;
    test_object_t *p1;
    test_object_t *p2;
    test_object_t *p3;
};

static struct {
    shadow_stack_layout_t l;
    field_index_t roots[3];
} ssl__create_tree = {
        .l = {
                .pointer_count = 3
        },
        .roots = {
                indexof(struct ss__create_tree, p1),
                indexof(struct ss__create_tree, p2),
                indexof(struct ss__create_tree, p3),
        }
};



static test_object_t* create_tree(shadow_stack_t *pss, int depth) {
    struct ss__create_tree ss = {
            .s = {
                    .next = pss,
                    .layout = &ssl__create_tree.l
            },
            .p1 = NULL,
            .p2 = NULL,
            .p3 = NULL
    };

    if (depth <= 0)
        return NULL;

    // Create a branch of the tree
    ss.p1 = create_tree(&ss.s, depth-1);
    ss.p2 = create_tree(&ss.s, depth-2);
    ss.p3 = create_tree(&ss.s, depth-1);

    return create(&ss.s, ss.p1, ss.p2, ++next_id, ss.p3);
}

static void test_tree(shadow_stack_t *pss, test_object_t *obj) {
    if (obj == NULL)
        return;

    test_tree(pss, obj->p1);
    test_tree(pss, obj->p2);
    test_tree(pss, obj->p3);

    next_id++;
    assert(obj->value == next_id);
}



struct ss__complex_compaction {
    shadow_stack_t s;
    test_object_t *root1;
    test_object_t *root2;
    test_object_t *root3;
};

static struct {
    shadow_stack_layout_t l;
    field_index_t roots[3];
} ssl__complex_compaction = {
        .l = {
                .pointer_count = 3
        },
        .roots = {
                indexof(struct ss__complex_compaction, root1),
                indexof(struct ss__complex_compaction, root2),
                indexof(struct ss__complex_compaction, root3),
        }
};

static void complex_compaction() {
    object_heap_create(&heap);

    struct ss__complex_compaction ss = {
        .s = {
                .next = NULL,
                .layout = &ssl__complex_compaction.l
        },
        .root1 = NULL,
        .root2 = NULL,
        .root3 = NULL
    };

    ss.root1 = create_tree(&ss.s, 5);
    ss.root2 = create_tree(&ss.s, 7);
    ss.root3 = create_tree(&ss.s, 3);

    test_object_t *stale_copy_of_roots[3] = {ss.root1, ss.root2, ss.root3 };
    int stale_copy_of_root_ids[3] = {ss.root1->value, ss.root2->value, ss.root3->value };
    object_heap_compact2(&heap, &ss.s);

    assert(ss.root1 != stale_copy_of_roots[0]);
    assert(ss.root2 != stale_copy_of_roots[1]);
    assert(ss.root3 != stale_copy_of_roots[2]);

    assert(ss.root1->value == stale_copy_of_root_ids[0]);
    assert(ss.root2->value == stale_copy_of_root_ids[1]);
    assert(ss.root3->value == stale_copy_of_root_ids[2]);

    next_id = 0;
    test_tree(&ss.s, ss.root1);
    test_tree(&ss.s, ss.root2);
    test_tree(&ss.s, ss.root3);
}

static void simple_compaction() {
    object_heap_create(&heap);

    test_object_t* ptr3 = (test_object_t*)object_create(&heap, NULL, &test_vtable.v);
    ptr3->p1 = NULL;
    ptr3->p2 = NULL;
    ptr3->value = 33;
    ptr3->p3 = NULL;

    test_object_t* ptr2 = (test_object_t*)object_create(&heap, NULL, &test_vtable.v);
    ptr2->p1 = NULL;
    ptr2->p2 = NULL;
    ptr2->value = 22;
    ptr2->p3 = ptr3;

    test_object_t* ptr1 = (test_object_t*)object_create(&heap, NULL, &test_vtable.v);
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
    complex_compaction();
}
