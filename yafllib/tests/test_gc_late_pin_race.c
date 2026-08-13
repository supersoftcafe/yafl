// Deterministic regression test for the promotion-vs-late-pin race: the
// Dekker handshake between gc_note_late_write and the promotion decision.
//
// The hazard: promotion is check-then-act. Prune's refs walk can pass an
// object BEFORE a mutator late-pins it, and set the page's `old` flag AFTER
// the mutator's gc_note_late_write read it as false. The page then joins the
// old generation holding a young edge that neither side flagged — minor
// cycles skip old pages, so nothing traces the referent and prune reclaims
// it while the structure is live.
//
// The window is a few instructions inside gc_fsa_prune_body, so this test
// target compiles its own object.c with YAFL_GC_RACE_PROBE, which inserts a
// hook exactly between the refs walk and the old-claim. The hook (below)
// performs a late write — pin, note, store a rooted-until-now YOUNG child
// into the aging parent's slot, unpin — inside the window, deterministically.
//
//   Without the handshake: the note reads `old` == false and sets nothing,
//   the page promotes, the child's root is dropped, and the next minor
//   reclaims the child (under YAFL_GC_POISON its bytes become 0x42). FAILS.
//   With it: the note set `redirty` before reading `old`, the promotion's
//   re-check consumes the flag and demotes to dirty_old — force-marked every
//   cycle — so the child stays traced and live. PASSES.
//
// Same manual-mode scaffolding as test_gc_gen.c: small heap so the promotion
// volume is a couple of filler batches, 8 KB objects so pages are never
// sparse (the compactor leaves them alone and addresses stay stable).

#include "../yafl.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

extern bool gc_debug_manual_mode;
extern int  gc_debug_stage(void);
extern void gc_debug_step(void);
extern int  gc_debug_object_state(object_t* o);        // 0 not-heap, 1 live, 2 reclaimed
extern int  gc_debug_object_generation(object_t* o);   // -1 not-heap, 0 young, 1 old

enum { ST_IDLE = 1 };

// Parent: one late-written slot, padded to half a page. The slot starts NULL
// and is filled exactly once, inside the probe window, mirroring a memoize
// publication (once.c) without the trie around it.
struct parent { object_t parent; object_t* slot; char pad[8192 - sizeof(object_t) - sizeof(object_t*)]; };
static vtable_t parent_vt = {
    .object_size = sizeof(struct parent), .array_el_size = 0,
    .object_pointer_locations = maskof(struct parent, .slot),
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 0, .name = "race_parent", .implements_array = VTABLE_IMPLEMENTS(0),
};

// Child: no pointers, MUTABLE. Not because the scenario needs mutation —
// because an immutable stable leaf promotes right alongside the parent, and
// an OLD child is exempt from the minor cycles the assertions run, so the
// test would pass vacuously with or without the handshake (the test_gc_step2
// lesson). A mutable page never promotes: C stays young — reclaimable by any
// minor that fails to trace it — for as long as the test cares to check.
// Mutable objects are also never relocated, so C's address is stable.
struct leaf { object_t parent; char pad[8192 - sizeof(object_t)]; };
static vtable_t leaf_vt = {
    .object_size = sizeof(struct leaf), .array_el_size = 0,
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 1, .name = "race_leaf", .implements_array = VTABLE_IMPLEMENTS(0),
};

// Filler: bigger than half a page so it never shares a page with P or C (a
// dying neighbour would reset their promotion clocks).
struct fill { object_t parent; char pad[12 * 1024 - sizeof(object_t)]; };
static vtable_t fill_vt = {
    .object_size = sizeof(struct fill), .array_el_size = 0,
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 0, .name = "race_fill", .implements_array = VTABLE_IMPLEMENTS(0),
};

static object_t*                _slots[2];    // [0] parent P, [1] child C until the write
static roots_declaration_func_t _prev;
static void _decl(void(*declare)(object_t**)) { _prev(declare); declare(&_slots[0]); declare(&_slots[1]); }

static volatile uintptr_t g_P, g_C;
static volatile int g_armed = 0, g_fired = 0;
static fun_t _exit_cont;

static void fail(const char* what, long got) {
    fprintf(stderr, "test_gc_late_pin_race: FAIL %s (got %ld)\n", what, got);
    fflush(stderr);
    abort();
}

