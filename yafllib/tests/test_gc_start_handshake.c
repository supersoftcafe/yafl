// Deterministic, stepped test: the cycle opens only once every thread has
// acknowledged it at a safe point (GC_STAGE_STARTING, object.c).
//
// A store's barrier reads gc_write_barrier_requested and the store follows,
// with no safe point in between. A thread can read the flag DOWN, then the
// cycle opens and other threads are scanned, and only then does its store
// land, overwriting a value without shading it. If another thread loaded
// that value after its own scan, nothing marks it:
//
//   1. H (rooted) holds O. Neither is reachable any other way.
//   2. The peer thread X runs the barrier of a store into H's field while
//      idle: flag down, nothing shaded. It then waits, RUNNING, before the
//      store.
//   3. This thread opens the cycle and steps it as far as it will go while
//      X is held.
//   4. This thread loads O from H onto its stack.
//   5. X's store overwrites H's field with NULL, then X suspends.
//   6. The cycle finishes. O is on this thread's stack: it must be live.
//
// Without the handshake, this thread is scanned at step 3, before its load,
// and X's store owes no shade, so O is reclaimed under its holder. With it,
// the cycle cannot pass the opening while X is between its flag read and its
// store, so this thread's scan comes after its load.
// Run with YAFL_THREADS=1; uses gc_debug_manual_mode.

#include "../yafl.h"
#include "../gc_stage.h"
#include <pthread.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

extern bool gc_debug_manual_mode;
extern int  gc_debug_stage(void);
extern void gc_debug_step(void);
extern int  gc_debug_object_state(object_t* o);   // 0 not-heap, 1 live, 2 reclaimed

struct holder { object_t parent; object_t* child; };
static vtable_t holder_vt = {
    .object_size = sizeof(struct holder), .array_el_size = 0,
    .object_pointer_locations = maskof(struct holder, .child),
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 1, .name = "handshake_holder", .implements_array = VTABLE_IMPLEMENTS(0),
};
struct leaf { object_t parent; char pad[8192 - sizeof(object_t)]; };
static vtable_t leaf_vt = {
    .object_size = sizeof(struct leaf), .array_el_size = 0,
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 1, .name = "handshake_leaf", .implements_array = VTABLE_IMPLEMENTS(0),
};

static object_t* _root_H;   // H's only reference
static roots_declaration_func_t _prev;
static void _decl(void(*declare)(object_t**)) { _prev(declare); declare(&_root_H); }

static volatile uintptr_t g_H, g_O;   // where the collector does not look
static _Atomic int x_checked, x_go, x_stored;
static fun_t _exit_cont;

static void fail(const char* what, int got) {
    fprintf(stderr, "test_gc_start_handshake: FAIL %s (got %d)\n", what, got);
    fflush(stderr);
    abort();
}

static void step_to(int target) {
    for (int guard = 0; gc_debug_stage() != target; ++guard) {
        if (guard > 1000000) fail("stuck before stage", gc_debug_stage());
        gc_debug_step();
    }
}

// ── the peer, X ─────────────────────────────────────────────────────────────

static void _noop_roots(void* c, void(*d)(object_t**)) { (void)c; (void)d; }

// Steps 2 and 5: GC_STORE_MUTABLE_IN taken apart, as the race takes it apart.
static void __attribute__((noinline)) peer_work(void) {
    struct holder* h = (struct holder*)g_H;
    GC_WRITE_BARRIER_MUTABLE_IN(h, h->child, 1);   // (2) flag down
    atomic_store(&x_checked, 1);
    while (!atomic_load(&x_go)) {}                 // RUNNING: no safe point
    h->child = NULL;                               // (5)
    atomic_store(&x_stored, 1);
    gc_io_begin();                                 // suspended from here on
    for (;;) pause();
}

// The anchor's frame holds nothing else (see thread.c, _thread_main_loop).
static void* peer(void* arg) {
    (void)arg;
    object_t* stack_anchor = NULL;
    gc_declare_thread(_noop_roots, NULL, &stack_anchor);
    peer_work();
    return NULL;
}

// ── this thread ─────────────────────────────────────────────────────────────

// Each step in a frame of its own, so no copy of an address lingers for the
// conservative stack scan; scrub() overwrites what those frames left.
static void __attribute__((noinline)) allocate(void) {
    object_t* h = object_create(&holder_vt);
    GC_ROOT_STORE(_root_H, 1, h);
    object_t* o = object_create(&leaf_vt);
    memset(((struct leaf*)o)->pad, 0x5a, sizeof ((struct leaf*)o)->pad);
    GC_STORE_MUTABLE_IN(h, ((struct holder*)h)->child, 1, o);   // (1)
    g_H = (uintptr_t)h;
    g_O = (uintptr_t)o;
}

static void __attribute__((noinline)) scrub(void) {
    volatile uintptr_t junk[512];
    for (int i = 0; i < 512; ++i) junk[i] = (uintptr_t)(i * 2 + 1);
    __asm__ volatile("" :: "r"(junk[0]), "r"(junk[511]) : ARCH_CALLEE_SAVED_CLOBBERS);
}

// (3) Open the cycle, then step it as far as it goes while X is held.
static void __attribute__((noinline)) open_cycle(void) {
    for (int guard = 0; gc_debug_stage() == GC_STAGE_IDLE || gc_debug_stage() == GC_STAGE_START; ++guard) {
        if (guard > 1000000) fail("the cycle did not open", gc_debug_stage());
        gc_debug_step();
    }
    for (int i = 0; i < 64; ++i)
        gc_debug_step();
}

static void _entrypoint(object_t* self, fun_t cont) {
    (void)self; _exit_cont = cont;
    gc_debug_manual_mode = true;
    while (gc_debug_stage() == GC_STAGE_NOT_STARTED) usleep(1000);   // wait for the collector
    step_to(GC_STAGE_IDLE);

    allocate();
    scrub();
    pthread_t x;
    if (pthread_create(&x, NULL, peer, NULL) != 0) fail("pthread_create", 0);
    while (!atomic_load(&x_checked)) {}

    open_cycle();
    printf("test_gc_start_handshake: held at stage %s\n", gc_stage_name((enum gc_stage)gc_debug_stage()));
    object_t* volatile held = ((struct holder*)g_H)->child;   // (4)
    if ((uintptr_t)held != g_O) fail("H did not hold O", 0);

    atomic_store(&x_go, 1);
    while (!atomic_load(&x_stored)) {}
    step_to(GC_STAGE_IDLE);   // (6)

    int st = gc_debug_object_state(held);
    printf("test_gc_start_handshake: after the cycle O_state=%d (1=live, 2=reclaimed)\n", st);
    if (st != 1) fail("a store whose barrier read the flag down before the cycle opened lost a value a scanned thread held", st);
    printf("test_gc_start_handshake: OK\n");
    fflush(stdout);
    ((void(*)(object_t*,object_t*))_exit_cont.f)(_exit_cont.o, integer_from_int32(0));
}

int main(void) {
    setenv("YAFL_HEAP_SIZE", "64m", 0);
    _prev = add_roots_declaration_func(_decl);
    thread_start(_entrypoint);
    return 0;
}
