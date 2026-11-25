// Deterministic, single-stepped test: the overflow re-scan must not bump the
// epoch while a page is claimed (issue #148).
//
// When the reprocess ring has overflowed, the mark tail answers with a
// re-scan: it bumps `epoch` and moves every page processed so far back onto
// the scan list. A claimed page is on no list, so the move cannot take it. If
// a claim spans the bump, its page is stamped with the old epoch at the end
// of its scan and then published to the prune list, where it stays. A later
// mark on that page finds `processed_by_epoch != epoch`, which the mark paths
// take to mean "on the scan list, or being scanned", so the page is neither
// pushed on the ring nor scanned again. Prune keeps the marked object, and
// frees its children under it.
//
// The tail checks that no marking is outstanding before it decides on the
// re-scan, but it used to let the pool lock go between that check and the
// bump, and a claim could start in between:
//
//   1. Holders H[0..16], each on a page of its own with a rooted anchor, so
//      each page is marked and scanned. Page W holds X, X2 and Y2, none of
//      them rooted, so W is white; X2 holds Y2.
//   2. A cycle runs. When its tail starts with every holder's page processed
//      (gc_test_tail_probe), the holders are marked as mutators' barriers
//      mark them, which overflows the ring; the ring is then drained.
//   3. The tail decides on the re-scan. At that point (gc_test_reset_probe) a
//      second thread marks X, which hands W over, and runs the mark body,
//      which claims and scans W. It holds between the end of that scan and
//      the page's publication (gc_test_publish_probe) until the tail has
//      returned.
//   4. The second thread is let go and drains marking; then X2 is marked.
//   5. The cycle must end with X, X2 and Y2 live.
//
// Run with YAFL_THREADS=1; uses gc_debug_manual_mode. Builds its own object.c
// with YAFL_GC_RESET_PROBE and YAFL_GC_PUBLISH_PROBE.

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
extern void gc_test_drain_marking(void);
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
    .is_mutable = 1, .name = "epoch_holder", .implements_array = VTABLE_IMPLEMENTS(0),
};
struct link { object_t parent; object_t* child; };
static vtable_t link_vt = {
    .object_size = sizeof(struct link), .array_el_size = 0,
    .object_pointer_locations = maskof(struct link, .child),
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 1, .name = "epoch_link", .implements_array = VTABLE_IMPLEMENTS(0),
};
struct leaf { object_t parent; char pad[64]; };
static vtable_t leaf_vt = {
    .object_size = sizeof(struct leaf), .array_el_size = 0,
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 1, .name = "epoch_leaf", .implements_array = VTABLE_IMPLEMENTS(0),
};

// The addresses, where the collector does not look.
static volatile uintptr_t g_H[N], g_X, g_X2, g_Y2;
// The anchors: one rooted object on each holder's page.
static object_t* g_A[N];
static roots_declaration_func_t _prev;
static void _decl(void(*declare)(object_t**)) {
    _prev(declare);
    for (int i = 0; i < N; ++i) declare(&g_A[i]);
}
static fun_t _exit_cont;

// 0: waiting for the first tail; 1: ring overflowed, waiting for the re-scan
// decision; 2: the claim is holding; 3: released, X2 marked.
static _Atomic int  g_phase;
static _Atomic bool g_held, g_release, g_claimer_done;
static thread_local bool t_is_claimer;
static thrd_t g_claimer;

