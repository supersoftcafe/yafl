// Deterministic, single-stepped test: an OLD forwarding stub's body stays
// valid while an old referrer still reaches it.
//
// A major compacts a sparse old page into a page born old, leaving a stub
// whose old referrers keep its address until the next major rewrites them. A
// reader that follows such a referrer reads the STUB's body: the object as it
// was when it moved. If that body points at a young object, nothing young is
// allowed to vanish under it — but a minor never scans an old page, so the
// stub's field is never rewritten when the young object itself moves, and the
// young object's own forwarder dies a cycle later. The stub keeps its card, so
// every minor traces its body (through the copy's vtable) and rewrites it.
//
//   1. O (small, among rooted fillers) points at R (young: its page holds P,
//      pinned throughout, so the page never promotes, and a rooted spacer);
//      Y (half a page, rooted) points at O. Cycles until O and Y are old.
//   2. The fillers' roots go; a major compacts O's page: O moves into a page
//      born old, Y still names O's stub.
//   3. The spacer's root goes; minors compact R's page (R moves, P stays) and
//      then reclaim R's forwarder once nothing marks it.
//   4. Through Y, O's stub must still reach a live R, with its id.
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
extern void gc_debug_request_major(void);

enum { ST_IDLE = 1 };
enum { FILLERS = 300, R_ID = 0x7e5d };

struct node { object_t parent; object_t* f; intptr_t id; };
static vtable_t node_vt = {
    .object_size = sizeof(struct node), .array_el_size = 0,
    .object_pointer_locations = maskof(struct node, .f),
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 0, .name = "os_node", .implements_array = VTABLE_IMPLEMENTS(0),
};
struct small { object_t parent; intptr_t x; };
static vtable_t small_vt = {
    .object_size = sizeof(struct small), .array_el_size = 0,
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 0, .name = "os_small", .implements_array = VTABLE_IMPLEMENTS(0),
};
// R's spacer: enough that R's page is not sparse (over a third full) until
// it dies, and then it is.
struct spacer { object_t parent; char pad[6144 - sizeof(object_t)]; };
static vtable_t spacer_vt = {
    .object_size = sizeof(struct spacer), .array_el_size = 0,
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 0, .name = "os_spacer", .implements_array = VTABLE_IMPLEMENTS(0),
};
// Half a page: Y's page is never sparse.
struct parent { object_t parent; object_t* f; char pad[8192 - sizeof(object_t) - sizeof(object_t*)]; };
static vtable_t parent_vt = {
    .object_size = sizeof(struct parent), .array_el_size = 0,
    .object_pointer_locations = maskof(struct parent, .f),
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 0, .name = "os_parent", .implements_array = VTABLE_IMPLEMENTS(0),
};
// Churn, bigger than half a page so it never shares a page with the others.
struct fill { object_t parent; char pad[12 * 1024 - sizeof(object_t)]; };
static vtable_t churn_vt = {
    .object_size = sizeof(struct fill), .array_el_size = 0,
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 0, .name = "os_churn", .implements_array = VTABLE_IMPLEMENTS(0),
};

enum { ROOT_BRIDGE = FILLERS, ROOT_Y, ROOT_SPACER, ROOT_P, ROOTS };
static object_t*                _roots[ROOTS];
static roots_declaration_func_t _prev;
static void _decl(void(*declare)(object_t**)) {
    _prev(declare);
    for (int i = 0; i < ROOTS; ++i) declare(&_roots[i]);
}

// The addresses, where the collector does not look: a local holding one
// across a cycle would be a conservative root, and pin the page it names.
static volatile uintptr_t g_O, g_R, g_Y, g_P;
static fun_t _exit_cont;

