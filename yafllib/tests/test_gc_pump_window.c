// Deterministic, single-stepped test: a rescan request the reprocess ring has
// handed to a pump, but the pump has not yet delivered, must keep marking
// alive.
//
// A mutator that marks an object on a page already processed this epoch
// pushes the page on the reprocess ring; a mark executor's pump takes the
// entry off and requeues the page. While the entry is between the two, the
// ring is empty, so it must count as in flight: if another executor's tail
// sees neither, it retires marking, the requeue arrives after the end and is
// dropped, and the marked object is kept by prune's residue merge without
// ever having been scanned — its children are reclaimed under it. (Seen on
// aarch64 as test_gc_mesh's rare corrupt chain: the pump was preempted
// between taking the entry and counting it.)
//
//   1. A (on page P) holds B. Neither is rooted, so neither is marked.
//   2. A cycle runs. When its tail finds P processed and nothing left to scan
//      (the probe, compiled into this target alone: YAFL_GC_PUMP_PROBE), A is
//      marked as a mutator's barrier marks it, which puts P on the ring.
//   3. The tail's pump takes the entry; at that moment a second tail runs, as
//      another executor's would.
//   4. When the cycle ends, A was marked, so B must still be live.
//
// Run with YAFL_THREADS=1; uses gc_debug_manual_mode.

#include "../yafl.h"
#include "callee_saved.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

extern bool gc_debug_manual_mode;
extern int  gc_debug_stage(void);
extern void gc_debug_step(void);
extern int  gc_debug_object_state(object_t* o);   // 0 not-heap, 1 live, 2 reclaimed
extern void gc_test_mutator_mark(object_t* o);
extern void gc_test_mark_tail(void);
extern bool gc_test_page_done(void* page);
extern bool gc_test_object_seen(object_t* o);

enum { ST_IDLE = 1 };

// Mutable: never relocated, so the addresses stay stable.
struct holder { object_t parent; object_t* child; char pad[8192 - sizeof(object_t) - sizeof(object_t*)]; };
static vtable_t holder_vt = {
    .object_size = sizeof(struct holder), .array_el_size = 0,
    .object_pointer_locations = maskof(struct holder, .child),
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 1, .name = "pump_holder", .implements_array = VTABLE_IMPLEMENTS(0),
};
struct leaf { object_t parent; char pad[8192 - sizeof(object_t)]; };
static vtable_t leaf_vt = {
    .object_size = sizeof(struct leaf), .array_el_size = 0,
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 1, .name = "pump_leaf", .implements_array = VTABLE_IMPLEMENTS(0),
};

// The addresses, where the collector does not look.
static volatile uintptr_t g_A, g_B;
static bool  g_marking, g_in_window;
static int   g_marked, g_second_tail;
static fun_t _exit_cont;
static void fail(const char* what, int got);

void gc_test_tail_probe(void) {
    if (!g_marking || g_in_window) return;
    if (!gc_test_page_done((void*)(g_A & ~(uintptr_t)(GC_PAGE_SIZE - 1)))) return;
    g_marking = false;
    if (gc_test_object_seen((object_t*)g_A))
        fail("setup: A was marked before the probe (a stale copy of its address reached the scan)", 0);
    gc_test_mutator_mark((object_t*)g_A);   // P is processed: onto the ring
    g_marked = 1;
    g_in_window = true;                     // the tail's own pump takes it next
}

void gc_test_pump_probe(void) {
    if (!g_in_window) return;
    g_in_window = false;
    gc_test_mark_tail();                    // another executor's tail, now
    g_second_tail = 1;
}

static void fail(const char* what, int got) {
    fprintf(stderr, "test_gc_pump_window: FAIL %s (got %d)\n", what, got);
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
// below a gap: scrub()'s array lies at the bottom of its frame, and the slots
// above it (saved registers, padding) are not written, so a build() frame at
// the same depth would leave A's address there (clang -O0 does).
static void __attribute__((noinline)) build(void) {
    object_t* a = object_create(&holder_vt);
    object_t* b = object_create(&leaf_vt);
    memset(((struct leaf*)b)->pad, 0x5a, sizeof ((struct leaf*)b)->pad);
    GC_STORE_IN(a, ((struct holder*)a)->child, 1, b);
    g_A = (uintptr_t)a;
    g_B = (uintptr_t)b;
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
    __asm__ volatile("" :: "r"(junk[0]), "r"(junk[2047]) : CALLEE_SAVED_CLOBBERS);
}

static void _entrypoint(object_t* self, fun_t cont) {
    (void)self; _exit_cont = cont;
    gc_debug_manual_mode = true;
    while (gc_debug_stage() == 0) usleep(1000);   // wait for the collector
    while (gc_debug_stage() != ST_IDLE) gc_debug_step();

    build_below();
    scrub();

    g_marking = true;
    run_one_cycle();
    if (!g_marked) fail("the tail probe did not mark A", 0);
    if (!g_second_tail) fail("the pump probe did not run", 0);
    int a = gc_debug_object_state((object_t*)g_A), b = gc_debug_object_state((object_t*)g_B);
    printf("test_gc_pump_window: after the cycle A_state=%d B_state=%d (1=live, 2=reclaimed)\n", a, b);
    if (a != 1) fail("the marked object was reclaimed", a);
    if (b != 1) fail("a marked object's child was reclaimed: its rescan was dropped", b);
    printf("test_gc_pump_window: OK\n");
    fflush(stdout);
    ((void(*)(object_t*,object_t*))_exit_cont.f)(_exit_cont.o, integer_from_int32(0));
}

int main(void) {
    setenv("YAFL_HEAP_SIZE", "64m", 0);
    thread_start(_entrypoint);
    return 0;
}
