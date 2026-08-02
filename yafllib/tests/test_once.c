// yafl_cas_once: write-once publication into a [mutable] object's child slot.
//
// The primitive is what lets a lock-free structure grow in place. Two
// properties carry the whole design and are what these tests pin down:
//
//   * a slot goes NULL -> value exactly once; a second publish must FAIL and
//     leave the first value standing (that is what gives every caller one
//     answer, even when several threads computed different ones);
//   * the slot address comes from the vtable's POINTER MASK, not from
//     object_size arithmetic. Structs are GC_ALLOC_GRANULE-aligned and carry
//     trailing padding, so size-based offsets are wrong — the mixed-field
//     layout test below is the one that catches that.
#include "../yafl.h"
#include "../once.h"
#include <stdio.h>
#include <stdlib.h>

extern void *object_alloc_fast_raw(size_t size, bool is_mutable);

#define CHECK(cond, msg) do { if (!(cond)) { printf("FAIL: %s\n", msg); exit(1); } } while (0)

// Four trailing pointer slots, nothing else — the simple shape.
struct plain { object_t parent; object_t* c0; object_t* c1; object_t* c2; object_t* c3; };
static vtable_t PLAIN_VT = {
    .object_size = sizeof(struct plain), .array_el_size = 0,
    .object_pointer_locations = maskof(struct plain, .c0) | maskof(struct plain, .c1)
                              | maskof(struct plain, .c2) | maskof(struct plain, .c3),
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 1, .name = "once_plain", .implements_array = VTABLE_IMPLEMENTS(0),
};

// Scalars and pointers interleaved BEFORE the four slots, so the slots are
// neither at a fixed offset nor the only pointer fields. This is the layout
// that breaks any size-minus-N-words addressing scheme.
struct mixed {
    object_t  parent;
    int32_t   a;
    object_t* key;      // a pointer field that is NOT a slot
    int32_t   b;
    object_t* value;    // ditto
    object_t* c0; object_t* c1; object_t* c2; object_t* c3;
};
static vtable_t MIXED_VT = {
    .object_size = sizeof(struct mixed), .array_el_size = 0,
    .object_pointer_locations = maskof(struct mixed, .key) | maskof(struct mixed, .value)
                              | maskof(struct mixed, .c0) | maskof(struct mixed, .c1)
                              | maskof(struct mixed, .c2) | maskof(struct mixed, .c3),
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 1, .name = "once_mixed", .implements_array = VTABLE_IMPLEMENTS(0),
};

static object_t* alloc_with(vtable_t* vt, size_t size) {
    object_t* o = (object_t*)object_alloc_fast_raw(size, true);
    for (size_t i = 0; i < size / sizeof(void*); i++) ((void**)o)[i] = NULL;
    o->vtable = vt;
    return o;
}

static bool ok(object_t* r) { return int32_from_integer(r) != 0; }

static void run_tests(object_t* _unused, fun_t continuation) {
    (void)_unused; (void)continuation;
    int passed = 0;

    // --- publish into each of the four slots ---------------------------------
    {
        struct plain* p = (struct plain*)alloc_with(&PLAIN_VT, sizeof(struct plain));
        object_t* v0 = alloc_with(&PLAIN_VT, sizeof(struct plain));
        object_t* v3 = alloc_with(&PLAIN_VT, sizeof(struct plain));
        CHECK(ok(yafl_cas_once(NULL, (object_t*)p, 0, 4, v0)), "publish slot 0 failed");
        CHECK(p->c0 == v0, "slot 0 holds the wrong value");
        CHECK(p->c1 == NULL && p->c2 == NULL && p->c3 == NULL, "publish touched a neighbour");
        CHECK(ok(yafl_cas_once(NULL, (object_t*)p, 3, 4, v3)), "publish slot 3 failed");
        CHECK(p->c3 == v3, "slot 3 holds the wrong value");
        printf("  once_publishes_into_each_slot                OK\n"); passed++;
    }

    // --- write-once: the second publish must lose ----------------------------
    {
        struct plain* p = (struct plain*)alloc_with(&PLAIN_VT, sizeof(struct plain));
        object_t* first  = alloc_with(&PLAIN_VT, sizeof(struct plain));
        object_t* second = alloc_with(&PLAIN_VT, sizeof(struct plain));
        CHECK(ok(yafl_cas_once(NULL, (object_t*)p, 2, 4, first)), "first publish failed");
        CHECK(!ok(yafl_cas_once(NULL, (object_t*)p, 2, 4, second)), "second publish SUCCEEDED");
        CHECK(p->c2 == first, "the loser overwrote the winner");
        printf("  once_second_publish_loses_and_first_stands   OK\n"); passed++;
    }

    // --- slot address comes from the mask, not from object_size --------------
    {
        struct mixed* m = (struct mixed*)alloc_with(&MIXED_VT, sizeof(struct mixed));
        object_t* k = alloc_with(&PLAIN_VT, sizeof(struct plain));
        m->key = k; m->value = k;          // non-slot pointer fields, must survive
        object_t* v1 = alloc_with(&PLAIN_VT, sizeof(struct plain));
        CHECK(ok(yafl_cas_once(NULL, (object_t*)m, 1, 4, v1)), "mixed publish failed");
        CHECK(m->c1 == v1, "mixed: wrong slot written — mask addressing is broken");
        CHECK(m->c0 == NULL && m->c2 == NULL && m->c3 == NULL, "mixed: neighbour clobbered");
        CHECK(m->key == k && m->value == k, "mixed: a NON-slot pointer field was clobbered");
        printf("  once_addresses_slots_via_the_pointer_mask    OK\n"); passed++;
    }

    // --- bad arguments are refused, not crashed on -------------------------
    {
        struct plain* p = (struct plain*)alloc_with(&PLAIN_VT, sizeof(struct plain));
        object_t* v = alloc_with(&PLAIN_VT, sizeof(struct plain));
        CHECK(!ok(yafl_cas_once(NULL, NULL, 0, 4, v)),  "NULL object accepted");
        CHECK(!ok(yafl_cas_once(NULL, (object_t*)p, -1, 4, v)), "negative slot accepted");
        CHECK(!ok(yafl_cas_once(NULL, (object_t*)p, 4, 4, v)),  "out-of-range slot accepted");
        CHECK(!ok(yafl_cas_once(NULL, (object_t*)p, 0, 0, v)),  "zero nslots accepted");
        CHECK(p->c0 == NULL && p->c1 == NULL && p->c2 == NULL && p->c3 == NULL,
              "a refused publish still wrote something");
        printf("  once_refuses_bad_arguments                   OK\n"); passed++;
    }

    printf("once: %d passed, 0 failed\n", passed);
    exit(0);
}

int main(void) {
    thread_start(run_tests);
    return 1;   // unreachable: run_tests exits
}
