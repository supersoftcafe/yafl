/*
 * Forwarding-chain path-compression test (single-stepped, manual mode).
 *
 * Compaction leaves a forwarding stub behind; the copy can itself be
 * compacted later, forming a chain A -> B -> C. Heap FIELDS are snapped to
 * the tail as the trace rewrites them, but a stub kept alive by an
 * unrewritable reference — a conservative stack slot — has only its own
 * forward WORD, and without compression the chain re-marks every hop each
 * cycle and can grow a hop per compaction of its current tail, forever.
 * The scanner now path-compresses: scanning A rewrites its word to the
 * tail, and the bypassed middle stub dies.
 *
 *   1. K rooted on a page filled with dropped filler -> page sparse -> the
 *      prune compacts it: stub A -> B. (A must NOT be on the stack for this
 *      cycle: pinned pages are never compacted.)
 *   2. Pin A on the stack from here on. Fill + drop B's page -> next prune
 *      compacts it: chain A -> B -> C; the root field snaps to the tail by
 *      itself.
 *   3. One more cycle: scanning pinned A must compress its word to C.
 *   4. And the cycle after: nothing marks bypassed B any more — its page
 *      (stubs only) must be reclaimed.
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
extern int  gc_debug_object_state(object_t* o);   // 0 not-heap, 1 live, 2 reclaimed

enum { ST_IDLE = 1 };

struct leaf { object_t parent; char pad[32 - sizeof(object_t)]; };
static vtable_t leaf_vt = {
    .object_size = sizeof(struct leaf), .array_el_size = 0,
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 0, .name = "chain_leaf", .implements_array = VTABLE_IMPLEMENTS(0),
};

static object_t*                _slots[1];
static roots_declaration_func_t _prev;
static void _decl(void(*declare)(object_t**)) { _prev(declare); declare(&_slots[0]); }

/* Plain globals are NOT GC roots and not conservatively scanned — safe
 * parking spots for raw addresses the collector must not see. */
static volatile uintptr_t g_A, g_B, g_C;
static fun_t _exit_cont;

static void fail(const char* what, long got) {
    fprintf(stderr, "test_gc_fwd_chain: FAIL %s (got 0x%lx)\n", what, got);
    fflush(stderr);
    abort();
}

static void run_one_cycle(void) {
    int guard = 0;
    do {
        gc_debug_step();
        if (++guard > 100000) fail("cycle did not start", gc_debug_stage());
    } while (gc_debug_stage() == ST_IDLE);
    while (gc_debug_stage() != ST_IDLE) {
        gc_debug_step();
        if (++guard > 1000000) fail("cycle did not finish", gc_debug_stage());
    }
}

/* Allocate + root K, then bury its page in dropped filler so the page is
 * sparse at the next prune. Own frame: K's address must not linger on the
 * entrypoint's stack, or the conservative scan pins the page and the
 * compactor skips it. */
static void __attribute__((noinline)) create_and_bury(void) {
    object_t* k = object_create(&leaf_vt);
    GC_WRITE_BARRIER(_slots[0], 1);
    _slots[0] = k;
    g_A = (uintptr_t)k;
    for (int i = 0; i < 460; ++i) {
        volatile object_t* f = object_create(&leaf_vt);
        (void)f;
    }
}

/* Dropped filler to share (and then vacate) the COPY's bump page. */
static void __attribute__((noinline)) bury_copy_page(void) {
    for (int i = 0; i < 460; ++i) {
        volatile object_t* f = object_create(&leaf_vt);
        (void)f;
    }
}

static void __attribute__((noinline)) scrub(void) {
    volatile uintptr_t junk[512];
    for (int i = 0; i < 512; ++i) junk[i] = (uintptr_t)(i * 2 + 1);
    __asm__ volatile("" :: "r"(junk[0]), "r"(junk[511]) : "memory",
        "rbx", "r12", "r13", "r14", "r15");
}

