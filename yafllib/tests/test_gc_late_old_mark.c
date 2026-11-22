// Deterministic, single-stepped test: a mutator's mark held over into the next
// cycle must not hand an OLD page over to a minor (#134).
//
// A barrier filters before it counts itself: an object on an old page, or one
// marked already, needs nothing. One that passed the filter just before
// marking closed and was then held (preempted) can count itself and find
// marking open again, the NEXT cycle's. Its object's page may have been
// promoted at the prune in between. Handed over, the old page joins the
// minor's scan list: its objects are scanned, but every mark of an object on
// an old page is skipped (old is implicitly live), so its prune keeps only the
// one the barrier marked, and frees everything else on the page under the
// pointers that reach it (test_gc_mesh, 1 run in ~500 with the soak's hot
// settings).
//
//   1. R (a declared root) -> Z -> Y, Z and Y on one page. Cycles until that
//      page is old.
//   2. A minor opens. In its root scan, a barrier past its filter (by hand)
//      marks Z.
//   3. The minor runs to its end. Y must still be live, and its page old.
//
// Run with YAFL_THREADS=1; uses gc_debug_manual_mode. Builds its own object.c
// with YAFL_GC_HANDOFF_PROBE, for the test helpers.

#include "../yafl.h"
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

extern bool gc_debug_manual_mode;
extern int  gc_debug_stage(void);
extern void gc_debug_step(void);
extern int  gc_debug_object_state(object_t* o);        // 0 not-heap, 1 live, 2 reclaimed
extern int  gc_debug_object_generation(object_t* o);   // -1 not-heap, 0 young, 1 old
extern void gc_test_mutator_mark_unfiltered(object_t* o);

enum { ST_IDLE = 1, ST_SCAN_ROOTS = 3 };

struct node { object_t parent; object_t* next; intptr_t id; };
static vtable_t node_vt = {
    .object_size = sizeof(struct node), .array_el_size = 0,
    .object_pointer_locations = maskof(struct node, .next),
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 0, .name = "late_old_node", .implements_array = VTABLE_IMPLEMENTS(0),
};
// Churn, bigger than half a page so it never shares a page with Z and Y: it
// drives the allocation volume that promotion waits for.
struct fill { object_t parent; char pad[12 * 1024 - sizeof(object_t)]; };
static vtable_t churn_vt = {
    .object_size = sizeof(struct fill), .array_el_size = 0,
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 0, .name = "late_old_churn", .implements_array = VTABLE_IMPLEMENTS(0),
};

static object_t*                _slots[1];
static roots_declaration_func_t _prev;
static void _decl(void(*declare)(object_t**)) { _prev(declare); declare(&_slots[0]); }

static volatile uintptr_t g_Z, g_Y;   // where the collector does not look
static fun_t _exit_cont;

void gc_test_handoff_probe(void);
void gc_test_handoff_probe(void) {}   // the shared probe build's hook: unused here

static void fail(const char* what, int got) {
    fprintf(stderr, "test_gc_late_old_mark: FAIL %s (got %d)\n", what, got);
    fflush(stderr);
    abort();
}

static void run_until(int want) {
    for (int guard = 0; gc_debug_stage() != want; ++guard) {
        if (guard > 1000000) fail("the collector never reached the stage", gc_debug_stage());
        gc_debug_step();
    }
}

static void run_one_cycle(void) {
    for (int guard = 0; gc_debug_stage() == ST_IDLE; ++guard) {
        if (guard > 100000) fail("cycle did not start", gc_debug_stage());
        gc_debug_step();
    }
    run_until(ST_IDLE);
}

static gc_page_t* page_of(uintptr_t o) {
    return (gc_page_t*)(o & ~(uintptr_t)(GC_PAGE_SIZE - 1));
}

// In a frame of its own, so no copy of an address lingers for the
// conservative stack scan; scrub() overwrites what the frame left.
static void __attribute__((noinline)) build(void) {
    object_t* y = object_create(&node_vt);
    object_t* z = object_create(&node_vt);
    ((struct node*)z)->next = y;   // construction: fresh, no barrier owed
    GC_ROOT_STORE(_slots[0], 1, z);
    g_Y = (uintptr_t)y;
    g_Z = (uintptr_t)z;
}

static void __attribute__((noinline)) churn(void) {
    for (int i = 0; i < 170; ++i) {
        volatile object_t* f = object_create(&churn_vt);
        (void)f;
    }
}

static void __attribute__((noinline)) scrub(void) {
    volatile uintptr_t junk[2048];
    for (int i = 0; i < 2048; ++i) junk[i] = (uintptr_t)(i * 2 + 1);
    __asm__ volatile("" :: "r"(junk[0]), "r"(junk[2047]) : ARCH_CALLEE_SAVED_CLOBBERS);
}

static void __attribute__((noinline)) straggler(void) {
    gc_test_mutator_mark_unfiltered((object_t*)g_Z);
}

static int state(uintptr_t o) { return gc_debug_object_state((object_t*)o); }
static int gen(uintptr_t o)   { return gc_debug_object_generation((object_t*)o); }

static void _entrypoint(object_t* self, fun_t cont) {
    (void)self; _exit_cont = cont;
    gc_debug_manual_mode = true;
    while (gc_debug_stage() == 0) usleep(1000);   // wait for the collector
    run_until(ST_IDLE);

    // (1) Z -> Y on one page, aged until the page is old.
    build();
    scrub();
    if (page_of(g_Z) != page_of(g_Y)) fail("setup: Z and Y landed on different pages", 0);
    for (int cycles = 0; gen(g_Z) != 1; ++cycles) {
        if (cycles > 25) fail("setup: Z's page never promoted", gen(g_Z));
        churn();
        scrub();
        run_one_cycle();
    }

    // (2) A minor opens; in its root scan, the held-over barrier marks Z.
    run_until(ST_SCAN_ROOTS);
    straggler();
    scrub();

    // (3) The minor runs to its end.
    run_until(ST_IDLE);
    int y = state(g_Y);
    printf("test_gc_late_old_mark: after the minor Y_state=%d (1=live, 2=reclaimed) generation=%d\n",
           y, gen(g_Y));
    if (y != 1) fail("Y was reclaimed: its old page was handed over to a minor", y);
    if (gen(g_Z) != 1) fail("Z's page left the old generation", gen(g_Z));
    printf("test_gc_late_old_mark: OK\n");
    fflush(stdout);
    ((void(*)(object_t*,object_t*))_exit_cont.f)(_exit_cont.o, integer_from_int32(0));
}

int main(void) {
    setenv("YAFL_HEAP_SIZE", "64m", 0);
    setenv("YAFL_GC_PROMOTE_FLOOR", "64", 0);
    setenv("YAFL_GC_COMPACT_PERCENT", "0", 0);   // Z and Y stay where they are
    _prev = add_roots_declaration_func(_decl);
    thread_start(_entrypoint);
    return 0;
}
