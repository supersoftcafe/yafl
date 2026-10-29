// Deterministic, single-stepped test: compaction must not evacuate a
// DIRTY-OLD page in a minor cycle.
//
// An old page is never traced by a minor cycle, and it may point into a
// dirty-old page (gc_object_refs_are_old accepts one: a dirty-old page is
// force-marked as a root every minor, so its objects stay live). If a minor's
// prune then COMPACTS that dirty-old page, its objects move and leave
// forwarders behind. The old referrer is not traced, so its field is never
// snapped to the copy and nothing records that it still needs the forwarder:
// the forwarder's slot is reclaimed, reused, and the old object reads
// whatever moved in (the -O3 self-compile with YAFL_LOCAL_GC=0: a
// PsDestructure whose list pointed at a DictNode).
//
// A dirty-old page goes sparse only if it was sparse when it promoted, which
// a conservative reference allows: it pins the page against compaction while
// the page ages.
//
//   1. M (mutable, so never old) and B (small, B.f = M) on a page that holds
//      nothing else live; A (half a page, A.f = B) rooted. A stack reference
//      to B pins B's page while the cycles run, until B's page is dirty-old
//      (B points at M, which never promotes) and A's page is old.
//   2. The stack reference goes. One more cycle: B's page is pruned as a
//      dirty-old page, sparse and no longer pinned.
//   3. A is old, so A.f must still be a live object, not a forwarder, then
//      and for the cycles after.
// Run with YAFL_THREADS=1; uses gc_debug_manual_mode, as test_gc_gen does.

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

// Must match enum gc_stage in object.c.
enum { ST_IDLE = 1 };

// Half a page: A's page is never sparse, so the compactor leaves it alone.
struct parent { object_t parent; object_t* f; char pad[8192 - sizeof(object_t) - sizeof(object_t*)]; };
static vtable_t parent_vt = {
    .object_size = sizeof(struct parent), .array_el_size = 0,
    .object_pointer_locations = maskof(struct parent, .f),
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 0, .name = "dc_parent", .implements_array = VTABLE_IMPLEMENTS(0),
};
struct node { object_t parent; object_t* f; };
static vtable_t node_vt = {
    .object_size = sizeof(struct node), .array_el_size = 0,
    .object_pointer_locations = maskof(struct node, .f),
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 0, .name = "dc_node", .implements_array = VTABLE_IMPLEMENTS(0),
};
// Mutable: a mutable page never promotes, so B can never be fully old.
struct leaf { object_t parent; intptr_t x; };
static vtable_t leaf_vt = {
    .object_size = sizeof(struct leaf), .array_el_size = 0,
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 1, .name = "dc_leaf", .implements_array = VTABLE_IMPLEMENTS(0),
};
// Filler, bigger than half a page so it never shares A's page.
struct fill { object_t parent; char pad[12 * 1024 - sizeof(object_t)]; };
static vtable_t fill_vt = {
    .object_size = sizeof(struct fill), .array_el_size = 0,
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 0, .name = "dc_fill", .implements_array = VTABLE_IMPLEMENTS(0),
};

static object_t*                _slots[1];   // A
static roots_declaration_func_t _prev;
static void _decl(void(*declare)(object_t**)) { _prev(declare); declare(&_slots[0]); }

// The addresses, where the collector does not look.
static volatile uintptr_t g_A, g_B;
static fun_t _exit_cont;

static void fail(const char* what, int got) {
    fprintf(stderr, "test_gc_dirty_compact: FAIL %s (got %d)\n", what, got);
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

static gc_page_t* page_of(uintptr_t o) {
    return (gc_page_t*)(o & ~(uintptr_t)(GC_PAGE_SIZE - 1));
}

// Each step runs in a frame of its own, so no copy of an address lingers for
// the conservative stack scan; scrub() overwrites what those frames left.
static void __attribute__((noinline)) create(void) {
    object_t* m = object_create(&leaf_vt);
    object_t* b = object_create(&node_vt);
    ((struct node*)b)->f = m;
    // Garbage that fills B's page past room for A; it dies at the first
    // prune and leaves B's page sparse.
    volatile object_t* spacer = object_create(&fill_vt);
    (void)spacer;
    object_t* a = object_create(&parent_vt);
    ((struct parent*)a)->f = b;
    memset(((struct parent*)a)->pad, 0x5a, sizeof ((struct parent*)a)->pad);
    GC_ROOT_STORE(_slots[0], 1, a);
    g_A = (uintptr_t)a;
    g_B = (uintptr_t)b;
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

// The pin: a conservative reference to B, held in a frame that stays live
// across the cycles, as a deep caller's spilled register would.
static void __attribute__((noinline)) age_while_pinned(void) {
    volatile uintptr_t pin = g_B;
    for (int cycles = 0; !(page_of(g_B)->head.dirty_old
                           && gc_debug_object_generation((object_t*)g_A) == 1); ++cycles) {
        if (cycles > 40) fail("B's page never became dirty-old with A old", cycles);
        churn_filler();
        scrub();
        run_one_cycle();
    }
    if (page_of(g_B)->head.compacted) fail("B's page was compacted while pinned", 1);
    __asm__ volatile("" :: "r"(pin));
}

static void check_a(const char* when) {
    if (gc_debug_object_generation((object_t*)g_A) != 1)
        fail("A left the old generation", gc_debug_object_generation((object_t*)g_A));
    object_t* f = ((struct parent*)g_A)->f;
    if (vtable_is_forward(f->vtable)) {
        fprintf(stderr, "test_gc_dirty_compact: %s\n", when);
        fail("an old object points at a forwarder: its dirty-old target was compacted in a minor", 0);
    }
    if (gc_debug_object_state(f) != 1) {
        fprintf(stderr, "test_gc_dirty_compact: %s\n", when);
        fail("an old object's target was reclaimed", gc_debug_object_state(f));
    }
}

static void _entrypoint(object_t* self, fun_t cont) {
    (void)self; _exit_cont = cont;
    gc_debug_manual_mode = true;
    while (gc_debug_stage() == 0) usleep(1000);   // wait for the collector
    step_to(ST_IDLE);

    // (1) A, B and M; age them while B's page is pinned.
    create();
    scrub();
    if (page_of(g_A) == page_of(g_B)) fail("A shares B's page", 0);
    age_while_pinned();
    scrub();

    // (2) and (3): the pin is gone; B's page is pruned as dirty-old.
    for (int cycles = 0; cycles < 6; ++cycles) {
        churn_filler();
        scrub();
        run_one_cycle();
        check_a(cycles == 0 ? "the cycle after the pin went" : "a later cycle");
    }
    printf("test_gc_dirty_compact: OK (B's page compacted=%d dirty_old=%d)\n",
           page_of(g_B)->head.compacted, page_of(g_B)->head.dirty_old);
    fflush(stdout);
    ((void(*)(object_t*,object_t*))_exit_cont.f)(_exit_cont.o, integer_from_int32(0));
}

int main(void) {
    // As test_gc_old_late_write: a small heap and a low promotion floor, so
    // the pages promote after a few batches of filler. Set before any
    // allocation.
    setenv("YAFL_HEAP_SIZE", "64m", 0);
    setenv("YAFL_GC_PROMOTE_FLOOR", "64", 0);
    _prev = add_roots_declaration_func(_decl);
    thread_start(_entrypoint);
    return 0;
}
