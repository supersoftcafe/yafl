// Deterministic, single-stepped test: a late write into an OLD page made
// between the cycle's START and the writer's own root scan.
//
// The ragged snapshot finds whatever a thread moves from its stack into the
// heap before its own root scan by tracing the heap afterwards. An `old` page
// is not traced by a minor cycle, so a late write landing on one in that
// window — the writer then dropping the value — is seen only because the end
// of SCAN_ROOTS demotes the pages late writes touched (gc_demote_redirtied,
// object.c), as START does.
//
//   1. P (immutable, half a page) is rooted and cycled until its page is old.
//   2. C (mutable, so it stays young) is allocated while the collector is
//      idle — not allocated black — and parked where the collector does not
//      look.
//   3. The cycle opens; stepping stops on entering SCAN_ROOTS, before this
//      thread's scan.
//   4. C is late-written into P's slot (pin, gc_note_late_write, store,
//      unpin), and dropped from the stack.
//   5. The cycle finishes. P's slot is C's only reference: C must be live.
//
// Without the demotion at the end of SCAN_ROOTS, P's page stays old for the
// cycle, nothing traces its slot, and C is reclaimed while P points at it.
// Run with YAFL_THREADS=1; uses gc_debug_manual_mode, as test_gc_gen does.

#include "../yafl.h"
#include "callee_saved.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

extern bool gc_debug_manual_mode;
extern int  gc_debug_stage(void);
extern void gc_debug_step(void);
extern int  gc_debug_object_state(object_t* o);        // 0 not-heap, 1 live, 2 reclaimed
extern int  gc_debug_object_generation(object_t* o);   // -1 not-heap, 0 young, 1 old

// Must match enum gc_stage in object.c.
enum { ST_IDLE = 1, ST_SCAN_ROOTS = 3 };

// Half a page, so P's page is never sparse and the compactor leaves it alone.
struct parent { object_t parent; object_t* slot; char pad[8192 - sizeof(object_t) - sizeof(object_t*)]; };
static vtable_t parent_vt = {
    .object_size = sizeof(struct parent), .array_el_size = 0,
    .object_pointer_locations = maskof(struct parent, .slot),
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 0, .name = "old_parent", .implements_array = VTABLE_IMPLEMENTS(0),
};
// Mutable: a mutable page never promotes, so C stays young, reclaimable by
// any cycle that fails to trace it, and never moves.
struct leaf { object_t parent; char pad[8192 - sizeof(object_t)]; };
static vtable_t leaf_vt = {
    .object_size = sizeof(struct leaf), .array_el_size = 0,
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 1, .name = "young_leaf", .implements_array = VTABLE_IMPLEMENTS(0),
};
// Filler, bigger than half a page so it never shares P's page.
struct fill { object_t parent; char pad[12 * 1024 - sizeof(object_t)]; };
static vtable_t fill_vt = {
    .object_size = sizeof(struct fill), .array_el_size = 0,
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 0, .name = "old_fill", .implements_array = VTABLE_IMPLEMENTS(0),
};

static object_t*                _slots[1];   // P
static roots_declaration_func_t _prev;
static void _decl(void(*declare)(object_t**)) { _prev(declare); declare(&_slots[0]); }

// The addresses, where the collector does not look.
static volatile uintptr_t g_P, g_C;
static fun_t _exit_cont;

static void fail(const char* what, int got) {
    fprintf(stderr, "test_gc_old_late_write: FAIL %s (got %d)\n", what, got);
    fflush(stderr);
    abort();
}

static void step_to(int target) {
    for (int guard = 0; gc_debug_stage() != target; ++guard) {
        if (guard > 1000000) fail("stuck before stage", gc_debug_stage());
        gc_debug_step();
    }
}

static void run_one_cycle(void) {
    for (int guard = 0; gc_debug_stage() == ST_IDLE; ++guard) {
        if (guard > 100000) fail("cycle did not start", gc_debug_stage());
        gc_debug_step();
    }
    step_to(ST_IDLE);
}

// Each step runs in a frame of its own, so no copy of an address lingers for
// the conservative stack scan; scrub() overwrites what those frames left.
static void __attribute__((noinline)) create_and_root_parent(void) {
    object_t* p = object_create(&parent_vt);
    ((struct parent*)p)->slot = NULL;
    memset(((struct parent*)p)->pad, 0x5a, sizeof ((struct parent*)p)->pad);
    GC_ROOT_STORE(_slots[0], 1, p);
    g_P = (uintptr_t)p;
}

static void __attribute__((noinline)) allocate_child(void) {
    object_t* c = object_create(&leaf_vt);
    memset(((struct leaf*)c)->pad, 0x5a, sizeof ((struct leaf*)c)->pad);
    g_C = (uintptr_t)c;
}

// The late write, as once.c makes one.
static void __attribute__((noinline)) late_write(void) {
    object_t* owner = object_pin_resolve((object_t*)g_P);
    gc_note_late_write(owner);
    __atomic_store_n((uintptr_t*)&((struct parent*)owner)->slot, (uintptr_t)g_C, __ATOMIC_RELEASE);
    object_unpin(owner);
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
    __asm__ volatile("" :: "r"(junk[0]), "r"(junk[511]) : CALLEE_SAVED_CLOBBERS);
}

static int P_generation(void) { return gc_debug_object_generation((object_t*)g_P); }
static int C_state(void)      { return gc_debug_object_state((object_t*)g_C); }

static void _entrypoint(object_t* self, fun_t cont) {
    (void)self; _exit_cont = cont;
    gc_debug_manual_mode = true;
    while (gc_debug_stage() == 0) usleep(1000);   // wait for the collector
    step_to(ST_IDLE);

    // (1) P onto an old page.
    create_and_root_parent();
    scrub();
    for (int cycles = 0; P_generation() != 1; ++cycles) {
        if (cycles > 25) fail("P never promoted", P_generation());
        churn_filler();
        scrub();
        run_one_cycle();
    }

    // (2) C, while idle.
    allocate_child();
    scrub();

    // (3) Open the cycle; stop before this thread's root scan.
    step_to(ST_SCAN_ROOTS);
    if (P_generation() != 1) fail("P's page left the old generation early", P_generation());

    // (4) The late write, then drop C.
    late_write();
    scrub();

    // (5) Finish the cycle.
    step_to(ST_IDLE);
    int st = C_state();
    printf("test_gc_old_late_write: after the cycle C_state=%d (1=live, 2=reclaimed)\n", st);
    if (st != 1) fail("a late write into an old page before its writer's scan lost its value", st);
    printf("test_gc_old_late_write: OK\n");
    fflush(stdout);
    ((void(*)(object_t*,object_t*))_exit_cont.f)(_exit_cont.o, integer_from_int32(0));
}

int main(void) {
    // As test_gc_gen: a small heap and a low promotion floor, so P promotes
    // after a few batches of filler. Set before any allocation.
    setenv("YAFL_HEAP_SIZE", "64m", 0);
    setenv("YAFL_GC_PROMOTE_FLOOR", "64", 0);
    _prev = add_roots_declaration_func(_decl);
    thread_start(_entrypoint);
    return 0;
}
