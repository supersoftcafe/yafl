// Deterministic, single-stepped test: a YOUNG page that a carded OLD object
// points into is compacted in a minor, and the old object follows the move.
//
// An old page is never traced by a minor, so an old object's field that
// pointed at an evacuated object would keep the forwarder's address, nothing
// would keep the forwarder, and its slot would be reclaimed and reused under
// the old referrer (the -O3 self-compile, before cards: a PsDestructure whose
// list pointed at a DictNode). Cards close it: an old object that points at a
// young one is carded, every minor traces its fields at the end of
// SCAN_ROOTS, and that trace rewrites a field past a forwarder to the copy.
//
//   1. A (half a page, rooted) is cycled until its page is old.
//   2. B (small, carrying an id) is born on a page whose other occupant, a
//      spacer, is garbage; B is late-written into A's slot under the pin,
//      which cards A, and dropped everywhere else.
//   3. Cycles: the spacer dies, B's page is sparse and is compacted. After
//      every cycle A is still old and A's slot reaches a live B with its id;
//      a slot that held a forwarder when a cycle began has been rewritten by
//      the time it ends.
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
extern int  gc_debug_object_carded(object_t* o);       // -1 not-heap, 0 no, 1 yes

// Must match enum gc_stage in object.c.
enum { ST_IDLE = 1 };
enum { B_ID = 0x5eed };

// Half a page: A's page is never sparse, so the compactor leaves it alone.
struct parent { object_t parent; object_t* f; char pad[8192 - sizeof(object_t) - sizeof(object_t*)]; };
static vtable_t parent_vt = {
    .object_size = sizeof(struct parent), .array_el_size = 0,
    .object_pointer_locations = maskof(struct parent, .f),
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 0, .name = "cc_parent", .implements_array = VTABLE_IMPLEMENTS(0),
};
struct node { object_t parent; intptr_t id; };
static vtable_t node_vt = {
    .object_size = sizeof(struct node), .array_el_size = 0,
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 0, .name = "cc_node", .implements_array = VTABLE_IMPLEMENTS(0),
};
// Filler, bigger than half a page so it never shares A's page; also B's
// spacer, which leaves B's page sparse when it dies.
struct fill { object_t parent; char pad[12 * 1024 - sizeof(object_t)]; };
static vtable_t fill_vt = {
    .object_size = sizeof(struct fill), .array_el_size = 0,
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 0, .name = "cc_fill", .implements_array = VTABLE_IMPLEMENTS(0),
};

static object_t*                _slots[1];   // A
static roots_declaration_func_t _prev;
static void _decl(void(*declare)(object_t**)) { _prev(declare); declare(&_slots[0]); }

// The addresses, where the collector does not look: a local holding one
// across a cycle would be a conservative root, and pin the page it names.
static volatile uintptr_t g_A, g_B, g_before;
static volatile bool      g_forwarded_before;
static fun_t _exit_cont;

static void fail(const char* what, int got) {
    fprintf(stderr, "test_gc_card_compact: FAIL %s (got %d)\n", what, got);
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
static void __attribute__((noinline)) create_parent(void) {
    object_t* volatile a = object_create(&parent_vt);
    memset(((struct parent*)a)->pad, 0x5a, sizeof ((struct parent*)a)->pad);
    GC_ROOT_STORE(_slots[0], 1, a);
    g_A = (uintptr_t)a;
    a = NULL;
}

static void __attribute__((noinline)) create_child(void) {
    object_t* volatile b = object_create(&node_vt);
    ((struct node*)b)->id = B_ID;
    volatile object_t* spacer = object_create(&fill_vt);   // garbage on B's page
    (void)spacer;
    g_B = (uintptr_t)b;
    b = NULL;
}

// The late write, as `pin`, `:=` and `unpin` make one: it cards A.
static void __attribute__((noinline)) late_write(void) {
    object_t* owner = object_pin((object_t*)g_A);
    __atomic_store_n((uintptr_t*)&((struct parent*)owner)->f, (uintptr_t)g_B, __ATOMIC_RELEASE);
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
    __asm__ volatile("" :: "r"(junk[0]), "r"(junk[511]) : ARCH_CALLEE_SAVED_CLOBBERS);
}

static void __attribute__((noinline)) note_slot(void) {
    object_t* f = ((struct parent*)g_A)->f;
    g_before = (uintptr_t)f;
    g_forwarded_before = vtable_is_forward(f->vtable);
}

static bool __attribute__((noinline)) slot_unchanged(void) {
    return (uintptr_t)((struct parent*)g_A)->f == g_before;
}

// A is old, and its slot reaches a live B: through the forwarder if B has
// just been moved, never through a reclaimed object.
static void __attribute__((noinline)) check_a(const char* when) {
    if (gc_debug_object_generation((object_t*)g_A) != 1)
        fail("A left the old generation", gc_debug_object_generation((object_t*)g_A));
    object_t* f = ((struct parent*)g_A)->f;
    object_t* b = object_resolve(f);
    if (gc_debug_object_state(f) != 1 || gc_debug_object_state(b) != 1) {
        fprintf(stderr, "test_gc_card_compact: %s\n", when);
        fail("an old object's carded slot was reclaimed under it", gc_debug_object_state(b));
    }
    if (((struct node*)b)->id != B_ID) {
        fprintf(stderr, "test_gc_card_compact: %s\n", when);
        fail("an old object's carded slot reads another object", (int)((struct node*)b)->id);
    }
}

static void _entrypoint(object_t* self, fun_t cont) {
    (void)self; _exit_cont = cont;
    gc_debug_manual_mode = true;
    while (gc_debug_stage() == 0) usleep(1000);   // wait for the collector
    step_to(ST_IDLE);

    // (1) A onto an old page.
    create_parent();
    scrub();
    for (int cycles = 0; gc_debug_object_generation((object_t*)g_A) != 1; ++cycles) {
        if (cycles > 25) fail("A never promoted", gc_debug_object_generation((object_t*)g_A));
        churn_filler();
        scrub();
        run_one_cycle();
    }

    // (2) B, late-written into A.
    create_child();
    if (page_of(g_A) == page_of(g_B)) fail("A shares B's page", 0);
    late_write();
    scrub();
    if (gc_debug_object_carded((object_t*)g_A) != 1) fail("the late write did not card A", 0);

    // (3) B's page compacts; A follows.
    // A slot that holds a forwarder when a minor starts must hold something
    // else after it: the card's trace rewrote it. (Possibly another
    // forwarder: the copy can land on a page that is itself sparse, and be
    // moved again by the same cycle's prune.)
    bool moved = false;
    for (int cycles = 0; cycles < 8; ++cycles) {
        note_slot();
        churn_filler();
        scrub();
        run_one_cycle();
        check_a("after a cycle");
        if (g_forwarded_before && slot_unchanged())
            fail("a minor did not rewrite a carded slot past its forwarder", cycles);
        moved |= page_of(g_B)->head.compacted;
    }
    if (!moved) fail("B's page never compacted: the test did not reach its case", 0);
    printf("test_gc_card_compact: OK\n");
    fflush(stdout);
    ((void(*)(object_t*,object_t*))_exit_cont.f)(_exit_cont.o, integer_from_int32(0));
}

int main(void) {
    // As test_gc_old_late_write: a small heap and a low promotion floor, so
    // A promotes after a few batches of filler. Set before any allocation.
    setenv("YAFL_HEAP_SIZE", "64m", 0);
    setenv("YAFL_GC_PROMOTE_FLOOR", "64", 0);
    _prev = add_roots_declaration_func(_decl);
    thread_start(_entrypoint);
    return 0;
}
