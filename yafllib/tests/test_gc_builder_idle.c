// Deterministic, single-stepped test: list-builder links made around a
// nursery stand-down, and links into a chain that has escaped.
//
// A thread whose nursery has stood down has no active nursery: what it
// allocates lands on epoch-0 pages, which no nursery collects, so its links
// owe no escape for the cell they store (gc_local_barrier_inactive). When the
// nursery resumes, a cell born in it and linked into a builder cell born
// while stood down must escape: the nursery does not trace the older cell.
//
//   1. Rooted filler makes the nursery unproductive until it stands down.
//   2. Stood down: P0 -> C0 linked, and P1 allocated, both P0 and P1 rooted.
//   3. Root scans until the nursery resumes.
//   4. C1, born in the resumed nursery, linked into P1, and dropped.
//      Then P2, born in the nursery and escaped by rooting it, linked to C2,
//      and C2 to C3: straight after each link, before any flush, the new
//      cell must test shared, because other threads can now reach it.
//   5. Unrooted churn runs nursery collections; then a full cycle.
//   6. C0 to C3 must still be the cells they were, reachable from P0 to P2.
//
// Without the escape at the link (step 4), the first nursery collection frees
// C1 while P1 points at it. A link that notes BEFORE its store leaves C2
// pending, still private, and the next link into it skips its barrier.
// Run with YAFL_THREADS=1 and YAFL_GC_POISON=1.

#include "../yafl.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

extern bool gc_debug_manual_mode;
extern int  gc_debug_stage(void);
extern void gc_debug_step(void);

// Must match enum gc_stage in object.c.
enum { ST_IDLE = 1 };

enum { MARK = 0x5a };

// A list cell, as the list builder links them: the link is its last pointer.
struct cell { object_t parent; int64_t id; object_t* next; char pad[88]; };
static vtable_t cell_vt = {
    .object_size = sizeof(struct cell), .array_el_size = 0,
    .object_pointer_locations = maskof(struct cell, .next),
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 0, .name = "idle_cell", .implements_array = VTABLE_IMPLEMENTS(0),
};
// The terminator a fresh cell holds, static as the generated ChainEnd is.
struct end { object_t parent; };
static vtable_t end_vt = {
    .object_size = sizeof(struct end), .array_el_size = 0,
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 0, .name = "idle_end", .implements_array = VTABLE_IMPLEMENTS(0),
};
static struct end END = { .parent = { .vtable = (vtable_t*)((char*)&end_vt + VTABLE_TAG_BIT) } };
// Filler: rooted, it makes every nursery collection unproductive.
struct fill { object_t parent; char pad[4096 - sizeof(object_t)]; };
static vtable_t fill_vt = {
    .object_size = sizeof(struct fill), .array_el_size = 0,
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 0, .name = "idle_fill", .implements_array = VTABLE_IMPLEMENTS(0),
};

enum { FILLERS = 2048 };
static object_t*                _fill[FILLERS];
static object_t*                _slots[3];   // P0, P1, P2
static roots_declaration_func_t _prev;
static void _decl(void(*declare)(object_t**)) {
    _prev(declare);
    for (int i = 0; i < FILLERS; ++i) declare(&_fill[i]);
    declare(&_slots[0]); declare(&_slots[1]); declare(&_slots[2]);
}

// Cells are named by an id, not an address: compaction may move a sealed
// cell, and the link that holds it follows.
static int64_t g_slot, g_next_id;
static fun_t _exit_cont;

