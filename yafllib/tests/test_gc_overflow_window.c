// Deterministic, single-stepped test: a mark the reprocess ring drops because
// it is full must keep marking from retiring, even when it is dropped after
// the tail has read and cleared the overflow flag.
//
// A mutator that marks an object on a page already processed this epoch
// pushes the page on the reprocess ring. With the ring full the push is
// dropped and the overflow flag set instead, and the tail answers the flag
// with a re-scan of the whole heap. The tail reads (and clears) the flag
// before its final check: an overflow between the two, its ring entries then
// drained by other executors, leaves nothing outstanding but the flag. If the
// final check ignores it, marking retires, and the dropped object is kept by
// prune's residue merge without ever having been scanned — its children are
// reclaimed under it.
//
//   1. Holders H[0..16], each on a page of its own, each hold a leaf. None is
//      rooted, so none is marked.
//   2. A cycle runs. When its tail has read the flag and finds every holder's
//      page processed with nothing left to scan (the probe, compiled into this
//      target alone: YAFL_GC_OVERFLOW_PROBE), H[0..15] are marked as
//      mutators' barriers mark them, which fills the ring, and H[16] is
//      marked, which overflows it. Other executors then drain the ring and
//      scan what it requeued.
//   3. When the cycle ends, H[16] was marked, so its leaf must still be live.
//
// Run with YAFL_THREADS=1; uses gc_debug_manual_mode.

#include "../yafl.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
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
    .is_mutable = 1, .name = "overflow_holder", .implements_array = VTABLE_IMPLEMENTS(0),
};
struct leaf { object_t parent; char pad[64]; };
static vtable_t leaf_vt = {
    .object_size = sizeof(struct leaf), .array_el_size = 0,
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 1, .name = "overflow_leaf", .implements_array = VTABLE_IMPLEMENTS(0),
};

// The addresses, where the collector does not look.
static volatile uintptr_t g_H[N], g_L[N];
static bool  g_marking;
static int   g_overflowed;
static fun_t _exit_cont;
static void fail(const char* what, int got);

static void* page_of(uintptr_t a) { return (void*)(a & ~(uintptr_t)(GC_PAGE_SIZE - 1)); }

void gc_test_overflow_probe(void) {
    if (!g_marking) return;
    for (int i = 0; i < N; ++i)
        if (!gc_test_page_done(page_of(g_H[i]))) return;
    g_marking = false;
    for (int i = 0; i < N; ++i)
        if (gc_test_object_seen((object_t*)g_H[i]))
            fail("setup: a holder was marked before the probe (a stale copy of its address reached the scan)", i);
    for (int i = 0; i < N; ++i)              // the last finds the ring full
        gc_test_mutator_mark((object_t*)g_H[i]);
    gc_test_drain_marking();                 // other executors, now
    g_overflowed = 1;
}

static void fail(const char* what, int got) {
    fprintf(stderr, "test_gc_overflow_window: FAIL %s (got %d)\n", what, got);
    fflush(stderr);
    abort();
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

    g_marking = true;
    run_one_cycle();
    if (!g_overflowed) fail("the overflow probe did not run", 0);
    int h = gc_debug_object_state((object_t*)g_H[RING]), l = gc_debug_object_state((object_t*)g_L[RING]);
    printf("test_gc_overflow_window: after the cycle H_state=%d L_state=%d (1=live, 2=reclaimed)\n", h, l);
    if (h != 1) fail("the dropped holder was reclaimed", h);
    if (l != 1) fail("a dropped holder's child was reclaimed: marking retired over the overflow", l);
    printf("test_gc_overflow_window: OK\n");
    fflush(stdout);
    ((void(*)(object_t*,object_t*))_exit_cont.f)(_exit_cont.o, integer_from_int32(0));
}

int main(void) {
    setenv("YAFL_HEAP_SIZE", "64m", 0);
    thread_start(_entrypoint);
    return 0;
}