/* Each inspection runs in its OWN frame: at -O0 the compiler parks raw
 * addresses in frame slots, and anything left in the ENTRYPOINT's frame
 * would be conservatively re-pinned every cycle (scrub only clobbers the
 * stack BELOW the caller). */
static void __attribute__((noinline)) capture_B(void) {
    if (!vtable_is_forward(((object_t*)g_A)->vtable))
        fail("A was not compacted into a stub", (long)(uintptr_t)((object_t*)g_A)->vtable);
    g_B = (uintptr_t)((object_t*)g_A)->vtable;
    printf("test_gc_fwd_chain: A=%#lx -> B=%#lx\n", (long)g_A, (long)g_B);
}

static void __attribute__((noinline)) capture_C(void) {
    if (!vtable_is_forward(((object_t*)g_B)->vtable))
        fail("B was not compacted into a stub", (long)(uintptr_t)((object_t*)g_B)->vtable);
    g_C = (uintptr_t)((object_t*)g_B)->vtable;
    if (g_C == g_B || g_C == g_A) fail("C address unexpected", (long)g_C);
    printf("test_gc_fwd_chain: chain A=%#lx -> B=%#lx -> C=%#lx\n",
           (long)g_A, (long)g_B, (long)g_C);
}

static void __attribute__((noinline)) check_compressed(void) {
    uintptr_t a_word = (uintptr_t)((object_t*)g_A)->vtable;
    if (a_word != g_C) fail("A's forward word was not compressed to C", (long)a_word);
    printf("test_gc_fwd_chain: A's word compressed to C\n");
}

static void __attribute__((noinline)) check_final(void) {
    int b_state = gc_debug_object_state((object_t*)g_B);
    if (b_state == 1) fail("bypassed middle stub B still live", b_state);
    int c_state = gc_debug_object_state((object_t*)g_C);
    if (c_state != 1) fail("tail C not live", c_state);
    if ((uintptr_t)_slots[0] != g_C) fail("root not snapped to tail", (long)(uintptr_t)_slots[0]);
    printf("test_gc_fwd_chain: B reclaimed (state=%d), C live — OK\n", b_state);
}

static void _entrypoint(object_t* self, fun_t cont) {
    (void)self; _exit_cont = cont;
    gc_debug_manual_mode = true;
    /* gc_start() fires when the LAST thread registers — a countdown this
       entrypoint can outrun. Stepping through NOT_STARTED is a no-op, so a
       fast spin exhausts the step guard before the collector exists: wait
       for it (yielding, so the registering threads get scheduled). */
    while (gc_debug_stage() == 0) usleep(1000);

    /* (1) A's page sparse; A unpinned for this one cycle -> compacts. */
    create_and_bury();
    scrub();
    run_one_cycle();
    capture_B();

    /* (2) Pin A on the stack from here on; make B's page sparse. */
    volatile uintptr_t a_pin = g_A;
    bury_copy_page();
    scrub();
    run_one_cycle();   /* root snaps to B; B's page compacts at this prune */
    capture_C();

    /* (3) Scanning pinned A must path-compress its word to the tail C.
     * Pin C too from here on: C sits alone on a sparse page, and without the
     * pin the compactor keeps relocating it every cycle — recycling B's just
     * freed page for the new copy, which lands a fresh object at B's old
     * address and confuses the address-based assertions below. */
    volatile uintptr_t c_pin = g_C;
    scrub();
    run_one_cycle();
    check_compressed();

    /* (4) Nothing marks bypassed B now (it was last marked during the
     * compression cycle itself — the walk marks every hop): its stub-only
     * page must be reclaimed by this cycle's prune. */
    scrub();
    run_one_cycle();
    check_final();
    (void)c_pin;

    (void)a_pin;
    fflush(stdout);
    ((void(*)(object_t*,object_t*))_exit_cont.f)(_exit_cont.o, integer_from_int32(0));
}

int main(void) {
    _prev = add_roots_declaration_func(_decl);
    thread_start(_entrypoint);
    return 0;
}
