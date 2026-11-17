// Deterministic, single-stepped test: a reprocess-ring push must never
// overwrite an entry a pump has claimed but not yet taken (issue #132).
//
// The ring is a bounded MPMC queue of REPROCESS_PAGE_COUNT (16) slots. A
// mutator's barrier reserves index `tail` (if tail - head < 16) and fills slot
// tail % 16; a pump claims index `head` by advancing it, then takes the slot.
// `head` moves at the CLAIM, so between a pump's claim of index i and its take,
// a push may already reserve index i + 16 — the same slot, still holding entry
// i. A plain store there overwrote it. The pump then took entry i + 16 in
// place of i, entry i was lost, every later take on that slot ran a lap ahead,
// and the last pump of the cycle claimed an index whose entry was already
// gone. It spun on the empty slot for good, counted in gc_pages_in_flight, so
// marking never retired and no cycle ended: the allocators filled the heap and
// stalled in gc_page_alloc's reserve gate — the self-compile hang of #132.
// (The window is a few instructions wide, so it takes a pump preempted there.)
//
//   1. Holders H[0..16], each on a page of its own, each hold a leaf. None is
//      rooted, so none is marked.
//   2. A cycle runs. When its tail starts with every holder's page processed
//      (gc_test_tail_probe), a second thread marks H[0], which pushes index 0,
//      and pumps the ring: it claims index 0 and holds before taking the slot
//      (gc_test_pump_probe).
//   3. The main thread marks H[1..15] (indices 1..15), and a third thread
//      marks H[16]: index 16, slot 0 again, with entry 0 not yet taken.
//   4. The pump is released. It must take entry 0, then every other entry,
//      and finish; the cycle must end with every holder and leaf live.
//
// Run with YAFL_THREADS=1; uses gc_debug_manual_mode. Builds its own object.c
// with YAFL_GC_LAP_PROBE.

#include "../yafl.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <threads.h>
#include <unistd.h>

extern bool gc_debug_manual_mode;
extern int  gc_debug_stage(void);
extern void gc_debug_step(void);
extern int  gc_debug_object_state(object_t* o);   // 0 not-heap, 1 live, 2 reclaimed
extern void gc_test_mutator_mark(object_t* o);
extern void gc_test_pump_ring(void);
extern bool gc_test_page_done(void* page);
extern bool gc_test_object_seen(object_t* o);

enum { ST_IDLE = 1, RING = 16, N = RING + 1 };

// Mutable: never relocated, so the addresses stay stable. Over half a page,
// so no two share one.
struct holder { object_t parent; object_t* child; char pad[9000]; };
static vtable_t holder_vt = {
    .object_size = sizeof(struct holder), .array_el_size = 0,
    .object_pointer_locations = maskof(struct holder, .child),
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 1, .name = "lap_holder", .implements_array = VTABLE_IMPLEMENTS(0),
};
struct leaf { object_t parent; char pad[64]; };
static vtable_t leaf_vt = {
    .object_size = sizeof(struct leaf), .array_el_size = 0,
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 1, .name = "lap_leaf", .implements_array = VTABLE_IMPLEMENTS(0),
};

// The addresses, where the collector does not look.
static volatile uintptr_t g_H[N], g_L[N];
static fun_t _exit_cont;

static _Atomic bool g_probed, g_claimed, g_release, g_pump_done, g_lap_done;
static thread_local bool t_is_pumper;
static thrd_t g_pumper, g_lapper;

static void fail(const char* what, int got) {
    fprintf(stderr, "test_gc_ring_lap_window: FAIL %s (got %d)\n", what, got);
    fflush(stderr);
    abort();
}

static void* page_of(uintptr_t a) { return (void*)(a & ~(uintptr_t)(GC_PAGE_SIZE - 1)); }

static bool wait_for(_Atomic bool* flag, int ms) {
    for (int i = 0; i < ms; ++i) {
        if (atomic_load(flag)) return true;
        usleep(1000);
    }
    return atomic_load(flag);
}

// Step 2, on the second thread: a mutator's mark, then an executor's pump.
static int pumper_main(void* arg) {
    (void)arg;
    t_is_pumper = true;
    gc_test_mutator_mark((object_t*)g_H[0]);
    gc_test_pump_ring();
    atomic_store(&g_pump_done, true);
    return 0;
}

// Between the pump's claim of index 0 and its take.
void gc_test_pump_probe(void) {
    if (!t_is_pumper || atomic_load(&g_claimed)) return;
    atomic_store(&g_claimed, true);
    while (!atomic_load(&g_release)) usleep(1000);
}

