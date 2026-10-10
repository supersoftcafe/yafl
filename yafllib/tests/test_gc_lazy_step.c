// Deterministic, single-threaded test: a waiter enqueued on a GLOBAL lazy
// stub must survive the cycle it was enqueued in.
//
// A global stub's `flag` field is a declared root. lazy_thunk_enqueue CASes
// the waiter into it, and on the path where this thread wins the init race
// (status 1) the caller drops its `waiter` local at once: the flag is then
// the waiter's only reference. That is a root store like any other, so it
// needs the root-publish contract (see gc_root_publish in yafl.h):
//
//   1. W is allocated before the cycle opens, so it is not allocated black.
//   2. The cycle opens: the root snapshot reads the flag while it is NULL.
//   3. W is enqueued (status 1), then dropped. Its address is parked in a
//      plain global the collector never scans.
//   4. The take, marking and prune run. Only a publish of the flag marks W.
//
// Unpublished, W is reclaimed while the flag still points at it, and the
// drain later walks a freed task. Same shape as test_gc_publish_step.

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

// The global stub's flag field, declared as a root as the compilers declare it.
static object_t*                _flag[1];
static roots_declaration_func_t _prev;
static void _decl(void(*declare)(object_t**)) { _prev(declare); declare(&_flag[0]); }

// W's address, where the collector does not look.
static volatile uintptr_t g_W;
static int32_t            g_status;

static fun_t _exit_cont;

// Each step runs in its own frame and returns nothing, so W does not linger
// in the caller's frame; scrub() then overwrites what those frames left.
static __attribute__((noinline)) void allocate(void) {
    g_W = (uintptr_t)task_create(NULL);
}

static __attribute__((noinline)) void enqueue(void) {
    g_status = lazy_thunk_enqueue((object_t*)&_flag[0], (object_t*)g_W);
}

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

static void _entrypoint(object_t* self, fun_t cont) {
    (void)self;
    _exit_cont = cont;
    gc_debug_manual_mode = true;
    while (gc_debug_stage() == 0) usleep(1000);   // wait for the collector to exist
    step_to(ST_IDLE);

    // (1) Before the cycle opens.
    allocate();
    scrub();

    // (2) Open the cycle: the snapshot reads _flag[0] while it is NULL.
    step_to(ST_SCAN_ROOTS);

    // (3) Enqueue as the first waiter (this thread would now run the thunk),
    // then drop W.
    enqueue();
    scrub();
    if (g_status != 1) {
        fprintf(stderr, "test_gc_lazy_step: expected status 1, got %d\n", g_status);
        abort();
    }

    // (4) The take, marking and prune.
    step_to(ST_MARK_SWEEP);
    step_to(ST_PRUNE);
    step_to(ST_IDLE);

    int st = gc_debug_object_state((object_t*)g_W);
    printf("test_gc_lazy_step: after prune W_state=%d (1=live, 2=reclaimed); _flag[0]=%p\n",
           st, (void*)_flag[0]);
    if (st == 2)
        printf("test_gc_lazy_step: *** BUG: an enqueued lazy waiter was reclaimed ***\n");
    fflush(stdout);

    ((void(*)(object_t*,object_t*))_exit_cont.f)(_exit_cont.o, integer_from_int32(st == 1 ? 0 : 7));
}

int main(void) {
    _prev = add_roots_declaration_func(_decl);
    thread_start(_entrypoint);
    return 0;
}
