/*
 * object_same: reference identity that survives relocation (issue #73).
 *
 * Compaction leaves a forwarding stub behind, so for a while one holder may
 * point at the stub and another at the copy: a raw `==` says "different" for
 * one object. object_same must answer by IDENTITY — true across any
 * forwarding chain, false for distinct objects.
 *
 *   1. Hand-built stubs (no collector involved): the same pointer; distinct
 *      objects; a stub against its copy, both ways round; a two-hop chain
 *      against each of its hops; two stubs of one object; a stub against an
 *      unrelated object.
 *   2. A real compaction (single-stepped, manual mode, as test_gc_fwd_chain):
 *      the stub A and its copy B are the same object; neither is the same as
 *      an unrelated live object.
 *
 * Run with YAFL_THREADS=1; gc_debug_manual_mode so cycles are exact.
 */

#include "../yafl.h"
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

extern bool gc_debug_manual_mode;
extern int  gc_debug_stage(void);
extern void gc_debug_step(void);

enum { ST_IDLE = 1 };

struct leaf { object_t parent; char pad[32 - sizeof(object_t)]; };
static vtable_t leaf_vt = {
    .object_size = sizeof(struct leaf), .array_el_size = 0,
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 0, .name = "same_leaf", .implements_array = VTABLE_IMPLEMENTS(0),
};

static object_t*                _slots[2];
static roots_declaration_func_t _prev;
static void _decl(void(*declare)(object_t**)) {
    _prev(declare); declare(&_slots[0]); declare(&_slots[1]);
}

/* Plain globals are NOT GC roots and not conservatively scanned — safe
 * parking spots for raw addresses the collector must not see. */
static volatile uintptr_t g_A, g_B;
static fun_t _exit_cont;

static void fail(const char* what) {
    fprintf(stderr, "test_gc_object_same: FAIL %s\n", what);
    fflush(stderr);
    abort();
}

static void expect(bool got, bool want, const char* what) {
    if (got != want) fail(what);
}

/* ── 1. hand-built stubs ─────────────────────────────────────────────────── */

/* A live object's word is its tagged vtable; a stub's word is the plain
 * address of its copy (tag bit clear) — exactly what compaction publishes. */
static struct leaf s_live[4];
static struct leaf s_stub[3];

static object_t* live(int i) {
    s_live[i].parent.vtable = vtable_tag(&leaf_vt);
    return &s_live[i].parent;
}

static object_t* stub_to(int i, object_t* target) {
    s_stub[i].parent.vtable = (vtable_t*)target;
    return &s_stub[i].parent;
}

static void check_hand_built(void) {
    object_t* x = live(0);
    object_t* y = live(1);
    expect(object_same(x, x), true,  "same pointer");
    expect(object_same(x, y), false, "distinct objects");

    object_t* copy = live(2);
    object_t* stub = stub_to(0, copy);
    expect(object_same(stub, copy), true,  "stub vs its copy");
    expect(object_same(copy, stub), true,  "copy vs its stub");
    expect(object_same(stub, x),    false, "stub vs unrelated object");
    expect(object_same(x, stub),    false, "unrelated object vs stub");

    /* stub2 -> stub1 -> tail: the copy was itself compacted. */
    object_t* tail  = live(3);
    object_t* stub1 = stub_to(1, tail);
    object_t* stub2 = stub_to(2, stub1);
    expect(object_same(stub2, tail),  true, "two-hop stub vs tail");
    expect(object_same(tail, stub2),  true, "tail vs two-hop stub");
    expect(object_same(stub2, stub1), true, "two-hop stub vs one-hop stub");
    expect(object_same(stub1, stub2), true, "one-hop stub vs two-hop stub");
    expect(object_same(stub2, copy),  false, "two-hop stub vs another copy");

    /* Two stubs of one object (a head stub whose word was compressed past
     * the middle, and the middle itself): equal without either being live. */
    s_stub[2].parent.vtable = (vtable_t*)tail;
    expect(object_same(stub2, stub1), true, "two stubs of one object");

    printf("test_gc_object_same: hand-built stubs OK\n");
}

/* ── 2. a real compaction ────────────────────────────────────────────────── */

static void run_one_cycle(void) {
    int guard = 0;
    do {
        gc_debug_step();
        if (++guard > 100000) fail("cycle did not start");
    } while (gc_debug_stage() == ST_IDLE);
    while (gc_debug_stage() != ST_IDLE) {
        gc_debug_step();
        if (++guard > 1000000) fail("cycle did not finish");
    }
}

/* Allocate + root A, then bury its page in dropped filler so the page is
 * sparse at the next prune. Own frame: A's address must not linger on the
 * entrypoint's stack, or the conservative scan pins the page and the
 * compactor skips it. */
static void __attribute__((noinline)) create_and_bury(void) {
    object_t* volatile k = object_create(&leaf_vt);
    GC_ROOT_STORE(_slots[0], 1, k);
    g_A = (uintptr_t)k;
    k = NULL;
    for (int i = 0; i < 460; ++i) {
        volatile object_t* f = object_create(&leaf_vt);
        (void)f;
    }
}

/* An unrelated live object, rooted. Allocated AFTER the cycle, so it is not
 * on A's page and does not keep that page dense. */
static void __attribute__((noinline)) create_other(void) {
    object_t* volatile o = object_create(&leaf_vt);
    GC_ROOT_STORE(_slots[1], 1, o);
    o = NULL;
}

static void __attribute__((noinline)) scrub(void) {
    volatile uintptr_t junk[512];
    for (int i = 0; i < 512; ++i) junk[i] = (uintptr_t)(i * 2 + 1);
    __asm__ volatile("" :: "r"(junk[0]), "r"(junk[511]) : ARCH_CALLEE_SAVED_CLOBBERS);
}

static void __attribute__((noinline)) check_compacted(void) {
    object_t* a = (object_t*)g_A;
    if (!vtable_is_forward(a->vtable)) fail("A was not compacted into a stub");
    g_B = (uintptr_t)a->vtable;
    object_t* b = (object_t*)g_B;
    object_t* other = _slots[1];
    expect(object_same(a, b),     true,  "compacted stub vs its copy");
    expect(object_same(b, a),     true,  "copy vs its compacted stub");
    expect(object_same(a, other), false, "compacted stub vs unrelated object");
    expect(object_same(other, b), false, "unrelated object vs copy");
    printf("test_gc_object_same: real compaction A=%#lx -> B=%#lx OK\n",
           (long)g_A, (long)g_B);
}

static void _entrypoint(object_t* self, fun_t cont) {
    (void)self; _exit_cont = cont;
    gc_debug_manual_mode = true;
    while (gc_debug_stage() == 0) usleep(1000);

    check_hand_built();

    create_and_bury();
    scrub();
    run_one_cycle();
    create_other();
    check_compacted();

    fflush(stdout);
    ((void(*)(object_t*,object_t*))_exit_cont.f)(_exit_cont.o, integer_from_int32(0));
}

int main(void) {
    _prev = add_roots_declaration_func(_decl);
    thread_start(_entrypoint);
    return 0;
}
