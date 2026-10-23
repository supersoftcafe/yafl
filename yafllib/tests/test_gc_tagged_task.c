// Deterministic, single-threaded test: a task referenced ONLY by a
// TASK-tagged word must survive a collection.
//
// A pending result is the task-carrying word a call returned: a value, or the
// callee's task with PTR_TAG_TASK set. The compilers keep it as returned — in
// a C local, or in an async frame's field across a park — until the use that
// awaits it, so the collector must read a task-tagged word as a reference to
// its task (tasks are mutable, so they never move: the tag needs no care when
// a reference is updated).
//
// Two cases, each a full stepped cycle with T allocated before it opens (so
// it is not allocated black) and T's untagged address kept only where the
// collector does not look:
//   1. HEAP: the tagged word is the only reference, in a pointer field of a
//      rooted mutable object — precise marking.
//   2. STACK: the tagged word is the only reference, in a stack slot of a
//      live frame — the conservative scan.

#include "../yafl.h"
#include <stdio.h>
#include <string.h>
#include <unistd.h>

extern bool gc_debug_manual_mode;
extern int  gc_debug_stage(void);
extern void gc_debug_step(void);
extern int  gc_debug_object_state(object_t* o);   // 0 not-heap, 1 live, 2 reclaimed

// Must match enum gc_stage in object.c.
enum { ST_NOT_STARTED = 0, ST_IDLE = 1, ST_START = 2,
       ST_SCAN_ROOTS = 3, ST_MARK_SWEEP = 4, ST_PRUNE = 5 };

// The holder: a declared root naming a mutable object (a task: its
// callback.o is a traced pointer field).
static object_t*                _holder;
static roots_declaration_func_t _prev;
static void _decl(void(*declare)(object_t**)) { _prev(declare); declare(&_holder); }

// T's address, disguised where the collector does not look.
static volatile uintptr_t g_T_hidden;
#define HIDE(p) ((uintptr_t)(p) ^ (uintptr_t)0x5a5a5a5a5a5a5a50ull)

static fun_t _exit_cont;

static __attribute__((noinline)) void scrub(void) {
    volatile char junk[16384];
    memset((char*)junk, 0, sizeof junk);
}

static void step_to(int target) {
    for (int g = 0; gc_debug_stage() != target; ++g) {
        if (g > 100000) { fprintf(stderr, "step_to: stuck at stage %d\n", gc_debug_stage()); abort(); }
        gc_debug_step();
    }
}

static void full_cycle(void) {
    step_to(ST_SCAN_ROOTS);
    step_to(ST_MARK_SWEEP);
    step_to(ST_PRUNE);
    step_to(ST_IDLE);
}

static int verdict(const char* name) {
    object_t* t = (object_t*)HIDE(g_T_hidden);
    int st = gc_debug_object_state(t);
    printf("test_gc_tagged_task: %s: after the cycle T_state=%d (1=live, 2=reclaimed, 0=page released)\n",
           name, st);
    if (st != 1)
        printf("test_gc_tagged_task: *** BUG: a task referenced by a tagged word was reclaimed ***\n");
    fflush(stdout);
    return st == 1;
}

// Case 1: the tagged word lives in the holder's field.
static __attribute__((noinline)) void heap_setup(void) {
    _holder = task_create(NULL);
    object_t* t = task_create(NULL);
    g_T_hidden = HIDE(t);
    ((task_t*)_holder)->callback.o = (object_t*)((uintptr_t)t | PTR_TAG_TASK);
}

static int heap_case(void) {
    step_to(ST_IDLE);
    heap_setup();
    scrub();
    full_cycle();
    return verdict("heap field");
}

// Case 2: the tagged word lives in this frame's stack slot.
static __attribute__((noinline)) void stack_setup(volatile uintptr_t* slot) {
    object_t* t = task_create(NULL);
    g_T_hidden = HIDE(t);
    *slot = (uintptr_t)t | PTR_TAG_TASK;
}

static __attribute__((noinline)) int stack_case(void) {
    volatile uintptr_t tagged = 0;
    step_to(ST_IDLE);
    stack_setup(&tagged);
    scrub();
    full_cycle();
    int ok = verdict("stack slot");
    (void)tagged;   // live across the cycle
    return ok;
}

static void _entrypoint(object_t* self, fun_t cont) {
    (void)self;
    _exit_cont = cont;
    gc_debug_manual_mode = true;
    while (gc_debug_stage() == 0) usleep(1000);   // wait for the collector to exist

    int ok = heap_case();
    ok &= stack_case();

    ((void(*)(object_t*,object_t*))_exit_cont.f)(_exit_cont.o, integer_from_int32(ok ? 0 : 7));
}

int main(void) {
    _prev = add_roots_declaration_func(_decl);
    thread_start(_entrypoint);
    return 0;
}
