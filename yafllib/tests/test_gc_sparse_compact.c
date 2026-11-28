// Deterministic, single-stepped test (#134): compaction empties a page in a
// nearly-free block whatever its occupancy, so the block's window opens for a
// multi-page run; the same page in a busy block is left alone.
//
// Pages are claimed in order on a small heap, one 12 KiB object each:
//
//   32 rooted | H2 | 32 rooted | 32 unrooted | H | 32 unrooted | rooted ...
//
// H and H2 are half a page each (rooted), above the ordinary compaction
// threshold. The rooted tail fills the heap until the singles watermark
// meets the runs band. A cycle frees the unrooted pages, leaving H's block
// sparse and H2's busy, with most of the heap still live: H must move, H2
// must not.
// Run with YAFL_THREADS=1; uses gc_debug_manual_mode.

#include "../yafl.h"
#include "../gc_stage.h"
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

extern bool   gc_debug_manual_mode;
extern int    gc_debug_stage(void);
extern void   gc_debug_step(void);
extern int    gc_debug_object_state(object_t* o);   // 0 not-heap, 1 live, 2 reclaimed
extern size_t memory_watermark(void);
extern size_t memory_run_floor(void);

enum { ZONE = 32, MAX_ROOTS = 1024, H_ID = 0x5ba25e, H2_ID = 0xb05e };

// Half a page: above the ordinary 33% compaction threshold.
struct half { object_t parent; intptr_t id; char pad[8192 - sizeof(object_t) - sizeof(intptr_t)]; };
static vtable_t half_vt = {
    .object_size = sizeof(struct half), .array_el_size = 0,
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 0, .name = "sc_half", .implements_array = VTABLE_IMPLEMENTS(0),
};
// Bigger than half a page, so each one takes a page of its own.
struct fill { object_t parent; char pad[12 * 1024 - sizeof(object_t)]; };
static vtable_t fill_vt = {
    .object_size = sizeof(struct fill), .array_el_size = 0,
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 0, .name = "sc_fill", .implements_array = VTABLE_IMPLEMENTS(0),
};

static object_t*                _roots[MAX_ROOTS];
static int                      _root_count = 0;
static roots_declaration_func_t _prev;
static void _decl(void(*declare)(object_t**)) {
    _prev(declare);
    for (int i = 0; i < _root_count; ++i) declare(&_roots[i]);
}

// The addresses, where the collector does not look: a local holding one
// across a cycle would be a conservative root, and pin the page it names.
static volatile uintptr_t g_H, g_H2;
static volatile int       g_H_root, g_H2_root;
static fun_t _exit_cont;

static void fail(const char* what, int got) {
    fprintf(stderr, "test_gc_sparse_compact: FAIL %s (got %d)\n", what, got);
    fflush(stderr);
    abort();
}

static void run_one_cycle(void) {
    for (int guard = 0; gc_debug_stage() == GC_STAGE_IDLE; ++guard) {
        if (guard > 100000) fail("cycle did not start", gc_debug_stage());
        gc_debug_step();
    }
    for (int guard = 0; gc_debug_stage() != GC_STAGE_IDLE; ++guard) {
        if (guard > 1000000) fail("cycle did not finish", gc_debug_stage());
        gc_debug_step();
    }
}

static int __attribute__((noinline)) rooted(object_t* o) {
    if (_root_count == MAX_ROOTS) fail("out of roots", _root_count);
    GC_ROOT_STORE(_roots[_root_count], 1, o);
    _root_count++;
    return _root_count - 1;
}

static void __attribute__((noinline)) fills(int count, bool keep) {
    for (int i = 0; i < count; ++i) {
        object_t* volatile f = object_create(&fill_vt);
        if (keep) rooted(f);
        f = NULL;
    }
}

static int __attribute__((noinline)) half(volatile uintptr_t* where, intptr_t id) {
    object_t* volatile h = object_create(&half_vt);
    ((struct half*)h)->id = id;
    *where = (uintptr_t)h;
    int root = rooted(h);
    h = NULL;
    return root;
}

static void __attribute__((noinline)) create(void) {
    fills(ZONE, true);
    g_H2_root = half(&g_H2, H2_ID);
    fills(ZONE, true);
    fills(ZONE, false);
    g_H_root = half(&g_H, H_ID);
    fills(ZONE, false);
    while (memory_run_floor() - memory_watermark() >= ZONE / 2)
        fills(1, true);
}

static void __attribute__((noinline)) scrub(void) {
    volatile uintptr_t junk[512];
    for (int i = 0; i < 512; ++i) junk[i] = (uintptr_t)(i * 2 + 1);
    __asm__ volatile("" :: "r"(junk[0]), "r"(junk[511]) : ARCH_CALLEE_SAVED_CLOBBERS);
}

static bool moved(uintptr_t o) {
    return gc_debug_object_state((object_t*)o) == 1
        && vtable_is_forward(((object_t*)o)->vtable);
}

// The root still reaches its object, with its id, through any forwarder.
static void __attribute__((noinline)) check_root(int root, intptr_t id, const char* what) {
    object_t* o = object_resolve(_roots[root]);
    if (gc_debug_object_state(o) != 1 || ((struct half*)o)->id != id) fail(what, root);
}

static void _entrypoint(object_t* self, fun_t cont) {
    (void)self; _exit_cont = cont;
    gc_debug_manual_mode = true;
    while (gc_debug_stage() == GC_STAGE_NOT_STARTED) usleep(1000);   // wait for the collector
    while (gc_debug_stage() != GC_STAGE_IDLE) gc_debug_step();

    create();
    scrub();
    bool h_moved = false;
    for (int cycles = 0; cycles < 4 && !h_moved; ++cycles) {
        run_one_cycle();
        scrub();
        h_moved = moved(g_H);
        if (moved(g_H2)) fail("a half-full page in a busy block was compacted", cycles);
    }
    if (!h_moved) fail("a half-full page in a sparse block was not compacted", 0);
    check_root(g_H_root, H_ID, "H's root lost it");
    check_root(g_H2_root, H2_ID, "H2's root lost it");

    printf("test_gc_sparse_compact: OK\n");
    fflush(stdout);
    ((void(*)(object_t*,object_t*))_exit_cont.f)(_exit_cont.o, integer_from_int32(0));
}

int main(void) {
    // 512 pages: small enough to fill. Set before any allocation.
    setenv("YAFL_HEAP_SIZE", "8m", 0);
    _prev = add_roots_declaration_func(_decl);
    thread_start(_entrypoint);
    return 0;
}