// The window hook: runs on the stepping thread inside gc_fsa_prune_body,
// between the refs walk of `page` and its old-claim. When armed and handed
// P's page, perform the late write exactly as once.c does.
void gc_test_race_probe(gc_page_t* page) {
    if (!g_armed) return;
    if (((uintptr_t)g_P & ~(uintptr_t)(GC_PAGE_SIZE-1)) != (uintptr_t)page) return;
    g_armed = 0;
    object_t* owner = object_pin_resolve((object_t*)g_P);
    gc_note_late_write(owner);
    __atomic_store_n((uintptr_t*)&((struct parent*)owner)->slot, (uintptr_t)g_C,
                     __ATOMIC_RELEASE);
    object_unpin(owner);
    // Drop C's root NOW: from here on the only path to C is P's slot, on the
    // page whose promotion decision is mid-flight around us.
    GC_WRITE_BARRIER(_slots[1], 1);
    _slots[1] = NULL;
    g_fired = 1;
    // Leave no copy of C's address in this frame or in callee-saved
    // registers for the conservative scan to find — a leaked copy would
    // root C and mask the very reclaim the test exists to detect.
    owner = NULL;
    __asm__ volatile("" :: "r"(owner) : "memory",
        "rbx", "r12", "r13", "r14", "r15");
}

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

// Allocate + root in a frame of their own so no stale copies of the
// addresses linger for the conservative stack scan.
static void __attribute__((noinline)) create_and_root(void) {
    object_t* p = object_create(&parent_vt);
    ((struct parent*)p)->slot = NULL;
    memset(((struct parent*)p)->pad, 0x5a, sizeof ((struct parent*)p)->pad);
    GC_WRITE_BARRIER(_slots[0], 1);
    _slots[0] = p;
    g_P = (uintptr_t)p;
    object_t* c = object_create(&leaf_vt);
    memset(((struct leaf*)c)->pad, 0x5a, sizeof ((struct leaf*)c)->pad);
    GC_WRITE_BARRIER(_slots[1], 1);
    _slots[1] = c;
    g_C = (uintptr_t)c;
}

static void __attribute__((noinline)) scrub(void) {
    volatile uintptr_t junk[512];
    for (int i = 0; i < 512; ++i) junk[i] = (uintptr_t)(i * 2 + 1);
    __asm__ volatile("" :: "r"(junk[0]), "r"(junk[511]) : "memory",
        "rbx", "r12", "r13", "r14", "r15");
}

static void __attribute__((noinline)) churn_filler(void) {
    for (int i = 0; i < 170; ++i) {
        volatile object_t* f = object_create(&fill_vt);
        (void)f;
    }
}

static void _entrypoint(object_t* self, fun_t cont) {
    (void)self; _exit_cont = cont;
    gc_debug_manual_mode = true;
    while (gc_debug_stage() == 0) usleep(1000);   // wait for the collector

    create_and_root();
    scrub();
    printf("test_gc_late_pin_race: P=%p C=%p\n", (void*)g_P, (void*)g_C);

    // Arm, then cycle with filler churn until the probe has interleaved the
    // write into P's page's promotion window. Bounded: promotion volume is
    // ~2 MiB on this heap and each churn batch is ~2 MiB.
    g_armed = 1;
    int cycles = 0;
    while (!g_fired) {
        churn_filler();
        scrub();
        run_one_cycle();
        if (++cycles > 25) fail("probe never fired (promotion not attempted)", cycles);
    }
    printf("test_gc_late_pin_race: write landed in the window after %d cycles\n", cycles);

    // The next minor is the one that reclaims C if the handshake is absent:
    // C's root is gone, C is young, and P's page just joined (or was demoted
    // from joining) the old generation. Then a few more for good measure —
    // C must stay traced until P's page legitimately promotes with C old.
    for (int i = 0; i < 4; ++i) {
        churn_filler();
        scrub();
        run_one_cycle();
        int cs = gc_debug_object_state((object_t*)g_C);
        if (cs != 1) fail("young referent reclaimed after cycle", cs);
    }

    // The slot must still hold C, and C's bytes must be intact (poison would
    // have wiped them 0x42 on a reclaim the state query somehow missed).
    object_t* seen = ((struct parent*)object_resolve((object_t*)g_P))->slot;
    if ((uintptr_t)seen != g_C) fail("slot lost the published value", (long)(uintptr_t)seen);
    if (((struct leaf*)(uintptr_t)g_C)->pad[0] != 0x5a) fail("child bytes clobbered",
        ((struct leaf*)(uintptr_t)g_C)->pad[0]);

    printf("test_gc_late_pin_race: OK\n");
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
