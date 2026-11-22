// Deterministic, single-stepped test: a page handed over after marking's last
// check must not stay on the hand-off stack into the next cycle (#134).
//
// The first mark of a white page pushes it onto a lock-free stack that the
// collector takes in full. A mutator's barrier that reads "marking open" just
// before the mark tail's final check, and pushes just after, leaves its page
// on the stack when the cycle retires. In the next cycle the page reads white
// again (its stamp belongs to the old cycle), so its first mark there pushes
// it a second time while it is still on the stack: the stack loops back on
// itself, and the take that walks it never ends.
//
//   1. H (mutable, a page of its own, unrooted) is never marked: its page is
//      white.
//   2. A cycle runs. At its final check (the probe, compiled into this target
//      alone: YAFL_GC_HANDOFF_PROBE) a mutator's barrier marks H. Its page is
//      handed over after the last take, and the cycle retires.
//   3. H is rooted. The next cycle's roots mark it first, which hands its page
//      over again. That cycle must finish, with H live.
//
// Run with YAFL_THREADS=1; uses gc_debug_manual_mode.

#include "../yafl.h"
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

extern bool gc_debug_manual_mode;
extern int  gc_debug_stage(void);
extern void gc_debug_step(void);
extern int  gc_debug_object_state(object_t* o);   // 0 not-heap, 1 live, 2 reclaimed
extern void gc_test_mutator_mark(object_t* o);
extern bool gc_test_object_seen(object_t* o);

enum { ST_IDLE = 1 };

// Mutable: never relocated, so the address stays stable. A whole page, so no
// other object's mark can hand its page over.
struct holder { object_t parent; char pad[MAX_OBJECT_SIZE - sizeof(object_t)]; };
static vtable_t holder_vt = {
    .object_size = sizeof(struct holder), .array_el_size = 0,
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 1, .name = "late_handoff_holder", .implements_array = VTABLE_IMPLEMENTS(0),
};

static object_t*                _slots[1];
static roots_declaration_func_t _prev;
static void _decl(void(*declare)(object_t**)) { _prev(declare); declare(&_slots[0]); }

static volatile uintptr_t g_H;   // where the collector does not look
static bool  g_armed;
static int   g_fired;
static fun_t _exit_cont;

static void fail(const char* what, int got) {
    fprintf(stderr, "test_gc_late_handoff: FAIL %s (got %d)\n", what, got);
    fflush(stderr);
    abort();
}

void gc_test_handoff_probe(void);
void gc_test_handoff_probe(void) {
    if (!g_armed) return;
    g_armed = false;
    if (gc_test_object_seen((object_t*)g_H))
        fail("setup: H was marked before the probe (a stale copy of its address reached the scan)", 0);
    gc_test_mutator_mark((object_t*)g_H);   // the barrier, just after the check
    g_fired = 1;
}

static void run_one_cycle(void) {
    int guard = 0;
    while (gc_debug_stage() == ST_IDLE) {
        if (++guard > 100000) fail("cycle did not start", gc_debug_stage());
        gc_debug_step();
    }
    while (gc_debug_stage() != ST_IDLE) {
        if (++guard > 1000000) fail("cycle did not finish", gc_debug_stage());
        gc_debug_step();
    }
}

// In a frame of its own, so no copy of the address lingers for the
// conservative stack scan; scrub() overwrites what the frame left.
static void __attribute__((noinline)) build(void) {
    g_H = (uintptr_t)object_create(&holder_vt);
}

static void __attribute__((noinline)) scrub(void) {
    volatile uintptr_t junk[2048];
    for (int i = 0; i < 2048; ++i) junk[i] = (uintptr_t)(i * 2 + 1);
    __asm__ volatile("" :: "r"(junk[0]), "r"(junk[2047]) : ARCH_CALLEE_SAVED_CLOBBERS);
}

static void __attribute__((noinline)) root_h(void) {
    gc_root_overwrite(&_slots[0], 1);
    _slots[0] = (object_t*)g_H;
    gc_root_publish(&_slots[0], 1);
}

static void _entrypoint(object_t* self, fun_t cont) {
    (void)self; _exit_cont = cont;
    gc_debug_manual_mode = true;
    while (gc_debug_stage() == 0) usleep(1000);   // wait for the collector
    while (gc_debug_stage() != ST_IDLE) gc_debug_step();

    build();
    scrub();
    g_armed = true;
    run_one_cycle();
    if (!g_fired) fail("the probe did not run", 0);
    if (gc_debug_object_state((object_t*)g_H) != 1) fail("the late mark did not keep H", 0);

    root_h();
    scrub();
    run_one_cycle();   // hangs if the late hand-off survived into this cycle
    int h = gc_debug_object_state((object_t*)g_H);
    if (h != 1) fail("H, rooted, was reclaimed", h);
    printf("test_gc_late_handoff: OK\n");
    fflush(stdout);
    ((void(*)(object_t*,object_t*))_exit_cont.f)(_exit_cont.o, integer_from_int32(0));
}

int main(void) {
    setenv("YAFL_HEAP_SIZE", "64m", 0);
    _prev = add_roots_declaration_func(_decl);
    thread_start(_entrypoint);
    return 0;
}