static void fail(const char* what, long got) {
    fprintf(stderr, "test_gc_builder_idle: FAIL %s (got %ld)\n", what, got);
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
static object_t* __attribute__((noinline)) new_cell(void) {
    object_t* c = object_new(&cell_vt, true);   // pinned, as the builder's cells are
    ((struct cell*)c)->id = g_next_id++;
    ((struct cell*)c)->next = &END.parent;
    memset(((struct cell*)c)->pad, MARK, sizeof ((struct cell*)c)->pad);
    return c;
}

// (1) Rooted filler until the nursery has been active and stood down.
static void __attribute__((noinline)) stand_down(void) {
    bool was_active = false;
    for (int i = 0; i < FILLERS; ++i) {
        object_t* f = object_create(&fill_vt);
        GC_ROOT_STORE(_fill[i], 1, f);
        was_active |= gc_alloc_tl.local_active;
        if (was_active && !gc_alloc_tl.local_active) return;
    }
    fail("the nursery never stood down; was it active", was_active);
}

// (2) Stood down: a whole link, and the older half of the next one.
static void __attribute__((noinline)) build_idle(void) {
    object_t* p0 = new_cell();
    object_t* c0 = new_cell();
    g_slot = list_builder_slot(c0);
    list_builder_link(p0, c0, g_slot);
    list_builder_seal(c0);
    GC_ROOT_STORE(_slots[0], 1, p0);
    object_t* p1 = new_cell();
    GC_ROOT_STORE(_slots[1], 1, p1);
}

// (4) Resumed: the younger half, born in the nursery.
static void __attribute__((noinline)) link_resumed(void) {
    object_t* c1 = new_cell();
    list_builder_link(_slots[1], c1, g_slot);
    list_builder_seal(c1);

    object_t* p2 = new_cell();
    if (!gc_local_obj_private(p2)) fail("a fresh nursery cell is not private", 2);
    GC_ROOT_STORE(_slots[2], 1, p2);
    if (gc_local_obj_private(p2)) fail("rooting did not escape P2", 2);
    object_t* c2 = new_cell();
    list_builder_link(p2, c2, g_slot);
    if (gc_local_obj_private(c2)) fail("a cell linked into an escaped cell still tests private", 2);
    object_t* c3 = new_cell();
    list_builder_link(c2, c3, g_slot);
    if (gc_local_obj_private(c3)) fail("a cell linked into an escaped cell still tests private", 3);
    list_builder_seal(c3);
}

// (5) Unrooted churn: nursery collections.
static void __attribute__((noinline)) churn(void) {
    for (int i = 0; i < 512; ++i) {
        volatile object_t* f = object_create(&fill_vt);
        (void)f;
    }
}

static void __attribute__((noinline)) scrub(void) {
    volatile uintptr_t junk[512];
    for (int i = 0; i < 512; ++i) junk[i] = (uintptr_t)(i * 2 + 1);
    __asm__ volatile("" :: "r"(junk[0]), "r"(junk[511]) : ARCH_CALLEE_SAVED_CLOBBERS);
}

// The cell after `p` is intact and has id `id`; return it.
static struct cell* check(const char* which, object_t* p, int64_t id) {
    struct cell* c = (struct cell*)object_resolve(((struct cell*)object_resolve(p))->next);
    if (vtable_untag(c->parent.vtable) != &cell_vt) fail(which, id);
    if (c->id != id) fail("a link holds the wrong cell", (long)c->id);
    for (size_t i = 0; i < sizeof c->pad; ++i)
        if ((unsigned char)c->pad[i] != MARK) fail("a linked cell was overwritten", (long)id);
    return c;
}

static void _entrypoint(object_t* self, fun_t cont) {
    (void)self; _exit_cont = cont;
    gc_debug_manual_mode = true;
    while (gc_debug_stage() == 0) usleep(1000);   // wait for the collector
    while (gc_debug_stage() != ST_IDLE) gc_debug_step();

    stand_down();
    build_idle();
    scrub();
    if (gc_alloc_tl.local_active) fail("the nursery resumed early", 1);

    // (3) A stood-down nursery resumes at a root scan.
    for (int cycles = 0; !gc_alloc_tl.local_active; ++cycles) {
        if (cycles > 200) fail("the nursery never resumed", cycles);
        run_one_cycle();
    }

    link_resumed();
    scrub();
    churn();
    scrub();
    if (!gc_alloc_tl.local_active) fail("the nursery stood down during the churn", 0);
    run_one_cycle();

    // Ids in creation order: P0 0, C0 1, P1 2, C1 3, P2 4, C2 5, C3 6.
    if (check("the idle link lost its cell", _slots[0], 1)->next != &END.parent)
        fail("the idle chain grew", 1);
    if (check("the resumed link lost its cell", _slots[1], 3)->next != &END.parent)
        fail("the resumed chain grew", 3);
    struct cell* c2 = check("the escaped chain lost its cell", _slots[2], 5);
    if (check("the escaped chain lost its second cell", &c2->parent, 6)->next != &END.parent)
        fail("the escaped chain grew", 6);
    printf("test_gc_builder_idle: OK\n");
    fflush(stdout);
    ((void(*)(object_t*,object_t*))_exit_cont.f)(_exit_cont.o, integer_from_int32(0));
}

int main(void) {
    // Nursery collections every two pages, so the stand-down comes quickly
    // and the churn runs several. Set before any allocation.
    setenv("YAFL_HEAP_SIZE", "64m", 0);
    setenv("YAFL_LOCAL_GC_PAGES", "2", 0);
    _prev = add_roots_declaration_func(_decl);
    thread_start(_entrypoint);
    return 0;
}
