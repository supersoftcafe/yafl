// Virtual dispatch through a vtable whose method ids COLLIDE.
//
// The vtable hash is near-perfect by design, not perfect: create_perfect_lookups
// re-numbers colliding methods for a bounded number of rounds and may stop with
// a few collisions left, and the code generator then places each overflowing
// entry in the next free slot. Lookup therefore starts at the hashed slot and
// walks on until the ids match — exactly as object_lookup_vtable does. The
// inline vtable_lookup once assumed a perfect table and read only the hashed
// slot, so a collided method answered with its neighbour's function (or, in a
// debug build, tripped its assert) — found by a generic class whose five
// instantiations implement one interface.
#include "../yafl.h"
#include <stdio.h>
#include <stdlib.h>

static void method_a(void) {}
static void method_b(void) {}
static void method_c(void) {}

// Ids 1 and 5 share slot 1 under a 4-slot mask; 5 overflows into slot 2, as
// the generator places it. Id 2 hashes to slot 2 as well, so it too must walk
// past the overflow to its own place.
#define ID_A rotate_function_id(1)
#define ID_B rotate_function_id(5)
#define ID_C rotate_function_id(2)

static vtable_t* const COLLIDING_VT = VTABLE_DECLARE(5){
    .object_size = sizeof(object_t),
    .functions_mask = rotate_function_id(3),
    .name = "colliding",
    .lookup = {
        { .i = -1,   .f = (void*)&abort_on_vtable_lookup },
        { .i = ID_A, .f = (void*)&method_a },
        { .i = ID_B, .f = (void*)&method_b },
        { .i = ID_C, .f = (void*)&method_c },
        { .i = -1,   .f = (void*)&abort_on_vtable_lookup } },
};

#define CHECK(cond, msg) do { if (!(cond)) { printf("FAIL: %s\n", msg); exit(1); } } while (0)

int main(void) {
    object_t object = { .vtable = vtable_tag(COLLIDING_VT) };
    printf("=== vtable lookup with collisions ===\n");
    CHECK(vtable_lookup(&object, ID_A).f == (void*)&method_a, "hashed slot");
    CHECK(vtable_lookup(&object, ID_B).f == (void*)&method_b, "overflowed slot");
    CHECK(vtable_lookup(&object, ID_C).f == (void*)&method_c, "slot displaced by overflow");
    CHECK(object_lookup_vtable(&object, ID_B).f == (void*)&method_b, "out-of-line lookup agrees");
    printf("PASS\n");
    return 0;
}
