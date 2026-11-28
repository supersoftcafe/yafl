// A heap filled with data that never promotes must not abort while dead old
// data waits for a major cycle (#134).
//
// Old garbage is freed only by a major. The rule that calls one looks at the
// old generation's GROWTH (by a quarter since the last major, or by more than
// the heap has free), so an old generation that dies without growing never
// triggers it. When the heap then fills with young data, minor cycles free
// nothing, and the allocator's reserve gate gave up after two cycles without
// progress: out of memory, with nearly half the heap dead.
//
//   1. (stepped) Allocate OLD pages' worth of immutable nodes, held from a
//      rooted chain of mutable cells, and cycle until they are promoted.
//   2. (stepped) One major, so the old generation's baseline is its size.
//   3. Drop the root: every node is old garbage, which no minor can free.
//   4. (allocation-driven, the reserve gate live) Allocate LIVE pages' worth
//      of mutable blobs, all kept. OLD + LIVE exceed the heap; LIVE alone
//      fits. The program must finish.
//
// Run with YAFL_THREADS=1.

#include "../yafl.h"
#include "../gc_stage.h"
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

extern bool gc_debug_manual_mode;
extern int  gc_debug_stage(void);
extern void gc_debug_step(void);
extern int  gc_debug_object_generation(object_t* o);   // -1 not-heap, 0 young, 1 old
extern void gc_debug_request_major(void);
extern size_t memory_total_pages(void);
extern size_t memory_count(void);

enum { ITEMS = 60 };

// Two to a page (a page holds SLOTS_PER_PAGE slots), so a page of them is
// full and never compacted.
struct node { object_t parent; char pad[SLOTS_PER_PAGE / 2 * GC_SLOT_SIZE - sizeof(object_t)]; };
static vtable_t node_vt = {
    .object_size = sizeof(struct node), .array_el_size = 0,
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 0, .name = "old_garbage_node", .implements_array = VTABLE_IMPLEMENTS(0),
};
static vtable_t blob_vt = {
    .object_size = sizeof(struct node), .array_el_size = 0,
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 1, .name = "old_garbage_blob", .implements_array = VTABLE_IMPLEMENTS(0),
};
// Mutable (never promotes): a link and ITEMS references.
struct cell { object_t parent; struct cell* next; object_t* item[ITEMS]; };
static vtable_t cell_vt = {
    .object_size = sizeof(struct cell), .array_el_size = 0,
    .object_pointer_locations = (((ptr_mask_t)1 << (ITEMS + 2)) - 1) & ~(ptr_mask_t)1,
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 1, .name = "old_garbage_cell", .implements_array = VTABLE_IMPLEMENTS(0),
};
// Filler, dropped at once: over half a page, so it never shares a node's page.
struct fill { object_t parent; char pad[12 * 1024 - sizeof(object_t)]; };
static vtable_t fill_vt = {
    .object_size = sizeof(struct fill), .array_el_size = 0,
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 0, .name = "old_garbage_fill", .implements_array = VTABLE_IMPLEMENTS(0),
};

static object_t*                _slots[2];   // [0] the old chain, [1] the live chain
static roots_declaration_func_t _prev;
static void _decl(void(*declare)(object_t**)) {
    _prev(declare); declare(&_slots[0]); declare(&_slots[1]);
}
static fun_t _exit_cont;

static void fail(const char* what, long got) {
    fprintf(stderr, "test_gc_old_garbage: FAIL %s (got %ld)\n", what, got);
    fflush(stderr);
    abort();
}

static void run_one_cycle(void) {
    int guard = 0;
    do {
        gc_debug_step();
        if (++guard > 100000) fail("cycle did not start", gc_debug_stage());
    } while (gc_debug_stage() == GC_STAGE_IDLE);
    while (gc_debug_stage() != GC_STAGE_IDLE) {
        gc_debug_step();
        if (++guard > 10000000) fail("cycle did not finish", gc_debug_stage());
    }
}

// `n` objects of `vt`, held from a fresh chain of cells rooted in `*root`.
static void __attribute__((noinline)) build(object_t** root, vtable_t* vt, size_t n) {
    struct cell* head = NULL;
    for (size_t i = 0; i < n; ) {
        struct cell* c = (struct cell*)object_create(&cell_vt);
        GC_STORE_IN(c, c->next, 1, head);
        for (int k = 0; k < ITEMS && i < n; ++k, ++i) {
            object_t* o = object_create(vt);
            GC_STORE_IN(c, c->item[k], 1, o);
        }
        head = c;
        GC_ROOT_STORE(*root, 1, (object_t*)head);
    }
}

// Old nodes still young, sampled at both ends and the middle of the chain.
static int __attribute__((noinline)) young_nodes(void) {
    int young = 0;
    size_t i = 0;
    for (struct cell* c = (struct cell*)_slots[0]; c != NULL; c = c->next, ++i)
        if (i % 16 == 0 || c->next == NULL)
            young += gc_debug_object_generation(c->item[0]) == 0;
    return young;
}

static void __attribute__((noinline)) churn(void) {
    for (int i = 0; i < 170; ++i) {
        volatile object_t* f = object_create(&fill_vt);
        (void)f;
    }
}

static void __attribute__((noinline)) scrub(void) {
    volatile uintptr_t junk[512];
    for (int i = 0; i < 512; ++i) junk[i] = (uintptr_t)(i * 2 + 1);
    __asm__ volatile("" :: "r"(junk[0]), "r"(junk[511]) : ARCH_CALLEE_SAVED_CLOBBERS);
}

static void _entrypoint(object_t* self, fun_t cont) {
    (void)self; _exit_cont = cont;
    gc_debug_manual_mode = true;
    while (gc_debug_stage() == GC_STAGE_NOT_STARTED) usleep(1000);
    while (gc_debug_stage() != GC_STAGE_IDLE) gc_debug_step();

    size_t total = memory_total_pages();
    size_t old_pages = total * 45 / 100, live_pages = total * 55 / 100;

    // (1) The old data, promoted.
    build(&_slots[0], &node_vt, old_pages * 2);
    scrub();
    int cycles = 0;
    while (young_nodes() != 0) {
        churn();
        scrub();
        run_one_cycle();
        if (++cycles > 40) fail("the old data never promoted; young samples", young_nodes());
    }

    // (2) A major: the old generation's baseline is now its whole size.
    gc_debug_request_major();
    run_one_cycle();
    if (young_nodes() != 0) fail("the major left old data young", young_nodes());
    printf("test_gc_old_garbage: %zu pages promoted after %d cycles; %zu in use of %zu\n",
           old_pages, cycles, memory_count(), total);
    fflush(stdout);

    // (3) Drop it: old garbage now.
    gc_root_overwrite(&_slots[0], 1);
    _slots[0] = NULL;
    scrub();

    // (4) Fill the heap with data that never promotes, the collector paced by
    // allocation and the reserve gate live.
    gc_debug_manual_mode = false;
    build(&_slots[1], &blob_vt, live_pages * 2);
    printf("test_gc_old_garbage: %zu more pages kept; %zu in use of %zu\n",
           live_pages, memory_count(), total);
    printf("test_gc_old_garbage: OK\n");
    fflush(stdout);
    ((void(*)(object_t*,object_t*))_exit_cont.f)(_exit_cont.o, integer_from_int32(0));
}

int main(void) {
    setenv("YAFL_HEAP_SIZE", "64m", 0);
    setenv("YAFL_GC_PROMOTE_FLOOR", "64", 0);
    _prev = add_roots_declaration_func(_decl);
    thread_start(_entrypoint);
    return 0;
}
