// Deterministic, single-stepped test: a store into a STATIC object (a global
// lazy stub is one: an object with a vtable, outside the heap, its fields
// declared roots) whose barrier ran before the cycle opened.
//
// A heap container needs nothing after its store: the cycle traces it, or it
// was born during the cycle, which means the barrier saw the flag up and the
// hybrid barrier shades the new value. A static object is scanned once, at
// cycle open. A store whose barrier read the flag DOWN — before the cycle
// opened — and which lands after the snapshot leaves the value reachable only
// through a slot the cycle has already read. So the object store macros
// publish after the store when the container is not in the heap
// (GC_PUBLISH_IF_STATIC_IN, yafl.h).
//
//   1. V (mutable, so young and never moved) is allocated while idle — not
//      allocated black — and parked where the collector does not look.
//   2. The store's barrier runs while idle: flag down, nothing shaded.
//   3. The cycle opens: the snapshot reads the static slot while it is NULL.
//   4. The store, then the macro's after-store part; V is dropped.
//   5. The cycle finishes. The static slot is V's only reference: V must be
//      live.
//
// Steps 2 and 4 are GC_STORE_MUTABLE_IN taken apart, as the race takes it
// apart: a store macro has no safe point inside it, but another thread can
// open the cycle between its flag read and its store.
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

// Must match enum gc_stage in object.c.
enum { ST_IDLE = 1, ST_SCAN_ROOTS = 3 };

struct holder { object_t parent; object_t* child; };
static vtable_t holder_vt = {
    .object_size = sizeof(struct holder), .array_el_size = 0,
    .object_pointer_locations = maskof(struct holder, .child),
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 1, .name = "static_holder", .implements_array = VTABLE_IMPLEMENTS(0),
};
struct leaf { object_t parent; char pad[8192 - sizeof(object_t)]; };
static vtable_t leaf_vt = {
    .object_size = sizeof(struct leaf), .array_el_size = 0,
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 1, .name = "static_leaf", .implements_array = VTABLE_IMPLEMENTS(0),
};

// The static object, as generated code lays out a global's lazy stub: its
// pointer field is a declared root.
static struct holder S = { .parent = { .vtable = (vtable_t*)((char*)&holder_vt + VTABLE_TAG_BIT) }, .child = NULL };
static roots_declaration_func_t _prev;
static void _decl(void(*declare)(object_t**)) { _prev(declare); declare(&S.child); }

static volatile uintptr_t g_V;   // V's address, where the collector does not look
static fun_t _exit_cont;

static void fail(const char* what, int got) {
    fprintf(stderr, "test_gc_static_store: FAIL %s (got %d)\n", what, got);
    fflush(stderr);
    abort();
}

static void step_to(int target) {
    for (int guard = 0; gc_debug_stage() != target; ++guard) {
        if (guard > 1000000) fail("stuck before stage", gc_debug_stage());
        gc_debug_step();
    }
}

// Each step in a frame of its own, so no copy of V's address lingers for the
// conservative stack scan; scrub() overwrites what those frames left.
static void __attribute__((noinline)) allocate(void) {
    object_t* v = object_create(&leaf_vt);
    memset(((struct leaf*)v)->pad, 0x5a, sizeof ((struct leaf*)v)->pad);
    g_V = (uintptr_t)v;
}

static void __attribute__((noinline)) barrier_half(void) {
    GC_WRITE_BARRIER_MUTABLE_IN(&S, S.child, 1);
}

static void __attribute__((noinline)) store_half(void) {
    S.child = (object_t*)g_V;
    GC_PUBLISH_IF_STATIC_IN(&S, S.child, 1);
}

static void __attribute__((noinline)) scrub(void) {
    volatile uintptr_t junk[512];
    for (int i = 0; i < 512; ++i) junk[i] = (uintptr_t)(i * 2 + 1);
    __asm__ volatile("" :: "r"(junk[0]), "r"(junk[511]) : ARCH_CALLEE_SAVED_CLOBBERS);
}

static int V_state(void) { return gc_debug_object_state((object_t*)g_V); }

static void _entrypoint(object_t* self, fun_t cont) {
    (void)self; _exit_cont = cont;
    gc_debug_manual_mode = true;
    while (gc_debug_stage() == 0) usleep(1000);   // wait for the collector
    step_to(ST_IDLE);

    allocate();            // (1)
    scrub();
    barrier_half();        // (2) flag down
    step_to(ST_SCAN_ROOTS);   // (3) the snapshot reads S.child == NULL
    store_half();          // (4)
    scrub();
    step_to(ST_IDLE);      // (5)

    int st = V_state();
    printf("test_gc_static_store: after the cycle V_state=%d (1=live, 2=reclaimed)\n", st);
    if (st != 1) fail("a store into a static object, barriered before the cycle, lost its value", st);
    printf("test_gc_static_store: OK\n");
    fflush(stdout);
    ((void(*)(object_t*,object_t*))_exit_cont.f)(_exit_cont.o, integer_from_int32(0));
}

int main(void) {
    setenv("YAFL_HEAP_SIZE", "64m", 0);
    _prev = add_roots_declaration_func(_decl);
    thread_start(_entrypoint);
    return 0;
}
