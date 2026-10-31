// Deterministic, single-stepped test: object_pin_set (yafl.h), the runtime
// half of `__builtin_pin_set__`, on each of its paths.
//
//   1. PENDING SCAN. The cycle is open and this thread's root scan has not
//      run, so the fill goes out of line (object_pin_set_pending) and pays
//      the insertion half. Y, allocated now, is born marked; V, allocated
//      while idle, is reachable only from this thread's stack, and dropped
//      after the fill: it must survive, and Y's slot hold it. This checks the
//      path is right, not that it is needed: the half matters only for an
//      object a PEER's marking has already scanned, and with one thread
//      nothing is marked before this thread's own scan.
//   2. TAKEN. A second fill of Y's slot answers V and leaves the slot alone.
//   3. A PEER'S PIN. Another thread holds Z's pin: the fill waits for the
//      release, then stores.
//   4. MOVED. M's page compacts; the fill goes through the STALE pointer and
//      lands in the copy. A read that resolves first sees it; the stub's own
//      body does not — the caller's stale copy stays stale.
//   5. OLD. P's page is old: the fill cards P, and minors keep the value
//      alive through the card.
// Run with YAFL_THREADS=1; uses gc_debug_manual_mode.

#include "../yafl.h"
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

extern bool gc_debug_manual_mode;
extern int  gc_debug_stage(void);
extern void gc_debug_step(void);
extern int  gc_debug_object_state(object_t* o);        // 0 not-heap, 1 live, 2 reclaimed
extern int  gc_debug_object_generation(object_t* o);   // -1 not-heap, 0 young, 1 old
extern int  gc_debug_object_carded(object_t* o);

// Must match enum gc_stage in object.c.
enum { ST_IDLE = 1, ST_SCAN_ROOTS = 3 };
enum { FILLERS = 300 };

struct node { object_t parent; object_t* slot; intptr_t id; };
static vtable_t node_vt = {
    .object_size = sizeof(struct node), .array_el_size = 0,
    .object_pointer_locations = maskof(struct node, .slot),
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 0, .name = "ps_node", .implements_array = VTABLE_IMPLEMENTS(0),
};
// Half a page, so P's page is never sparse and the compactor leaves it alone.
struct parent { object_t parent; object_t* slot; char pad[8192 - sizeof(object_t) - sizeof(object_t*)]; };
static vtable_t parent_vt = {
    .object_size = sizeof(struct parent), .array_el_size = 0,
    .object_pointer_locations = maskof(struct parent, .slot),
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 0, .name = "ps_parent", .implements_array = VTABLE_IMPLEMENTS(0),
};
// Mutable: a mutable page never promotes, so a value stays young,
// reclaimable by any cycle that fails to trace it, and never moves.
struct leaf { object_t parent; char pad[8192 - sizeof(object_t)]; };
static vtable_t leaf_vt = {
    .object_size = sizeof(struct leaf), .array_el_size = 0,
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 1, .name = "ps_leaf", .implements_array = VTABLE_IMPLEMENTS(0),
};
struct small { object_t parent; intptr_t x; };
static vtable_t small_vt = {
    .object_size = sizeof(struct small), .array_el_size = 0,
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 0, .name = "ps_small", .implements_array = VTABLE_IMPLEMENTS(0),
};
// Churn, bigger than half a page so it never shares a page with the others.
struct fill { object_t parent; char pad[12 * 1024 - sizeof(object_t)]; };
static vtable_t churn_vt = {
    .object_size = sizeof(struct fill), .array_el_size = 0,
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 0, .name = "ps_churn", .implements_array = VTABLE_IMPLEMENTS(0),
};

enum { ROOT_Y = FILLERS, ROOT_Z, ROOT_M, ROOT_P, ROOT_KEEP, ROOTS };
static object_t*                _roots[ROOTS];
static roots_declaration_func_t _prev;
static void _decl(void(*declare)(object_t**)) {
    _prev(declare);
    for (int i = 0; i < ROOTS; ++i) declare(&_roots[i]);
}

// The addresses, where the collector does not look: a local holding one
// across a cycle would be a conservative root, and pin the page it names.
static volatile uintptr_t g_Y, g_V, g_W, g_Z, g_M, g_P;
static fun_t _exit_cont;

