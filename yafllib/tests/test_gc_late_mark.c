// Deterministic, single-stepped test: a mutator's mark that lands after
// marking has closed must not hide a page from the next cycle (#134).
//
// A barrier reads gc_write_barrier_requested inline and marks out of line, so
// one that read the flag up just before marking closed can set its mark bit
// later — after its page has been pruned and its bitmaps reset. The bit then
// outlives the cycle. In the next one a mark of the same object finds the bit
// already set and leaves the page as it is: never handed over, never scanned,
// pruned as if dead but for that one bit, which keeps the object while its
// children, traced by no one, are freed under it (test_gc_mesh, 1 run in ~100
// with the soak's hot settings).
//
//   1. R (a declared root) -> H (mutable, a page to itself) -> C (a leaf, on
//      another page). A full cycle runs: all three live.
//   2. Marking closed and the cycle over, a mutator's barrier marks H (the
//      straggler, by hand).
//   3. The next cycle runs. C must still be live.
//
// Run with YAFL_THREADS=1; uses gc_debug_manual_mode. Builds its own object.c
// with YAFL_GC_HANDOFF_PROBE, for the test helpers.

#include "../yafl.h"
#include "../gc_stage.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

extern bool gc_debug_manual_mode;
extern int  gc_debug_stage(void);
extern void gc_debug_step(void);
extern int  gc_debug_object_state(object_t* o);   // 0 not-heap, 1 live, 2 reclaimed
extern void gc_test_mutator_mark(object_t* o);

// Mutable: never relocated, so the addresses stay stable. H fills a page, so
// no other object's mark can hand its page over.
struct holder { object_t parent; object_t* child; char pad[MAX_OBJECT_SIZE - sizeof(object_t) - sizeof(object_t*)]; };
static vtable_t holder_vt = {
    .object_size = sizeof(struct holder), .array_el_size = 0,
    .object_pointer_locations = maskof(struct holder, .child),
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 1, .name = "late_mark_holder", .implements_array = VTABLE_IMPLEMENTS(0),
};
struct leaf { object_t parent; char pad[64]; };
static vtable_t leaf_vt = {
    .object_size = sizeof(struct leaf), .array_el_size = 0,
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 1, .name = "late_mark_leaf", .implements_array = VTABLE_IMPLEMENTS(0),
};

static object_t*                _slots[1];
static roots_declaration_func_t _prev;
static void _decl(void(*declare)(object_t**)) { _prev(declare); declare(&_slots[0]); }

static volatile uintptr_t g_H, g_C;   // where the collector does not look
static fun_t _exit_cont;

void gc_test_handoff_probe(void);
void gc_test_handoff_probe(void) {}   // the shared probe build's hook: unused here

static void fail(const char* what, int got) {
    fprintf(stderr, "test_gc_late_mark: FAIL %s (got %d)\n", what, got);
    fflush(stderr);
    abort();
}

static void run_one_cycle(void) {
    int guard = 0;
    while (gc_debug_stage() == GC_STAGE_IDLE) {
        if (++guard > 100000) fail("cycle did not start", gc_debug_stage());
        gc_debug_step();
    }
    while (gc_debug_stage() != GC_STAGE_IDLE) {
        if (++guard > 1000000) fail("cycle did not finish", gc_debug_stage());
        gc_debug_step();
    }
}

// In a frame of its own, so no copy of an address lingers for the
// conservative stack scan; scrub() overwrites what the frame left.
static void __attribute__((noinline)) build(void) {
    object_t* h = object_create(&holder_vt);
    object_t* c = object_create(&leaf_vt);
    memset(((struct leaf*)c)->pad, 0x5a, sizeof ((struct leaf*)c)->pad);
    GC_STORE_IN(h, ((struct holder*)h)->child, 1, c);
    gc_root_overwrite(&_slots[0], 1);
    _slots[0] = h;
    gc_root_publish(&_slots[0], 1);
    g_H = (uintptr_t)h;
    g_C = (uintptr_t)c;
}

static void __attribute__((noinline)) scrub(void) {
    volatile uintptr_t junk[2048];
    for (int i = 0; i < 2048; ++i) junk[i] = (uintptr_t)(i * 2 + 1);
    __asm__ volatile("" :: "r"(junk[0]), "r"(junk[2047]) : ARCH_CALLEE_SAVED_CLOBBERS);
}

static void __attribute__((noinline)) straggler(void) {
    gc_test_mutator_mark((object_t*)g_H);
}

static int __attribute__((noinline)) state(volatile uintptr_t* a) {
    return gc_debug_object_state((object_t*)*a);
}

static void _entrypoint(object_t* self, fun_t cont) {
    (void)self; _exit_cont = cont;
    gc_debug_manual_mode = true;
    while (gc_debug_stage() == GC_STAGE_NOT_STARTED) usleep(1000);   // wait for the collector
    while (gc_debug_stage() != GC_STAGE_IDLE) gc_debug_step();

    build();
    scrub();
    run_one_cycle();
    if (state(&g_H) != 1 || state(&g_C) != 1) fail("setup: H or C not live after a cycle", 0);

    straggler();
    scrub();
    run_one_cycle();
    int c = state(&g_C);
    printf("test_gc_late_mark: after the next cycle C_state=%d (1=live, 2=reclaimed)\n", c);
    if (c != 1) fail("C was reclaimed: H's page went unscanned behind a stale mark", c);
    printf("test_gc_late_mark: OK\n");
    fflush(stdout);
    ((void(*)(object_t*,object_t*))_exit_cont.f)(_exit_cont.o, integer_from_int32(0));
}

int main(void) {
    setenv("YAFL_HEAP_SIZE", "64m", 0);
    _prev = add_roots_declaration_func(_decl);
    thread_start(_entrypoint);
    return 0;
}
