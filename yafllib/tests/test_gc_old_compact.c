// Deterministic, single-stepped test: a major compacts a sparse OLD page into
// a page born old.
//
// Old stays old, but its garbage still goes, at a major, and a page left
// sparse is compacted like any other. Its copies must land on a page that is
// OLD from birth: their referrers are old, no minor traces those, and a young
// copy would be reclaimed under them. The copies keep the OLD stamp and their
// cards; the vacated page, all forwarders, stays old until the next major's
// trace has rewritten every old referrer past them.
//
//   1. O (carded: it points at M, mutable, which never promotes) sits on a
//      page among fillers, each rooted; R (half a page, rooted) points at O.
//      Cycles until O's and R's pages are old.
//   2. The fillers' roots go: old garbage, which no minor reclaims.
//   3. A major: the fillers die, O's page is sparse and compacts. O's copy is
//      old, stamped and carded.
//   4. Minors: R still reaches O's copy (through the forwarder), and M lives
//      on through the copy's card.
//   5. A major rewrites R's field to the copy; a later one frees the
//      forwarder.
// Run with YAFL_THREADS=1; uses gc_debug_manual_mode.

#include "../yafl.h"
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

extern bool gc_debug_manual_mode;
extern int  gc_debug_stage(void);
extern void gc_debug_step(void);
extern int  gc_debug_object_state(object_t* o);        // 0 not-heap, 1 live, 2 reclaimed
extern int  gc_debug_object_generation(object_t* o);   // -1 not-heap, 0 young, 1 old
extern int  gc_debug_object_carded(object_t* o);       // -1 not-heap, 0 no, 1 yes
extern void gc_debug_request_major(void);

enum { ST_IDLE = 1 };
enum { FILLERS = 300, O_ID = 0x0c0de };

struct node { object_t parent; object_t* f; intptr_t id; };
static vtable_t node_vt = {
    .object_size = sizeof(struct node), .array_el_size = 0,
    .object_pointer_locations = maskof(struct node, .f),
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 0, .name = "oc_node", .implements_array = VTABLE_IMPLEMENTS(0),
};
struct small { object_t parent; intptr_t x; };
static vtable_t filler_vt = {
    .object_size = sizeof(struct small), .array_el_size = 0,
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 0, .name = "oc_filler", .implements_array = VTABLE_IMPLEMENTS(0),
};
static vtable_t mutable_vt = {
    .object_size = sizeof(struct small), .array_el_size = 0,
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 1, .name = "oc_mutable", .implements_array = VTABLE_IMPLEMENTS(0),
};
// Half a page: R's page is never sparse.
struct parent { object_t parent; object_t* f; char pad[8192 - sizeof(object_t) - sizeof(object_t*)]; };
static vtable_t parent_vt = {
    .object_size = sizeof(struct parent), .array_el_size = 0,
    .object_pointer_locations = maskof(struct parent, .f),
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 0, .name = "oc_parent", .implements_array = VTABLE_IMPLEMENTS(0),
};
// Churn, bigger than half a page so it never shares a page with the others.
struct fill { object_t parent; char pad[12 * 1024 - sizeof(object_t)]; };
static vtable_t churn_vt = {
    .object_size = sizeof(struct fill), .array_el_size = 0,
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 0, .name = "oc_churn", .implements_array = VTABLE_IMPLEMENTS(0),
};

static object_t*                _roots[FILLERS + 1];   // the fillers, then R
static roots_declaration_func_t _prev;
static void _decl(void(*declare)(object_t**)) {
    _prev(declare);
    for (int i = 0; i <= FILLERS; ++i) declare(&_roots[i]);
}

// The addresses, where the collector does not look: a local holding one
// across a cycle would be a conservative root, and pin the page it names.
static volatile uintptr_t g_O, g_M, g_R, g_C;
static fun_t _exit_cont;