// Step 3, on the third thread: the push one lap on, onto entry 0's slot.
static int lapper_main(void* arg) {
    (void)arg;
    gc_test_mutator_mark((object_t*)g_H[RING]);
    atomic_store(&g_lap_done, true);
    return 0;
}

void gc_test_tail_probe(void) {
    if (atomic_load(&g_probed)) return;
    for (int i = 0; i < N; ++i)
        if (!gc_test_page_done(page_of(g_H[i]))) return;
    for (int i = 0; i < N; ++i)
        if (gc_test_object_seen((object_t*)g_H[i]))
            fail("setup: a holder was marked before the probe (a stale copy of its address reached the scan)", i);
    atomic_store(&g_probed, true);

    if (thrd_create(&g_pumper, pumper_main, NULL) != thrd_success) fail("setup: thrd_create", 0);
    if (!wait_for(&g_claimed, 10000)) fail("setup: the pump never claimed index 0", 0);
    for (int i = 1; i < RING; ++i)
        gc_test_mutator_mark((object_t*)g_H[i]);
    if (thrd_create(&g_lapper, lapper_main, NULL) != thrd_success) fail("setup: thrd_create", 1);
    // Give the lap push every chance to land on the claimed slot. With the
    // slot held it may wait for the take; it must not overwrite.
    wait_for(&g_lap_done, 200);

    atomic_store(&g_release, true);
    if (!wait_for(&g_pump_done, 5000))
        fail("the pump is still spinning on an empty slot: a push overwrote an entry claimed but not yet taken", 0);
    if (!wait_for(&g_lap_done, 5000)) fail("the lap push never completed", 0);
    thrd_join(g_pumper, NULL);
    thrd_join(g_lapper, NULL);
}

static void run_one_cycle(void) {
    int guard = 0;
    while (gc_debug_stage() == ST_IDLE) {
        if (++guard > 100000) fail("cycle did not start", gc_debug_stage());
        gc_debug_step();
    }
    while (gc_debug_stage() != ST_IDLE) {
        if (++guard > 1000000) fail("cycle did not finish", gc_debug_stage());
        gc_debug_step();
    }
}

// In a frame of its own, so no copy of an address lingers for the
// conservative stack scan; scrub() overwrites what the frame left. Built
// below a gap, as test_gc_pump_window explains.
static void __attribute__((noinline)) build(void) {
    for (int i = 0; i < N; ++i) {
        object_t* h = object_create(&holder_vt);
        object_t* l = object_create(&leaf_vt);
        memset(((struct leaf*)l)->pad, 0x5a, sizeof ((struct leaf*)l)->pad);
        GC_STORE_IN(h, ((struct holder*)h)->child, 1, l);
        g_H[i] = (uintptr_t)h;
        g_L[i] = (uintptr_t)l;
    }
}

static void __attribute__((noinline)) build_below(void) {
    volatile char gap[1024];
    gap[0] = 0;
    build();
    __asm__ volatile("" :: "r"(gap) : "memory");
}

static void __attribute__((noinline)) scrub(void) {
    volatile uintptr_t junk[2048];
    for (int i = 0; i < 2048; ++i) junk[i] = (uintptr_t)(i * 2 + 1);
    __asm__ volatile("" :: "r"(junk[0]), "r"(junk[2047]) : ARCH_CALLEE_SAVED_CLOBBERS);
}

static void _entrypoint(object_t* self, fun_t cont) {
    (void)self; _exit_cont = cont;
    gc_debug_manual_mode = true;
    while (gc_debug_stage() == 0) usleep(1000);   // wait for the collector
    while (gc_debug_stage() != ST_IDLE) gc_debug_step();

    build_below();
    scrub();
    for (int i = 1; i < N; ++i)
        for (int j = 0; j < i; ++j)
            if (page_of(g_H[i]) == page_of(g_H[j])) fail("setup: two holders share a page", i);

    run_one_cycle();
    if (!atomic_load(&g_probed)) fail("the probe did not run", 0);
    for (int i = 0; i < N; ++i) {
        if (gc_debug_object_state((object_t*)g_H[i]) != 1) fail("a marked holder was reclaimed", i);
        if (gc_debug_object_state((object_t*)g_L[i]) != 1) fail("a marked holder's child was reclaimed", i);
    }
    printf("test_gc_ring_lap_window: OK\n");
    fflush(stdout);
    ((void(*)(object_t*,object_t*))_exit_cont.f)(_exit_cont.o, integer_from_int32(0));
}

int main(void) {
    setenv("YAFL_HEAP_SIZE", "64m", 0);
    thread_start(_entrypoint);
    return 0;
}
