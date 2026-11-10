/*
 * Compaction keeps an in-place array's slot rounding as capacity.
 *
 * An array built in place (vtable array_cap_offset) is copied by compaction
 * at its `length`, rounded up to whole slots. The copy's capacity must be
 * what that rounded size holds — not `length` — so a moved buffer can still
 * grow in place into the rounding; and the elements in the rounding must be
 * zero, because an in-place element write runs the write barrier, which reads
 * the slot's prior value as a pointer.
 *
 *   B: 1-byte elements, length 5 → 16 + 5 = 21 bytes, one 32-byte slot:
 *      the copy holds 16 elements.
 *   P: pointer elements, length 1 → 16 + 8 = 24 bytes, one slot: the copy
 *      holds 2 elements, and element 1 is NULL.
 *
 * Both start with capacity == length (what an earlier copy left), are rooted,
 * and are buried in dropped filler so their page is sparse and compacts.
 * Single-stepped (gc_debug_manual_mode); run with YAFL_THREADS=1.
 */

#include "../yafl.h"
#include <stdio.h>
#include <stdlib.h>
#include <stddef.h>
#include <unistd.h>

extern bool gc_debug_manual_mode;
extern int  gc_debug_stage(void);
extern void gc_debug_step(void);
extern int  gc_debug_object_state(object_t* o);        // 0 not-heap, 1 live, 2 reclaimed

enum { ST_IDLE = 1 };

struct bytes { object_t parent; int32_t length; int32_t capacity; uint8_t items[]; };
static vtable_t bytes_vt = {
    .object_size = offsetof(struct bytes, items), .array_el_size = sizeof(uint8_t),
    .object_pointer_locations = 0, .array_el_pointer_locations = 0,
    .functions_mask = 0, .array_len_offset = offsetof(struct bytes, length),
    .array_cap_offset = offsetof(struct bytes, capacity),
    .is_mutable = 0, .name = "cap_bytes", .implements_array = VTABLE_IMPLEMENTS(0),
};

struct ptrs { object_t parent; int32_t length; int32_t capacity; object_t* items[]; };
static vtable_t ptrs_vt = {
    .object_size = offsetof(struct ptrs, items), .array_el_size = sizeof(object_t*),
    .object_pointer_locations = 0, .array_el_pointer_locations = maskof(object_t*, ),
    .functions_mask = 0, .array_len_offset = offsetof(struct ptrs, length),
    .array_cap_offset = offsetof(struct ptrs, capacity),
    .is_mutable = 0, .name = "cap_ptrs", .implements_array = VTABLE_IMPLEMENTS(0),
};

struct leaf { object_t parent; intptr_t id; char pad[32 - sizeof(object_t) - sizeof(intptr_t)]; };
static vtable_t leaf_vt = {
    .object_size = sizeof(struct leaf), .array_el_size = 0,
    .object_pointer_locations = 0, .array_el_pointer_locations = 0,
    .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 0, .name = "cap_leaf", .implements_array = VTABLE_IMPLEMENTS(0),
};

enum { LEAF_ID = 0x1eaf };

static object_t*                _slots[2];   // B, P
static roots_declaration_func_t _prev;
static void _decl(void(*declare)(object_t**)) {
    _prev(declare); declare(&_slots[0]); declare(&_slots[1]);
}

/* Plain globals are not roots and not scanned: safe parking for addresses. */
static volatile uintptr_t g_B, g_P;
static fun_t _exit_cont;

static void fail(const char* what, long got) {
    fprintf(stderr, "test_gc_array_capacity: FAIL %s (got %ld)\n", what, got);
    fflush(stderr);
    abort();
}

static void run_one_cycle(void) {
    int guard = 0;
    do {
        gc_debug_step();
        if (++guard > 100000) fail("cycle did not start", gc_debug_stage());
    } while (gc_debug_stage() == ST_IDLE);
    while (gc_debug_stage() != ST_IDLE) {
        gc_debug_step();
        if (++guard > 1000000) fail("cycle did not finish", gc_debug_stage());
    }
}

