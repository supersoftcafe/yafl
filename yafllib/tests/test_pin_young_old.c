// The fast-fail pin (object_try_pin_young) refuses an object on an OLD page,
// leaving the pin bit and the page's flags alone, and holds on a young one.
// P is promoted exactly as test_gc_old_late_write does (rooted, cycled with
// filler churn until its page is old). Run with YAFL_THREADS=1; manual mode.

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
static volatile uintptr_t g_P;
static fun_t _exit_cont;

static void fail(const char* what, int got) {
    fprintf(stderr, "test_pin_young_old: FAIL %s (got %d)\n", what, got);
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

static int P_generation(void) { return gc_debug_object_generation((object_t*)g_P); }

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

    // Old: refused, nothing changed.
    object_t* p = (object_t*)g_P;
    vtable_t* before = p->vtable;
    if (object_try_pin_young(p)) fail("fast pin took an object on an old page", 0);
    if (p->vtable != before) fail("a refused fast pin changed the vtable word", 0);
    if (vtable_is_pinned(p->vtable)) fail("a refused fast pin left the pin bit", 0);
    if (P_generation() != 1) fail("the refusal demoted the page", P_generation());

    // Young: a fresh object holds, double-pin refuses, unpin restores.
    object_t* y = object_create(&leaf_vt);
    if (!object_try_pin_young(y)) fail("fast pin refused a young object", 0);
    if (!vtable_is_pinned(y->vtable)) fail("fast pin held without the pin bit", 0);
    if (object_try_pin_young(y)) fail("a second fast pin succeeded on a pinned object", 0);
    object_unpin(y);
    if (vtable_is_pinned(y->vtable)) fail("unpin left the bit", 0);
    if (!object_try_pin_young(y)) fail("fast pin refused after unpin", 0);
    object_unpin(y);

    // A forwarded word (tag bit clear): this address is a stale copy.
    object_t* z = object_create(&leaf_vt);
    vtable_t* zvt = z->vtable;
    z->vtable = (vtable_t*)(uintptr_t)(((uintptr_t)y) & ~(uintptr_t)3);
    bool took = object_try_pin_young(z);
    z->vtable = zvt;
    if (took) fail("fast pin took a forwarded object", 0);

    // Off the managed heap: refused.
    static object_t fake;
    if (object_try_pin_young(&fake)) fail("fast pin took a non-heap object", 0);

    printf("test_pin_young_old: OK\n");
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
