// Deterministic, single-threaded test of the root-publish contract.
//
// A value stored into a declared root AFTER the cycle's root snapshot is
// marked only by gc_root_publish. test_gc_step stores an object allocated
// inside the cycle's opening window, which allocate-black already marks, so
// it passes with the publish removed. The case the publish exists for is an
// object allocated BEFORE the cycle opens:
//
//   1. O is allocated before the cycle opens, so it is not allocated black,
//      and its page will join this cycle's pool at this thread's take.
//   2. The cycle opens: the root snapshot reads the slot while it is NULL.
//   3. O is stored into the slot and published, then dropped. Its only
//      reference is the slot; its address is parked in a plain global the
//      collector never scans.
//   4. The take, marking and prune run. Only the publish marked O.
//
// This is the window test_gc_min2_window opens with a sleep, made exact by
// driving the collector by hand (gc_debug_step, gc_debug_manual_mode). With
// the publish's shading removed, O is reclaimed while the slot still points
// at it.
// Run with YAFL_THREADS=1.

#include "../yafl.h"
#include <stdio.h>
#include <string.h>
#include <unistd.h>

extern bool gc_debug_manual_mode;
extern int  gc_debug_stage(void);
extern void gc_debug_step(void);
extern int  gc_debug_object_state(object_t* o);   // 0 not-heap, 1 live, 2 reclaimed

// Must match enum gc_stage in object.c.
enum { ST_NOT_STARTED = 0, ST_IDLE = 1, ST_START = 2,
       ST_SCAN_ROOTS = 3, ST_MARK_SWEEP = 4, ST_PRUNE = 5 };

struct obj { object_t parent; object_t* f; };
static vtable_t obj_vt = {
    .object_size = sizeof(struct obj), .array_el_size = 0,
    .object_pointer_locations = maskof(struct obj, .f),
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 1, .name = "publish_step_obj", .implements_array = VTABLE_IMPLEMENTS(0),
};

static object_t*                _slots[1];
static roots_declaration_func_t _prev;
static void _decl(void(*declare)(object_t**)) { _prev(declare); declare(&_slots[0]); }

// O's address, where the collector does not look.
static volatile uintptr_t g_O;

static fun_t _exit_cont;

// Each step runs in its own frame and returns nothing, so O does not linger
// in the caller's frame; scrub() then overwrites what those frames left.
static __attribute__((noinline)) void allocate(void) {
    g_O = (uintptr_t)object_create(&obj_vt);
}

static __attribute__((noinline)) void store_and_publish(void) {
    gc_root_overwrite(&_slots[0], 1);
    _slots[0] = (object_t*)g_O;
    gc_root_publish(&_slots[0], 1);
}

static __attribute__((noinline)) void scrub(void) {
    volatile char junk[16384];
    memset((char*)junk, 0, sizeof junk);
}

static void step_to(int target) {
    for (int g = 0; gc_debug_stage() != target; ++g) {
        if (g > 100000) { fprintf(stderr, "step_to: stuck at stage %d\n", gc_debug_stage()); abort(); }
        gc_debug_step();
    }
}

static int O_state(void) { return gc_debug_object_state((object_t*)g_O); }

static void _entrypoint(object_t* self, fun_t cont) {
    (void)self;
    _exit_cont = cont;
    gc_debug_manual_mode = true;
    while (gc_debug_stage() == 0) usleep(1000);   // wait for the collector to exist
    step_to(ST_IDLE);

    // (1) Before the cycle opens.
    allocate();
    scrub();
    printf("test_gc_publish_step: O=%p allocated before the cycle\n", (void*)g_O);

    // (2) Open the cycle: the snapshot reads _slots[0] while it is NULL.
    step_to(ST_SCAN_ROOTS);

    // (3) Store and publish after the snapshot, then drop.
    store_and_publish();
    scrub();

    // (4) The take, marking and prune.
    step_to(ST_MARK_SWEEP);
    step_to(ST_PRUNE);
    step_to(ST_IDLE);

    int st = O_state();
    printf("test_gc_publish_step: after prune O_state=%d (1=live, 2=reclaimed); _slots[0]=%p\n",
           st, (void*)_slots[0]);
    if (st == 2)
        printf("test_gc_publish_step: *** BUG: a published root's object was reclaimed ***\n");
    fflush(stdout);

    ((void(*)(object_t*,object_t*))_exit_cont.f)(_exit_cont.o, integer_from_int32(st == 1 ? 0 : 7));
}

int main(void) {
    _prev = add_roots_declaration_func(_decl);
    thread_start(_entrypoint);
    return 0;
}