static void fail(const char* what, int got) {
    fprintf(stderr, "test_gc_pin_set: FAIL %s (got %d)\n", what, got);
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

static void __attribute__((noinline)) scrub(void) {
    volatile uintptr_t junk[512];
    for (int i = 0; i < 512; ++i) junk[i] = (uintptr_t)(i * 2 + 1);
    __asm__ volatile("" :: "r"(junk[0]), "r"(junk[511]) : ARCH_CALLEE_SAVED_CLOBBERS);
}

static void __attribute__((noinline)) churn(void) {
    for (int i = 0; i < 170; ++i) {
        volatile object_t* f = object_create(&churn_vt);
        (void)f;
    }
}

static void __attribute__((noinline)) drop(int from, int to) {
    for (int i = from; i < to; ++i) {
        gc_root_overwrite(&_roots[i], 1);
        _roots[i] = NULL;
    }
}

static object_t* __attribute__((noinline)) fill(uintptr_t o, size_t offset, uintptr_t v) {
    return object_pin_set((object_t*)o, offset, (object_t*)v);
}

static void __attribute__((noinline)) new_leaf(volatile uintptr_t* into) {
    object_t* v = object_create(&leaf_vt);
    memset(((struct leaf*)v)->pad, 0x5a, sizeof ((struct leaf*)v)->pad);
    *into = (uintptr_t)v;
}

static int state(uintptr_t o) { return gc_debug_object_state((object_t*)o); }
static int gen(uintptr_t o)   { return gc_debug_object_generation((object_t*)o); }

// ── 1, 2: pending scan, then taken ──────────────────────────────────────────

// Unrooted for this cycle: born marked, Y lives through it.
static void __attribute__((noinline)) create_y(void) {
    object_t* y = object_create(&node_vt);
    g_Y = (uintptr_t)y;
}

static void pending_then_taken(void) {
    new_leaf(&g_V);                 // while idle: not born marked
    scrub();
    step_to(ST_SCAN_ROOTS);
    if (!(atomic_load_explicit(&gc_alloc_tl.safe_point_request, memory_order_relaxed)
          & GC_SAFE_POINT_SCAN_ROOTS))
        fail("this thread's root scan is not pending: the test cannot reach its case", 0);
    create_y();                     // born marked: never scanned this cycle
    if (fill(g_Y, offsetof(struct node, slot), g_V) != NULL)
        fail("an empty slot did not answer NULL", 0);
    scrub();
    step_to(ST_IDLE);
    if (state(g_V) != 1) fail("a value filled before this thread's scan was reclaimed", state(g_V));
    if (((struct node*)g_Y)->slot != (object_t*)g_V) fail("the pending fill did not store", 0);

    new_leaf(&g_W);
    if (fill(g_Y, offsetof(struct node, slot), g_W) != (object_t*)g_V)
        fail("a taken slot did not answer its value", 0);
    if (((struct node*)g_Y)->slot != (object_t*)g_V) fail("a taken slot was overwritten", 0);
    scrub();
    GC_ROOT_STORE(_roots[ROOT_Y], 1, (object_t*)g_Y);   // for the cycles to come
}

// ── 3: a peer holds the pin ─────────────────────────────────────────────────

static _Atomic int peer_holds, peer_released;

static void* peer(void* arg) {
    (void)arg;
    while (!object_try_pin((object_t*)g_Z)) {}
    atomic_store(&peer_holds, 1);
    usleep(50 * 1000);
    atomic_store(&peer_released, 1);
    object_unpin((object_t*)g_Z);
    return NULL;
}

static void __attribute__((noinline)) create_z(void) {
    object_t* z = object_create(&node_vt);
    GC_ROOT_STORE(_roots[ROOT_Z], 1, z);
    g_Z = (uintptr_t)z;
}

static void peer_pin(void) {
    create_z();
    new_leaf(&g_V);
    GC_ROOT_STORE(_roots[ROOT_KEEP], 1, (object_t*)g_V);
    pthread_t t;
    if (pthread_create(&t, NULL, peer, NULL) != 0) fail("pthread_create", 0);
    while (!atomic_load(&peer_holds)) {}
    if (fill(g_Z, offsetof(struct node, slot), g_V) != NULL)
        fail("a fill after a peer's pin did not answer NULL", 0);
    if (!atomic_load(&peer_released)) fail("the fill did not wait for the peer's pin", 0);
    pthread_join(t, NULL);
    if (((struct node*)g_Z)->slot != (object_t*)g_V) fail("the fill after a peer's pin did not store", 0);
    scrub();
}

// ── 4: moved ────────────────────────────────────────────────────────────────

static void __attribute__((noinline)) create_m(void) {
    object_t* m = object_create(&node_vt);
    GC_ROOT_STORE(_roots[ROOT_M], 1, m);
    g_M = (uintptr_t)m;
    for (int i = 0; i < FILLERS; ++i) {
        object_t* volatile f = object_create(&small_vt);
        GC_ROOT_STORE(_roots[i], 1, f);
        f = NULL;
    }
    m = NULL;
}

static void moved(void) {
    create_m();
    scrub();
    drop(0, FILLERS);               // M's page is sparse, with deaths: no promotion
    for (int cycles = 0; !vtable_is_forward(((object_t*)g_M)->vtable); ++cycles) {
        if (cycles > 4) fail("M's sparse page was not compacted", 0);
        churn();
        scrub();
        run_one_cycle();
    }
    new_leaf(&g_V);
    GC_ROOT_STORE(_roots[ROOT_KEEP], 1, (object_t*)g_V);
    if (fill(g_M, offsetof(struct node, slot), g_V) != NULL)
        fail("a fill through a moved object did not answer NULL", 0);
    object_t* copy = object_resolve((object_t*)g_M);
    if (copy == (object_t*)g_M || object_resolve(_roots[ROOT_M]) != copy)
        fail("the root does not reach the copy", 0);
    if (((struct node*)copy)->slot != (object_t*)g_V) fail("the fill did not land in the copy", 0);
    // The caller's stale copy stays stale: the stub's own body still reads
    // empty. Only a read that resolves first sees the store.
    if (((struct node*)g_M)->slot != NULL) fail("the stub's body was written", 0);
    new_leaf(&g_W);
    if (fill(g_M, offsetof(struct node, slot), g_W) != (object_t*)g_V)
        fail("a second fill through the stale pointer did not answer the copy's value", 0);
    scrub();
}

// ── 5: old ──────────────────────────────────────────────────────────────────

static void __attribute__((noinline)) create_p(void) {
    object_t* p = object_create(&parent_vt);
    ((struct parent*)p)->slot = NULL;
    memset(((struct parent*)p)->pad, 0x5a, sizeof ((struct parent*)p)->pad);
    GC_ROOT_STORE(_roots[ROOT_P], 1, p);
    g_P = (uintptr_t)p;
}

static void old_target(void) {
    create_p();
    scrub();
    for (int cycles = 0; gen(g_P) != 1; ++cycles) {
        if (cycles > 25) fail("P never promoted", gen(g_P));
        churn();
        scrub();
        run_one_cycle();
    }
    new_leaf(&g_V);
    if (fill(g_P, offsetof(struct parent, slot), g_V) != NULL)
        fail("a fill into an old object did not answer NULL", 0);
    scrub();
    if (!gc_debug_object_carded((object_t*)g_P)) fail("a fill into an old object did not card it", 0);
    for (int cycles = 0; cycles < 3; ++cycles) {
        churn();
        scrub();
        run_one_cycle();
        if (state(g_V) != 1) fail("a carded slot's value was reclaimed by a minor", state(g_V));
        if (gen(g_P) != 1) fail("P's page left the old generation", gen(g_P));
    }
}

static void _entrypoint(object_t* self, fun_t cont) {
    (void)self; _exit_cont = cont;
    gc_debug_manual_mode = true;
    while (gc_debug_stage() == 0) usleep(1000);   // wait for the collector
    step_to(ST_IDLE);

    pending_then_taken();
    peer_pin();
    moved();
    old_target();

    printf("test_gc_pin_set: OK\n");
    fflush(stdout);
    ((void(*)(object_t*,object_t*))_exit_cont.f)(_exit_cont.o, integer_from_int32(0));
}

int main(void) {
    // As test_gc_gen: a small heap and a low promotion floor, so P promotes
    // after a few batches of churn. Set before any allocation.
    setenv("YAFL_HEAP_SIZE", "64m", 0);
    setenv("YAFL_GC_PROMOTE_FLOOR", "64", 0);
    _prev = add_roots_declaration_func(_decl);
    thread_start(_entrypoint);
    return 0;
}
