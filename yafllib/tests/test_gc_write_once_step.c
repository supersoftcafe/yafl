// Deterministic, single-threaded test of the WRITE-ONCE inline store
// (gc_store_owes_nothing, yafl.h) while a cycle marks.
//
// A store whose overwritten slots are all NULL owes the snapshot nothing: the
// deletion half shades the overwritten value, and there is none. Its
// insertion half — shading the stored value, for a thread whose own root scan
// is still to come — is what keeps a value the thread moves from its unscanned
// stack into a container the cycle never traces. So the store may stay inline
// only once this thread has been scanned:
//
//   1. The cycle opens; stepping stops in SCAN_ROOTS, before this thread's
//      scan. A write-once store must call out (the grey slot).
//   2. After the scan, while marking: a write-once store stays inline; a store
//      that overwrites a value still calls out (the deletion half).
//   3. The store is made, the cycle finishes, and the stored value survives.
//
// The hazard in (1) needs a second thread — a container born after ANOTHER
// thread's scan — so on one thread a missing grey slot cannot be seen as a
// reclaim; this test pins the decision itself instead. Run with
// YAFL_THREADS=1.

#include "../yafl.h"
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

extern bool gc_debug_manual_mode;
extern int  gc_debug_stage(void);
extern void gc_debug_step(void);
extern int  gc_debug_object_state(object_t* o);   // 0 not-heap, 1 live, 2 reclaimed

// Must match enum gc_stage in object.c.
enum { ST_IDLE = 1, ST_SCAN_ROOTS = 3, ST_MARK_SWEEP = 4 };

struct holder { object_t parent; object_t* f; };
static vtable_t holder_vt = {
    .object_size = sizeof(struct holder), .array_el_size = 0,
    .object_pointer_locations = maskof(struct holder, .f),
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 0, .name = "wo_holder", .implements_array = VTABLE_IMPLEMENTS(0),
};

static object_t*                _slots[2];   // [0] P, written once; [1] Q, already full
static roots_declaration_func_t _prev;
static void _decl(void(*declare)(object_t**)) { _prev(declare); declare(&_slots[0]); declare(&_slots[1]); }
static volatile uintptr_t g_V;
static fun_t _exit_cont;

static void fail(const char* what) {
    fprintf(stderr, "test_gc_write_once_step: FAIL %s\n", what);
    fflush(stderr);
    abort();
}

static void step_to(int target) {
    for (int g = 0; gc_debug_stage() != target; ++g) {
        if (g > 1000000) fail("stuck before stage");
        gc_debug_step();
    }
}

// The store family's mask is relative to the FIELD: bit 0 is its first word.
static bool inline_store(object_t* obj) {
    return gc_store_owes_nothing(&((struct holder*)obj)->f, 1);
}

static void _entrypoint(object_t* self, fun_t cont) {
    (void)self; _exit_cont = cont;
    gc_debug_manual_mode = true;
    while (gc_debug_stage() == 0) usleep(1000);
    step_to(ST_IDLE);

    object_t* p = object_create(&holder_vt);
    GC_ROOT_STORE(_slots[0], 1, p);
    object_t* q = object_create(&holder_vt);
    ((struct holder*)q)->f = object_create(&holder_vt);   // fresh: no barrier owed
    GC_ROOT_STORE(_slots[1], 1, q);
    object_t* v = object_create(&holder_vt);
    g_V = (uintptr_t)v;

    // (1) Marking, this thread not yet scanned.
    step_to(ST_SCAN_ROOTS);
    if (!gc_write_barrier_requested) fail("no cycle marking in SCAN_ROOTS");
    if (inline_store(p)) fail("a write-once store stayed inline with this thread's scan pending");

    // (2) Marking, this thread scanned.
    step_to(ST_MARK_SWEEP);
    if (!gc_write_barrier_requested) fail("no cycle marking in MARK_SWEEP");
    if (!inline_store(p)) fail("a write-once store called out after this thread's scan");
    if (inline_store(q)) fail("a store overwriting a value stayed inline while marking");

    // (3) The store, then the rest of the cycle.
    GC_STORE_IN(p, ((struct holder*)p)->f, 1, v);
    v = NULL;
    step_to(ST_IDLE);
    if (gc_debug_object_state((object_t*)g_V) != 1) fail("the stored value was reclaimed");
    if (((struct holder*)_slots[0])->f != (object_t*)g_V) fail("the slot lost the stored value");

    printf("test_gc_write_once_step: OK\n");
    fflush(stdout);
    ((void(*)(object_t*,object_t*))_exit_cont.f)(_exit_cont.o, integer_from_int32(0));
}

int main(void) {
    _prev = add_roots_declaration_func(_decl);
    thread_start(_entrypoint);
    return 0;
}
