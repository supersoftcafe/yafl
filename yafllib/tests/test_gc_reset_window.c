// Deterministic, single-stepped test: the overflow re-scan must not empty a
// reprocess-ring slot that a pump has already claimed (issue #132).
//
// The ring is a bounded MPMC queue. A mutator's barrier reserves an index by
// advancing `tail`, then fills the slot. A pump claims an index by advancing
// `head`, counts itself in flight, then takes the slot, spinning while it is
// still empty (the mutator may not have filled it yet). Marking cannot retire
// while anything is in flight.
//
// When the ring has overflowed, the mark tail answers with a re-scan of the
// whole heap, and used to reset the ring as it did: clear every slot, then
// head = tail = 0. Its emptiness check runs under the pool lock, but the
// reset ran after the lock was let go, with mutators and other executors still
// running. A push and a claim landing between the two lose the entry: the
// mutator fills the slot, the reset clears it, and the pump spins on it for
// good. It stays in flight, so marking never retires and no cycle ends. The
// allocators then fill the heap and stall in gc_page_alloc's reserve gate —
// the self-compile hang, with RSS at the heap limit.
//
//   1. Holders H[0..17], each on a page of its own, each hold a leaf. None is
//      rooted, so none is marked.
//   2. A cycle runs. When its tail starts with every holder's page processed
//      (gc_test_tail_probe), H[0..16] are marked, as mutators' barriers mark
//      them, which fills the ring and overflows it; the ring is then drained.
//   3. The tail decides on the re-scan. At that point (gc_test_reset_probe) a
//      second thread marks H[17], which pushes its page on the ring, and pumps
//      the ring, claiming that entry; it holds between the claim and taking
//      the slot (gc_test_pump_probe) until the tail has finished.
//   4. The pump must then get its entry and finish, and the cycle must end
//      with every holder and leaf live.
//
// Run with YAFL_THREADS=1; uses gc_debug_manual_mode. Builds its own object.c
// with YAFL_GC_RESET_PROBE.

#include "../yafl.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <threads.h>
#include <time.h>
#include <unistd.h>

extern bool gc_debug_manual_mode;
extern int  gc_debug_stage(void);
extern void gc_debug_step(void);
extern int  gc_debug_object_state(object_t* o);   // 0 not-heap, 1 live, 2 reclaimed
extern void gc_test_mutator_mark(object_t* o);
extern void gc_test_drain_marking(void);
extern void gc_test_pump_ring(void);
extern bool gc_test_page_done(void* page);
extern bool gc_test_object_seen(object_t* o);

enum { ST_IDLE = 1, RING = 16, N = RING + 2, LATE = RING + 1 };

// Mutable: never relocated, so the addresses stay stable. Over half a page,
// so no two share one.
struct holder { object_t parent; object_t* child; char pad[9000]; };
static vtable_t holder_vt = {
    .object_size = sizeof(struct holder), .array_el_size = 0,
    .object_pointer_locations = maskof(struct holder, .child),
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 1, .name = "reset_holder", .implements_array = VTABLE_IMPLEMENTS(0),
};
struct leaf { object_t parent; char pad[64]; };
static vtable_t leaf_vt = {
    .object_size = sizeof(struct leaf), .array_el_size = 0,
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 1, .name = "reset_leaf", .implements_array = VTABLE_IMPLEMENTS(0),
};

// The addresses, where the collector does not look.
static volatile uintptr_t g_H[N], g_L[N];
static fun_t _exit_cont;

// 0: waiting for the first tail; 1: ring overflowed, waiting for the re-scan
// decision; 2: the pump is holding; 3: the tail has run on; 4: released.
static _Atomic int  g_phase;
static _Atomic bool g_claimed, g_release, g_pump_done;
static thread_local bool t_is_pumper;
static thrd_t g_pumper;

static void fail(const char* what, int got) {
    fprintf(stderr, "test_gc_reset_window: FAIL %s (got %d)\n", what, got);
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
    atomic_store(&g_phase, 1);
    for (int i = 0; i <= RING; ++i)          // the last finds the ring full
        gc_test_mutator_mark((object_t*)g_H[i]);
    gc_test_drain_marking();
    for (int i = 0; i < N; ++i)
        if (!gc_test_page_done(page_of(g_H[i]))) fail("setup: a holder's page was not processed after the drain", i);
}

// Step 3, on the second thread: a mutator's mark, then an executor's pump.
static int pumper_main(void* arg) {
    (void)arg;
    t_is_pumper = true;
    gc_test_mutator_mark((object_t*)g_H[LATE]);
    gc_test_pump_ring();
    atomic_store(&g_pump_done, true);
    return 0;
}

// Step 3, between the claim and taking the slot.
void gc_test_pump_probe(void) {
    if (!t_is_pumper || atomic_load(&g_claimed)) return;
    atomic_store(&g_claimed, true);
    while (!atomic_load(&g_release)) usleep(1000);
}

// Step 3, in the tail.
void gc_test_reset_probe(void) {
    if (atomic_load(&g_phase) != 1) return;
    atomic_store(&g_phase, 2);
    if (thrd_create(&g_pumper, pumper_main, NULL) != thrd_success) fail("setup: thrd_create", 0);
    if (!wait_for(&g_claimed, 10000)) fail("setup: the second thread never claimed its ring entry", 0);
}

static void step(void) {
    gc_debug_step();
    if (atomic_load(&g_phase) == 2) {        // the tail that held the probe has returned
        atomic_store(&g_phase, 3);
        atomic_store(&g_release, true);
        if (!wait_for(&g_pump_done, 5000))
            fail("the pump is still spinning on its ring slot: the overflow re-scan emptied a claimed entry", 0);
        thrd_join(g_pumper, NULL);
        atomic_store(&g_phase, 4);
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
    if (atomic_load(&g_phase) != 4) fail("the probes did not all run", atomic_load(&g_phase));
    for (int i = 0; i < N; ++i) {
        int h = gc_debug_object_state((object_t*)g_H[i]), l = gc_debug_object_state((object_t*)g_L[i]);
        if (h != 1) fail("a marked holder was reclaimed", i);
        if (l != 1) fail("a marked holder's child was reclaimed", i);
    }
    printf("test_gc_reset_window: OK\n");
    fflush(stdout);
    ((void(*)(object_t*,object_t*))_exit_cont.f)(_exit_cont.o, integer_from_int32(0));
}

int main(void) {
    setenv("YAFL_HEAP_SIZE", "64m", 0);
    thread_start(_entrypoint);
    return 0;
}
