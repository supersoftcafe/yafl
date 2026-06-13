// Deterministic, single-stepped test of the immutability-based generations.
//
//   1. Allocate K (immutable leaf) and root it.
//   2. Drive full GC cycles — with dropped FILLER allocated between them,
//      because promotion is volume-based: K's page must stay stable across
//      two dwell windows' worth of allocation before
//      gc_debug_object_generation(K) flips young -> old.
//   3. Drop the root. Run another full (minor) cycle: K must SURVIVE — old
//      pages are exempt from minor collection by design.
//   4. gc_debug_request_major(); run one more cycle: K must now be RECLAIMED.
//
// Run with YAFL_THREADS=1; uses gc_debug_manual_mode (allocation does not
// drive the FSA; the dwell gate is bypassed in manual mode). The heap is set
// small in main() so the dwell floor — and with it the promotion volume —
// stays a few MiB of filler.

#include "../yafl.h"
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

extern bool gc_debug_manual_mode;
extern int  gc_debug_stage(void);
extern void gc_debug_step(void);
extern int  gc_debug_object_state(object_t* o);        // 0 not-heap, 1 live, 2 reclaimed
extern int  gc_debug_object_generation(object_t* o);   // -1 not-heap, 0 young, 1 old
extern void gc_debug_request_major(void);

enum { ST_IDLE = 1 };

// Big enough (8 KB = half a 16 KB page) that K's page is never sparse, so the
// compactor leaves it alone — compacted pages are excluded from promotion and
// would have K chasing fresh young copies forever.
struct leaf { object_t parent; char pad[8192 - sizeof(object_t)]; };
static vtable_t leaf_vt = {
    .object_size = sizeof(struct leaf), .array_el_size = 0,
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 0, .name = "gen_leaf", .implements_array = VTABLE_IMPLEMENTS(0),
};

// Filler: bigger than half a page so it can never share K's page (a dying
// neighbour would make K's page unstable and reset its promotion clock).
struct fill { object_t parent; char pad[12 * 1024 - sizeof(object_t)]; };
static vtable_t fill_vt = {
    .object_size = sizeof(struct fill), .array_el_size = 0,
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 0, .name = "gen_fill", .implements_array = VTABLE_IMPLEMENTS(0),
};

// Allocate ~2 MiB of immediately-dropped filler: advances the allocation
// clock so K's stable page can clear the promotion volume.
static void __attribute__((noinline)) churn_filler(void) {
    for (int i = 0; i < 170; ++i) {
        volatile object_t* f = object_create(&fill_vt);
        (void)f;
    }
}

static object_t*                _slots[1];
static roots_declaration_func_t _prev;
static void _decl(void(*declare)(object_t**)) { _prev(declare); declare(&_slots[0]); }

static volatile uintptr_t g_K;
static fun_t _exit_cont;

static void fail(const char* what, int got) {
    fprintf(stderr, "test_gc_gen: FAIL %s (got %d)\n", what, got);
    fflush(stderr);
    abort();
}

// Drive exactly one full GC cycle: IDLE -> ... -> IDLE.
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

static int Kgen(void)   { return gc_debug_object_generation((object_t*)g_K); }
static int Kstate(void) { return gc_debug_object_state((object_t*)g_K); }

// Allocate + root K in its own frame so K's address does not linger in the
// entrypoint's stack slots, where the conservative scan would keep marking it.
static void __attribute__((noinline)) create_and_root(void) {
    object_t* k = object_create(&leaf_vt);
    GC_WRITE_BARRIER(_slots[0], 1);
    _slots[0] = k;
    g_K = (uintptr_t)k;
}

// Overwrite the stack below us and clobber callee-saved registers so no stale
// copy of K's address survives for the conservative scan to find.
static void __attribute__((noinline)) scrub(void) {
    volatile uintptr_t junk[512];
    for (int i = 0; i < 512; ++i) junk[i] = (uintptr_t)(i * 2 + 1);
    __asm__ volatile("" :: "r"(junk[0]), "r"(junk[511]) : "memory",
        "rbx", "r12", "r13", "r14", "r15");
}

static void _entrypoint(object_t* self, fun_t cont) {
    (void)self; _exit_cont = cont;
    gc_debug_manual_mode = true;
    /* gc_start() fires when the LAST thread registers — a countdown this
       entrypoint can outrun. Stepping through NOT_STARTED is a no-op, so a
       fast spin exhausts the step guard before the collector exists: wait
       for it (yielding, so the registering threads get scheduled). */
    while (gc_debug_stage() == 0) usleep(1000);

    // (1) Allocate + root K.
    create_and_root();
    scrub();
    printf("test_gc_gen: K=%p gen=%d state=%d\n", (void*)g_K, Kgen(), Kstate());
    if (Kgen() != 0) fail("expected young at birth", Kgen());

    // (2) Cycle until promoted (bounded), churning filler between cycles so
    // the allocation clock crosses the promotion volume.
    int cycles = 0;
    while (Kgen() == 0) {
        churn_filler();
        scrub();
        run_one_cycle();
        if (++cycles > 12) fail("never promoted", Kgen());
    }
    printf("test_gc_gen: promoted after %d cycles; state=%d\n", cycles, Kstate());
    if (Kstate() != 1) fail("promoted object not live", Kstate());

    // (3) Drop the root; a MINOR cycle must NOT reclaim an old object.
    GC_WRITE_BARRIER(_slots[0], 1);
    _slots[0] = NULL;
    scrub();
    run_one_cycle();
    if (Kstate() != 1) fail("minor cycle reclaimed an old object", Kstate());
    if (Kgen() != 1)   fail("object left the old generation unexpectedly", Kgen());
    printf("test_gc_gen: unreferenced old object correctly exempt from minor\n");

    // (4) A MAJOR cycle must reclaim it.
    gc_debug_request_major();
    run_one_cycle();
    int st = Kstate();
    printf("test_gc_gen: after major: state=%d (2=reclaimed or page freed)\n", st);
    if (st == 1) fail("major cycle failed to reclaim old garbage", st);

    printf("test_gc_gen: OK\n");
    fflush(stdout);
    ((void(*)(object_t*,object_t*))_exit_cont.f)(_exit_cont.o, integer_from_int32(0));
}

int main(void) {
    // Small heap before any allocation: dwell floor = total/64 = 1 MiB, so
    // the promotion volume (two dwell windows) is ~2 MiB — one churn_filler
    // batch per cycle clears it quickly.
    setenv("YAFL_HEAP_SIZE", "64m", 0);
    _prev = add_roots_declaration_func(_decl);
    thread_start(_entrypoint);
    return 0;
}