static void fail(const char* what, int got) {
    fprintf(stderr, "test_gc_old_stub_card: FAIL %s (got %d)\n", what, got);
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
    // R's page: R, P (pinned for good), the spacer.
    object_t* volatile r = object_create(&node_vt);
    ((struct node*)r)->id = R_ID;
    g_R = (uintptr_t)r;
    object_t* volatile p = object_create(&small_vt);
    GC_ROOT_STORE(_roots[ROOT_P], 1, p);
    g_P = (uintptr_t)object_pin(p);
    object_t* volatile s = object_create(&spacer_vt);
    GC_ROOT_STORE(_roots[ROOT_SPACER], 1, s);
    // Too big for what is left of R's page, so O's page starts here; rooted,
    // and dropped with the fillers, so O's page stays full until then.
    object_t* volatile b = object_create(&churn_vt);
    GC_ROOT_STORE(_roots[ROOT_BRIDGE], 1, b);
    // O's page: O among the fillers.
    object_t* volatile o = object_create(&node_vt);
    ((struct node*)o)->f = r;          // construction: fresh, no barrier owed
    g_O = (uintptr_t)o;
    for (int i = 0; i < FILLERS; ++i) {
        object_t* volatile f = object_create(&small_vt);
        GC_ROOT_STORE(_roots[i], 1, f);
        f = NULL;
    }
    object_t* volatile y = object_create(&parent_vt);
    ((struct parent*)y)->f = o;
    GC_ROOT_STORE(_roots[ROOT_Y], 1, y);
    g_Y = (uintptr_t)y;
    r = p = s = b = o = y = NULL;
}

static void __attribute__((noinline)) drop(int from, int to) {
    for (int i = from; i < to; ++i) {
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

static int gen(uintptr_t o)   { return gc_debug_object_generation((object_t*)o); }

// Y -> O's stub -> its body's field: a live R, with its id, through any
// forwarders.
static void __attribute__((noinline)) check_through_stub(const char* when) {
    object_t* stub = ((struct parent*)g_Y)->f;
    object_t* f = ((struct node*)stub)->f;
    object_t* r = object_resolve(f);
    int st = gc_debug_object_state(f);
    if (st != 1 || gc_debug_object_state(r) != 1 || ((struct node*)r)->id != R_ID) {
        fprintf(stderr, "test_gc_old_stub_card: %s\n", when);
        fail("an old stub's body points at a reclaimed object", st);
    }
}

static void _entrypoint(object_t* self, fun_t cont) {
    (void)self; _exit_cont = cont;
    gc_debug_manual_mode = true;
    while (gc_debug_stage() == 0) usleep(1000);   // wait for the collector
    while (gc_debug_stage() != ST_IDLE) gc_debug_step();

    // (1) O and Y old; R young.
    create();
    scrub();
    if (page_of(g_O) == page_of(g_R)) fail("O shares R's page", 0);
    for (int cycles = 0; gen(g_O) != 1 || gen(g_Y) != 1; ++cycles) {
        if (cycles > 25) fail("O or Y never promoted", gen(g_O));
        churn();
        scrub();
        run_one_cycle();
    }
    if (gen(g_R) != 0) fail("R promoted under its page's pin", gen(g_R));
    if (page_of(g_R)->head.compacted) fail("R's page compacted before O moved: the test cannot reach its case", 0);

    // (2) O moves, at a major; Y still names the stub.
    drop(0, ROOT_BRIDGE + 1);
    gc_debug_request_major();
    scrub();
    run_one_cycle();
    if (!vtable_is_forward(((object_t*)g_O)->vtable)) fail("O's sparse old page was not compacted", 0);
    if ((uintptr_t)((struct parent*)g_Y)->f != g_O) fail("Y no longer names O's stub before the next major", 0);
    check_through_stub("after O moved");

    // (3) R moves, in a minor; its forwarder dies a cycle or two later.
    drop(ROOT_SPACER, ROOT_SPACER + 1);
    for (int cycles = 0; cycles < 4; ++cycles) {
        churn();
        scrub();
        run_one_cycle();
        check_through_stub("after a minor");
    }
    if (!page_of(g_R)->head.compacted) fail("R's page never compacted: the test did not reach its case", 0);

    object_unpin((object_t*)g_P);
    printf("test_gc_old_stub_card: OK\n");
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
