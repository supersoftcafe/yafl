// Deterministic, single-stepped test of CARDS: old stays old.
//
// An old object may point at a young one only if its card bit is set; every
// minor cycle traces the carded objects' fields, and a major keeps old pages
// old.
//
//   1. K (an immutable leaf) and P (immutable, its slot holding M, a MUTABLE
//      object, which never promotes) are rooted. Cycles with dropped filler
//      between them carry the allocation clock past the promotion volume:
//      K's page promotes, and so does P's, carded for its young M.
//   2. M's only reference is P's slot. Minor cycles must keep M (they trace
//      P's card), P must stay old and stay carded.
//   3. A major, with K and P still rooted: both stay old, M stays live.
//   4. The roots are dropped; a major reclaims K, P and M.
//
// Run with YAFL_THREADS=1; uses gc_debug_manual_mode.

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

// Half a page each, so no two share a page and none is ever sparse enough to
// compact.
struct leaf { object_t parent; char pad[8192 - sizeof(object_t)]; };
static vtable_t leaf_vt = {
    .object_size = sizeof(struct leaf), .array_el_size = 0,
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 0, .name = "cards_leaf", .implements_array = VTABLE_IMPLEMENTS(0),
};
struct parent { object_t parent; object_t* slot; char pad[8192 - sizeof(object_t) - sizeof(object_t*)]; };
static vtable_t parent_vt = {
    .object_size = sizeof(struct parent), .array_el_size = 0,
    .object_pointer_locations = maskof(struct parent, .slot),
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 0, .name = "cards_parent", .implements_array = VTABLE_IMPLEMENTS(0),
};
static vtable_t mutable_vt = {
    .object_size = sizeof(struct leaf), .array_el_size = 0,
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 1, .name = "cards_mutable", .implements_array = VTABLE_IMPLEMENTS(0),
};
// Filler, bigger than half a page so it never shares a page with the others.
struct fill { object_t parent; char pad[12 * 1024 - sizeof(object_t)]; };
static vtable_t fill_vt = {
    .object_size = sizeof(struct fill), .array_el_size = 0,
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 0, .name = "cards_fill", .implements_array = VTABLE_IMPLEMENTS(0),
};

static object_t*                _slots[2];   // K, P
static roots_declaration_func_t _prev;
static void _decl(void(*declare)(object_t**)) { _prev(declare); declare(&_slots[0]); declare(&_slots[1]); }

// The addresses, where the collector does not look.
static volatile uintptr_t g_K, g_P, g_M;
static fun_t _exit_cont;

static void fail(const char* what, int got) {
    fprintf(stderr, "test_gc_cards: FAIL %s (got %d)\n", what, got);
    fflush(stderr);
    abort();
}

static void run_one_cycle(void) {
    for (int guard = 0; gc_debug_stage() == ST_IDLE; ++guard) {
        if (guard > 100000) fail("cycle did not start", gc_debug_stage());
        gc_debug_step();
    }
    for (int guard = 0; gc_debug_stage() != ST_IDLE; ++guard) {
        if (guard > 1000000) fail("cycle did not finish", gc_debug_stage());
        gc_debug_step();
    }
}

// Each step runs in a frame of its own, so no copy of an address lingers for
// the conservative stack scan; scrub() overwrites what those frames left.
static void __attribute__((noinline)) create_and_root(void) {
    object_t* volatile k = object_create(&leaf_vt);
    GC_ROOT_STORE(_slots[0], 1, k);
    g_K = (uintptr_t)k;
    object_t* volatile m = object_create(&mutable_vt);
    g_M = (uintptr_t)m;
    object_t* volatile p = object_create(&parent_vt);
    ((struct parent*)p)->slot = m;   // construction: fresh, no barrier owed
    GC_ROOT_STORE(_slots[1], 1, p);
    g_P = (uintptr_t)p;
    k = m = p = NULL;
}

static void __attribute__((noinline)) churn_filler(void) {
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

static int gen(uintptr_t o)   { return gc_debug_object_generation((object_t*)o); }
static int state(uintptr_t o) { return gc_debug_object_state((object_t*)o); }

static void _entrypoint(object_t* self, fun_t cont) {
    (void)self; _exit_cont = cont;
    gc_debug_manual_mode = true;
    while (gc_debug_stage() == 0) usleep(1000);   // wait for the collector
    while (gc_debug_stage() != ST_IDLE) gc_debug_step();

    // (1) K and P promote; P carded for M.
    create_and_root();
    scrub();
    for (int cycles = 0; gen(g_K) != 1 || gen(g_P) != 1; ++cycles) {
        if (cycles > 25) fail(gen(g_K) != 1 ? "K never promoted"
                                            : "P, pointing at a young object, never promoted", 0);
        churn_filler();
        scrub();
        run_one_cycle();
    }
    if (gen(g_M) != 0) fail("a mutable object promoted", gen(g_M));

    // (2) Minors trace P's card.
    for (int cycles = 0; cycles < 3; ++cycles) {
        churn_filler();
        scrub();
        run_one_cycle();
        if (state(g_M) != 1) fail("a minor reclaimed the young object a card holds", state(g_M));
        if (gen(g_P) != 1)   fail("P left the old generation", gen(g_P));
    }

    // (3) A major keeps old pages old.
    gc_debug_request_major();
    scrub();
    run_one_cycle();
    if (gen(g_K) != 1)   fail("a major demoted K", gen(g_K));
    if (gen(g_P) != 1)   fail("a major demoted P", gen(g_P));
    if (state(g_M) != 1) fail("a major reclaimed M", state(g_M));
    run_one_cycle();     // a minor after the major still traces the card
    if (state(g_M) != 1) fail("the minor after a major reclaimed M", state(g_M));

    // (4) Unrooted, a major reclaims all three.
    gc_root_overwrite(&_slots[0], 3);
    _slots[0] = _slots[1] = NULL;
    gc_debug_request_major();
    scrub();
    run_one_cycle();
    if (state(g_K) == 1) fail("a major kept unreachable old K", state(g_K));
    if (state(g_P) == 1) fail("a major kept unreachable old P", state(g_P));
    if (state(g_M) == 1) fail("a major kept unreachable M", state(g_M));

    printf("test_gc_cards: OK\n");
    fflush(stdout);
    ((void(*)(object_t*,object_t*))_exit_cont.f)(_exit_cont.o, integer_from_int32(0));
}

int main(void) {
    // As test_gc_gen: a small heap and a low promotion floor, so pages
    // promote after a few batches of filler. Set before any allocation.
    setenv("YAFL_HEAP_SIZE", "64m", 0);
    setenv("YAFL_GC_PROMOTE_FLOOR", "64", 0);
    _prev = add_roots_declaration_func(_decl);
    thread_start(_entrypoint);
    return 0;
}
