//
// Created by mbrown on 26/03/24.
//

#undef NDEBUG
#include <assert.h>
#include "../src/mmap.h"
#include "../src/object.h"
#include "../src/fiber.h"
#include <stdlib.h>
#include <unistd.h>


static void func0(int* flags) { flags[0] = 10; }
static void func1(int* flags) { flags[1] = 11; }
static void func2(int* flags) { flags[2] = 12; }
static void func3(int* flags) { flags[3] = 13; }
static void func4(int* flags) { flags[4] = 14; }


static void simple_parallel() {
    int flags[5] = { 0 };
    func_t funcs[5] = { (func_t)func0, (func_t)func1, (func_t)func2, (func_t)func3, (func_t)func4 };

    fiber_parallel(flags, funcs, 5);

    assert( flags[0] == 10 );
    assert( flags[1] == 11 );
    assert( flags[2] == 12 );
    assert( flags[3] == 13 );
    assert( flags[4] == 14 );
}


struct some_integers {
    object_t o;
    uint32_t i1, i2, i3, i4;
};

static layout_t some_integers_layout = {
        .size = sizeof(struct some_integers),
                .pointer_count = 0
};

static vtable_t some_integers_vtable = {
        .object_layout = &some_integers_layout,
        .array_layout = NULL,
        .array_len_offset = 0,
        .functions_mask = 0
};

struct some_objects {
    object_t o;
    object_t *o1, *o2, *o3, *o4;
};

static struct {
    layout_t l;
    uint32_t o[4];
} some_objects_layout = {
        .l = {
                .size = sizeof(struct some_objects),
                .pointer_count = 4
        },
        .o = {
                offsetof(struct some_objects, o1),
                offsetof(struct some_objects, o2),
                offsetof(struct some_objects, o3),
                offsetof(struct some_objects, o4)
        }
};

static vtable_t some_objects_vtable = {
        .object_layout = &some_objects_layout,
        .array_layout = NULL,
        .array_len_offset = 0,
        .functions_mask = 0
};

struct parameter_container {
    int depth;
    object_t *o1, *o2, *o3, *o4;
};


static object_t *massively_parallel_worker(int depth);

static void massively_parallel_enter1(struct parameter_container *p) {
    p->o1 = massively_parallel_worker(p->depth);
    fiber_object_heap_compact(1, &p->o1);
}

static void massively_parallel_enter2(struct parameter_container *p) {
    p->o2 = massively_parallel_worker(p->depth);
    fiber_object_heap_compact(1, &p->o2);
}

static void massively_parallel_enter3(struct parameter_container *p) {
    p->o3 = massively_parallel_worker(p->depth);
    fiber_object_heap_compact(1, &p->o3);
}

static void massively_parallel_enter4(struct parameter_container *p) {
    p->o4 = massively_parallel_worker(p->depth);
    fiber_object_heap_compact(1, &p->o4);
}

static func_t massively_parallel_functions[4] = {
        (func_t)massively_parallel_enter1,
        (func_t)massively_parallel_enter2,
        (func_t)massively_parallel_enter3,
        (func_t)massively_parallel_enter4
};

static object_t *massively_parallel_worker(int depth) {
    if (depth <= 0) {
        struct some_integers *r = (struct some_integers *)fiber_object_create(&some_integers_vtable);
        r->i1 = 1;
        r->i2 = 2;
        r->i3 = 3;
        r->i4 = 4;
        return &r->o;
    } else {
        struct parameter_container p = { .depth = depth-1 };
        fiber_parallel(&p, massively_parallel_functions, 4);

        struct some_objects *r = (struct some_objects *)fiber_object_create(&some_objects_vtable);
        r->o1 = p.o1;
        r->o2 = p.o2;
        r->o3 = p.o3;
        r->o4 = p.o4;
        return &r->o;
    }
}

static void massively_parallel() {
    massively_parallel_worker(1);
}


static void start(void* _) {
    simple_parallel();
    // massively_parallel();
    exit(0);
}

void test_fiber_parallel() {
    mmap_init();
    object_init();
    fiber_start(start, NULL);
    sleep(1000000);
}