/* Own frame, so no address lingers for the conservative stack scan. */
static void __attribute__((noinline)) create_and_bury(void) {
    object_t* volatile leaf = object_create(&leaf_vt);
    ((struct leaf*)leaf)->id = LEAF_ID;

    object_t* volatile b = array_create(&bytes_vt, 5, false);
    for (int i = 0; i < 5; ++i) ((struct bytes*)b)->items[i] = (uint8_t)(0xa0 + i);
    ((struct bytes*)b)->capacity = 5;
    GC_ROOT_STORE(_slots[0], 1, b);
    g_B = (uintptr_t)b;

    object_t* volatile p = array_create(&ptrs_vt, 1, false);
    GC_FILL_STORE_IN(p, ((struct ptrs*)p)->items[0], 1, leaf);
    ((struct ptrs*)p)->capacity = 1;
    GC_ROOT_STORE(_slots[1], 1, p);
    g_P = (uintptr_t)p;

    leaf = NULL; b = NULL; p = NULL;
    for (int i = 0; i < 460; ++i) {
        volatile object_t* f = object_create(&leaf_vt);
        (void)f;
    }
}

static void __attribute__((noinline)) scrub(void) {
    volatile uintptr_t junk[512];
    for (int i = 0; i < 512; ++i) junk[i] = (uintptr_t)(i * 2 + 1);
    __asm__ volatile("" :: "r"(junk[0]), "r"(junk[511]) : ARCH_CALLEE_SAVED_CLOBBERS);
}

static bool __attribute__((noinline)) both_moved(void) {
    return (uintptr_t)object_resolve(_slots[0]) != g_B
        && (uintptr_t)object_resolve(_slots[1]) != g_P;
}

static void __attribute__((noinline)) check_copies(void) {
    struct bytes* b = (struct bytes*)object_resolve(_slots[0]);
    if (b->length != 5) fail("bytes: length changed", b->length);
    if (b->capacity != 16) fail("bytes: copy capacity is not its slot rounding", b->capacity);
    for (int i = 0; i < 5; ++i)
        if (b->items[i] != (uint8_t)(0xa0 + i)) fail("bytes: element lost", i);

    struct ptrs* p = (struct ptrs*)object_resolve(_slots[1]);
    if (p->length != 1) fail("ptrs: length changed", p->length);
    if (p->capacity != 2) fail("ptrs: copy capacity is not its slot rounding", p->capacity);
    if (p->items[1] != NULL) fail("ptrs: the rounding element is not zero", (long)(uintptr_t)p->items[1]);
    object_t* leaf = object_resolve(p->items[0]);
    if (gc_debug_object_state(leaf) != 1) fail("ptrs: element 0 reclaimed", gc_debug_object_state(leaf));
    if (((struct leaf*)leaf)->id != LEAF_ID) fail("ptrs: element 0 reads another object", ((struct leaf*)leaf)->id);
}

static void _entrypoint(object_t* self, fun_t cont) {
    (void)self; _exit_cont = cont;
    gc_debug_manual_mode = true;
    while (gc_debug_stage() == 0) usleep(1000);   // wait for the collector
    while (gc_debug_stage() != ST_IDLE) gc_debug_step();

    create_and_bury();
    scrub();
    for (int cycles = 0; !both_moved(); ++cycles) {
        if (cycles > 8) fail("the arrays' page never compacted: the test did not reach its case", cycles);
        run_one_cycle();
        scrub();
    }
    check_copies();
    printf("test_gc_array_capacity: OK\n");
    fflush(stdout);
    ((void(*)(object_t*,object_t*))_exit_cont.f)(_exit_cont.o, integer_from_int32(0));
}

int main(void) {
    _prev = add_roots_declaration_func(_decl);
    thread_start(_entrypoint);
    return 0;
}