static void fail(const char* what, int got) {
    fprintf(stderr, "test_gc_claim_epoch: FAIL %s (got %d)\n", what, got);
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

// Step 2.
void gc_test_tail_probe(void) {
    if (atomic_load(&g_phase) != 0) return;
    for (int i = 0; i < N; ++i)
        if (!gc_test_page_done(page_of(g_H[i]))) return;
    for (int i = 0; i < N; ++i)
        if (gc_test_object_seen((object_t*)g_H[i]))
            fail("setup: a holder was marked before the probe (a stale copy of its address reached the scan)", i);
    if (gc_test_object_seen((object_t*)g_X) || gc_test_object_seen((object_t*)g_X2))
        fail("setup: W was marked before the probe", 0);
    atomic_store(&g_phase, 1);
    for (int i = 0; i < N; ++i)              // the last finds the ring full
        gc_test_mutator_mark((object_t*)g_H[i]);
    gc_test_drain_marking();
    for (int i = 0; i < N; ++i)
        if (!gc_test_page_done(page_of(g_H[i]))) fail("setup: a holder's page was not processed after the drain", i);
}

// Step 3, on the second thread: a mutator's mark, then an executor's claim.
static int claimer_main(void* arg) {
    (void)arg;
    t_is_claimer = true;
    gc_test_mutator_mark((object_t*)g_X);
    gc_test_drain_marking();
    atomic_store(&g_claimer_done, true);
    return 0;
}

// Step 3, between the end of W's scan and its publication.
void gc_test_publish_probe(void) {
    if (!t_is_claimer || atomic_load(&g_held)) return;
    atomic_store(&g_held, true);
    while (!atomic_load(&g_release)) usleep(1000);
}

// Step 3, in the tail.
void gc_test_reset_probe(void) {
    if (atomic_load(&g_phase) != 1) return;
    atomic_store(&g_phase, 2);
    if (thrd_create(&g_claimer, claimer_main, NULL) != thrd_success) fail("setup: thrd_create", 0);
    if (!wait_for(&g_held, 10000)) fail("setup: the second thread never finished its claim of W", 0);
}

// The tail hooks test_gc_reset_window uses; nothing to do here.
void gc_test_pump_probe(void) {}

static void step(void) {
    gc_debug_step();
    if (atomic_load(&g_phase) == 2) {        // the tail that held the probe has returned
        atomic_store(&g_release, true);
        if (!wait_for(&g_claimer_done, 10000)) fail("the second thread did not finish draining", 0);
        thrd_join(g_claimer, NULL);
        gc_test_mutator_mark((object_t*)g_X2);   // step 4
        atomic_store(&g_phase, 3);
    }
}

static void run_one_cycle(void) {
    int guard = 0;
    while (gc_debug_stage() == ST_IDLE) {
        if (++guard > 100000) fail("cycle did not start", gc_debug_stage());
        step();
    }
    while (gc_debug_stage() != ST_IDLE) {
        if (++guard > 1000000) fail("cycle did not finish", gc_debug_stage());
        step();
    }
}

// In a frame of its own, so no copy of an address lingers for the
// conservative stack scan; scrub() overwrites what the frame left. Built
// below a gap, as test_gc_pump_window explains.
static void __attribute__((noinline)) build(void) {
    for (int i = 0; i < N; ++i) {
        object_t* h = object_create(&holder_vt);
        g_A[i] = object_create(&leaf_vt);   // the bump fills the holder's page first
        object_t* l = object_create(&leaf_vt);
        GC_STORE_IN(h, ((struct holder*)h)->child, 1, l);
        g_H[i] = (uintptr_t)h;
    }
    object_t* x  = object_create(&holder_vt);   // over half a page: W is a page of its own
    object_t* x2 = object_create(&link_vt);
    object_t* y2 = object_create(&leaf_vt);
    memset(((struct leaf*)y2)->pad, 0x5a, sizeof ((struct leaf*)y2)->pad);
    GC_STORE_IN(x2, ((struct link*)x2)->child, 1, y2);
    g_X = (uintptr_t)x; g_X2 = (uintptr_t)x2; g_Y2 = (uintptr_t)y2;
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
    _prev = add_roots_declaration_func(_decl);
    while (gc_debug_stage() == 0) usleep(1000);   // wait for the collector
    while (gc_debug_stage() != ST_IDLE) gc_debug_step();

    build_below();
    for (int i = 0; i < N; ++i)
        if (page_of((uintptr_t)g_A[i]) != page_of(g_H[i])) fail("setup: an anchor is not on its holder's page", i);
    for (int i = 0; i < N; ++i)
        if (page_of(g_X) == page_of(g_H[i])) fail("setup: W is a holder's page", i);
    if (page_of(g_X2) != page_of(g_X) || page_of(g_Y2) != page_of(g_X))
        fail("setup: X, X2 and Y2 are not all on W", 0);
    scrub();
    for (int i = 1; i < N; ++i)
        for (int j = 0; j < i; ++j)
            if (page_of(g_H[i]) == page_of(g_H[j])) fail("setup: two holders share a page", i);

    run_one_cycle();
    if (atomic_load(&g_phase) != 3) fail("the probes did not all run", atomic_load(&g_phase));
    if (gc_debug_object_state((object_t*)g_X) != 1)  fail("X was reclaimed", 0);
    if (gc_debug_object_state((object_t*)g_X2) != 1) fail("X2 was reclaimed", 0);
    if (gc_debug_object_state((object_t*)g_Y2) != 1)
        fail("X2's child was reclaimed: W was published with the epoch the re-scan ended, so the mark of X2 never had it scanned", 0);
    printf("test_gc_claim_epoch: OK\n");
    fflush(stdout);
    ((void(*)(object_t*,object_t*))_exit_cont.f)(_exit_cont.o, integer_from_int32(0));
}

int main(void) {
    setenv("YAFL_HEAP_SIZE", "64m", 0);
    thread_start(_entrypoint);
    return 0;
}