static void fail(const char* what, int got) {
    fprintf(stderr, "test_gc_old_compact: FAIL %s (got %d)\n", what, got);
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

static gc_page_t* page_of(uintptr_t o) {
    return (gc_page_t*)(o & ~(uintptr_t)(GC_PAGE_SIZE - 1));
}

static void __attribute__((noinline)) create(void) {
    object_t* volatile m = object_create(&mutable_vt);
    g_M = (uintptr_t)m;
    object_t* volatile o = object_create(&node_vt);
    ((struct node*)o)->f = m;          // construction: fresh, no barrier owed
    ((struct node*)o)->id = O_ID;
    g_O = (uintptr_t)o;
    for (int i = 0; i < FILLERS; ++i) {
        object_t* volatile f = object_create(&filler_vt);
        GC_ROOT_STORE(_roots[i], 1, f);
        f = NULL;
    }
    object_t* volatile r = object_create(&parent_vt);
    ((struct parent*)r)->f = o;
    GC_ROOT_STORE(_roots[FILLERS], 1, r);
    g_R = (uintptr_t)r;
    m = o = r = NULL;
}

static void __attribute__((noinline)) drop_fillers(void) {
    for (int i = 0; i < FILLERS; ++i) {
        gc_root_overwrite(&_roots[i], 1);
        _roots[i] = NULL;
    }
}

static void __attribute__((noinline)) churn(void) {
    for (int i = 0; i < 170; ++i) {
        volatile object_t* f = object_create(&churn_vt);
        (void)f;
    }
}

static void __attribute__((noinline)) scrub(void) {
    volatile uintptr_t junk[512];
    for (int i = 0; i < 512; ++i) junk[i] = (uintptr_t)(i * 2 + 1);
    __asm__ volatile("" :: "r"(junk[0]), "r"(junk[511]) : ARCH_CALLEE_SAVED_CLOBBERS);
}

static int gen(uintptr_t o)    { return gc_debug_object_generation((object_t*)o); }
static int state(uintptr_t o)  { return gc_debug_object_state((object_t*)o); }
static int carded(uintptr_t o) { return gc_debug_object_carded((object_t*)o); }

// R reaches a live O with its id, through any forwarders.
static void __attribute__((noinline)) check_r(const char* when) {
    object_t* f = ((struct parent*)g_R)->f;
    object_t* o = object_resolve(f);
    if (state((uintptr_t)f) != 1 || state((uintptr_t)o) != 1 || ((struct node*)o)->id != O_ID) {
        fprintf(stderr, "test_gc_old_compact: %s\n", when);
        fail("an old referrer lost its referent", state((uintptr_t)o));
    }
    if (gen(g_R) != 1) fail("R left the old generation", gen(g_R));
}

static void __attribute__((noinline)) capture_copy(void) {
    uintptr_t word = (uintptr_t)((object_t*)g_O)->vtable;
    if (!vtable_is_forward((vtable_t*)word)) fail("the sparse old page was not compacted at the major", 0);
    g_C = word;
    if (page_of(g_C) == page_of(g_O)) fail("the copy landed on the page it left", 0);
    if (gen(g_C) != 1) fail("the copy of an old object is not old", gen(g_C));
    if (!((uintptr_t)((object_t*)g_C)->vtable & VTABLE_OLD_BIT)) fail("the copy lost its OLD stamp", 0);
    if (carded(g_C) != 1) fail("the copy of a carded object lost its card", carded(g_C));
}

static void _entrypoint(object_t* self, fun_t cont) {
    (void)self; _exit_cont = cont;
    gc_debug_manual_mode = true;
    while (gc_debug_stage() == 0) usleep(1000);   // wait for the collector
    while (gc_debug_stage() != ST_IDLE) gc_debug_step();

    // (1) O among its fillers; O, R old.
    create();
    scrub();
    for (int cycles = 0; gen(g_O) != 1 || gen(g_R) != 1; ++cycles) {
        if (cycles > 25) fail("O or R never promoted", gen(g_O));
        churn();
        scrub();
        run_one_cycle();
    }
    if (carded(g_O) != 1) fail("O, pointing at a mutable object, is not carded", carded(g_O));

    // (2) The fillers become old garbage.
    drop_fillers();
    scrub();
    run_one_cycle();
    if (state(g_M) != 1) fail("M was reclaimed", state(g_M));

    // (3) A major: O's page goes sparse and compacts into a page born old.
    gc_debug_request_major();
    scrub();
    run_one_cycle();
    capture_copy();
    check_r("after the compacting major");

    // (4) Minors: R reaches the copy through the forwarder; M lives through
    // the copy's card.
    for (int cycles = 0; cycles < 2; ++cycles) {
        churn();
        scrub();
        run_one_cycle();
        check_r("after a minor");
        if (state(g_M) != 1) fail("the copy's card no longer keeps M", state(g_M));
    }

    // (5) A major rewrites R past the forwarder; a later one frees it.
    gc_debug_request_major();
    scrub();
    run_one_cycle();
    check_r("after the next major");
    if ((uintptr_t)((struct parent*)g_R)->f != g_C) fail("a major did not rewrite an old field past its forwarder", 0);
    gc_debug_request_major();
    scrub();
    run_one_cycle();
    if (state(g_O) == 1) fail("the forwarder outlived every referrer", state(g_O));
    check_r("at the end");

    printf("test_gc_old_compact: OK\n");
    fflush(stdout);
    ((void(*)(object_t*,object_t*))_exit_cont.f)(_exit_cont.o, integer_from_int32(0));
}

int main(void) {
    // As test_gc_gen: a small heap and a low promotion floor, so pages
    // promote after a few batches of churn. Set before any allocation.
    setenv("YAFL_HEAP_SIZE", "64m", 0);
    setenv("YAFL_GC_PROMOTE_FLOOR", "64", 0);
    _prev = add_roots_declaration_func(_decl);
    thread_start(_entrypoint);
    return 0;
}
