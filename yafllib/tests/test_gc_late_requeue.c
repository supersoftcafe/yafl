// Deterministic, single-stepped test: a request to rescan a page that arrives
// after marking has retired must not take the page out of the cycle's prune.
//
// A mark executor pumps the reprocess ring after its page loop, with no stage
// check, so a rescan request (page_needs_scan) can arrive once the tail has
// retired the stage to PRUNE. Honoured, it moves the page from pages_to_prune
// back to pages_to_scan: the page skips this prune, its seen/scanned bitmaps
// are never reset, and the next cycle's page pass (seen & ~scanned) skips
// every object on it that this cycle scanned — their children are not traced,
// and are reclaimed while they are reachable.
//
//   1. X (mutable, rooted) holds Y (mutable, held by X alone).
//   2. A cycle runs; once marking has retired (the probe, compiled into this
//      target alone: YAFL_GC_RETIRE_PROBE), X's page is asked to be rescanned.
//   3. Two more cycles run. Y must still be live.
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
extern void gc_test_page_needs_scan(void* page);

enum { ST_IDLE = 1 };

// Both mutable: mutable pages never promote (so minor cycles keep tracing
// them) and are never relocated (so the addresses stay stable).
struct holder { object_t parent; object_t* child; char pad[8192 - sizeof(object_t) - sizeof(object_t*)]; };
static vtable_t holder_vt = {
    .object_size = sizeof(struct holder), .array_el_size = 0,
    .object_pointer_locations = maskof(struct holder, .child),
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 1, .name = "requeue_holder", .implements_array = VTABLE_IMPLEMENTS(0),
};
struct leaf { object_t parent; char pad[8192 - sizeof(object_t)]; };
static vtable_t leaf_vt = {
    .object_size = sizeof(struct leaf), .array_el_size = 0,
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 1, .name = "requeue_leaf", .implements_array = VTABLE_IMPLEMENTS(0),
};

static object_t*                _slots[1];   // X
static roots_declaration_func_t _prev;
static void _decl(void(*declare)(object_t**)) { _prev(declare); declare(&_slots[0]); }

// The addresses, where the collector does not look.
static volatile uintptr_t g_X, g_Y;
static bool  g_armed;
static int   g_fired;
static fun_t _exit_cont;

void gc_test_retire_probe(void) {
    if (!g_armed) return;
    g_armed = false;
    gc_test_page_needs_scan((void*)((uintptr_t)g_X & ~(uintptr_t)(GC_PAGE_SIZE - 1)));
    g_fired = 1;
}

static void fail(const char* what, int got) {
    fprintf(stderr, "test_gc_late_requeue: FAIL %s (got %d)\n", what, got);
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
// conservative stack scan; scrub() overwrites what the frame left.
static void __attribute__((noinline)) build(void) {
    object_t* x = object_create(&holder_vt);
    object_t* y = object_create(&leaf_vt);
    memset(((struct leaf*)y)->pad, 0x5a, sizeof ((struct leaf*)y)->pad);
    GC_STORE_IN(x, ((struct holder*)x)->child, 1, y);
    GC_ROOT_STORE(_slots[0], 1, x);
    g_X = (uintptr_t)x;
    g_Y = (uintptr_t)y;
}

static void __attribute__((noinline)) scrub(void) {
    volatile uintptr_t junk[512];
    for (int i = 0; i < 512; ++i) junk[i] = (uintptr_t)(i * 2 + 1);
    __asm__ volatile("" :: "r"(junk[0]), "r"(junk[511]) : ARCH_CALLEE_SAVED_CLOBBERS);
}

static int Y_state(void) { return gc_debug_object_state((object_t*)g_Y); }

static void _entrypoint(object_t* self, fun_t cont) {
    (void)self; _exit_cont = cont;
    gc_debug_manual_mode = true;
    while (gc_debug_stage() == 0) usleep(1000);   // wait for the collector
    while (gc_debug_stage() != ST_IDLE) gc_debug_step();

    build();
    scrub();

    g_armed = true;
    run_one_cycle();
    if (!g_fired) fail("the probe did not run", 0);
    for (int i = 0; i < 2; ++i) {
        scrub();
        run_one_cycle();
    }
    int st = Y_state();
    printf("test_gc_late_requeue: after the cycles Y_state=%d (1=live, 2=reclaimed)\n", st);
    if (st != 1) fail("a rescan request after marking ended lost a reachable object", st);
    printf("test_gc_late_requeue: OK\n");
    fflush(stdout);
    ((void(*)(object_t*,object_t*))_exit_cont.f)(_exit_cont.o, integer_from_int32(0));
}

int main(void) {
    setenv("YAFL_HEAP_SIZE", "64m", 0);
    _prev = add_roots_declaration_func(_decl);
    thread_start(_entrypoint);
    return 0;
}
