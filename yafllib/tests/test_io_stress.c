// Stress test that reproduces the intermittent GC crash/hang seen in
// the higher-level rt_bin scenario.  The pattern that tips the GC over:
//
//   1. The IO threadpool completes a job on an unrelated thread.
//   2. The worker's finisher runs, which calls task_complete, which calls
//      thread_dispatch_fast, which calls thread_work_prepare → object_create.
//   3. object_create needs a new page → gc_page_alloc → gc_fsa →
//      gc_fsa_mark_sweep — i.e. a full GC mark-sweep is run *inside* a
//      worker's finisher, while io_job_t / worker_node_t slots are being
//      churned at high rate.
//
// Symptoms observed in the wild:
//   * scan_elements stuck in the follow-forwarding inner loop on a vtable
//     whose tag bits are MANAGED (not FORWARD), apparently looping.
//   * scan_elements crashing in gc_object_is_on_heap_fast on a pointer
//     value that looks like ASCII string data — implying an io_job_t slot
//     whose memory was reused for a string object's byte buffer while the
//     mark phase was still treating it as an io_job.
//
// The reproducer here runs many small async IO operations in a tight
// chain and tracks down whether the suite gets through them all without
// crash or stall.  Run under a watchdog: any failure to call the exit
// continuation within REPRO_TIMEOUT_SECONDS is treated as a hang.

#include "../yafl.h"
#include <errno.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

EXTERN object_t* io_create     (object_t* self, object_t* path);
EXTERN object_t* io_open_read  (object_t* self, object_t* path);
EXTERN object_t* io_close      (object_t* self);
EXTERN object_t* io_write      (object_t* self, object_t* data);


// ---- Tunables ----------------------------------------------------------
//
// REPRO_ITERATIONS is the number of io_create-then-close cycles.  The
// default is sized to drive the GC into multiple mark-sweep passes while
// io_job_t / worker_node_t allocations are still in flight.  Increase if
// it doesn't repro on a given machine; reduce for a quick smoke test.

// 1000 iterations reproduces the bug ~100% of the time on a 4-thread
// IO pool with thread_count=2 workers, while taking only a few hundred
// milliseconds when the bug is fixed.
#ifndef REPRO_ITERATIONS
#define REPRO_ITERATIONS 1000
#endif

#ifndef REPRO_TIMEOUT_SECONDS
#define REPRO_TIMEOUT_SECONDS 10
#endif


// ---- CPS chaining helper ----------------------------------------------
//
// A real YAFL state machine roots the in-flight task via its state
// object's `my_task` field (compiler-generated, GC-traced).  This C test
// has no such state machine, so a static root `_in_flight_task` plays the
// same part — without it, the task's only path through the GC graph
// would be its callback closure, which isn't a root.

static void (*_next_step)(object_t*);
static object_t* _in_flight_task;   // GC root: current task awaited by then()

static object_t* _trampoline(object_t* self_unused, object_t* task) {
    (void)self_unused;
    object_t* value = ((task_obj_t*)task)->result;
    void (*next)(object_t*) = _next_step;
    _next_step = NULL;
    _in_flight_task = NULL;   // released for GC
    next(value);
    return NULL;
}

static void then(object_t* result, void (*next)(object_t*)) {
    if (!((uintptr_t)result & PTR_TAG_TASK)) {
        next(result);
        return;
    }
    _next_step = next;
    task_obj_t* t = (task_obj_t*)TASK_UNTAG(result);
    _in_flight_task = (object_t*)t;
    task_on_complete(&t->parent, (fun_t){.f=(void*)_trampoline, .o=NULL});
}


// ---- Watchdog ----------------------------------------------------------
//
// Async chain that fails to converge would normally just sit there.  A
// pthread watchdog fires SIGABRT after REPRO_TIMEOUT_SECONDS to flip the
// failure into a visible coredump rather than waiting indefinitely.

static _Atomic(bool) _finished = false;

static void* _watchdog_main(void* arg) {
    (void)arg;
    struct timespec deadline;
    clock_gettime(CLOCK_REALTIME, &deadline);
    deadline.tv_sec += REPRO_TIMEOUT_SECONDS;
    pthread_mutex_t mu = PTHREAD_MUTEX_INITIALIZER;
    pthread_cond_t  cv = PTHREAD_COND_INITIALIZER;
    pthread_mutex_lock(&mu);
    while (!atomic_load(&_finished)) {
        int rc = pthread_cond_timedwait(&cv, &mu, &deadline);
        if (rc == ETIMEDOUT) {
            fprintf(stderr,
                "test_io_stress: WATCHDOG TIMEOUT — chain stalled after %d seconds.\n"
                "Likely a GC mark-sweep deadlock or lost-wakeup in the unified queue.\n",
                REPRO_TIMEOUT_SECONDS);
            // SIGABRT so the coredump captures the live thread state.
            abort();
        }
    }
    pthread_mutex_unlock(&mu);
    return NULL;
}


// ---- Driver ------------------------------------------------------------

static fun_t       _exit_cont;
static int32_t     _iter_remaining;
static object_t*   _path;            // GC root: tmp file path

static void _do_iteration(void);


// step3 → close finished, advance to next iteration (or exit).
static void _stress_close_done(object_t* close_result) {
    (void)close_result;
    if (--_iter_remaining > 0) {
        _do_iteration();
        return;
    }
    atomic_store(&_finished, true);
    object_t* status = integer_create_from_int32(0);
    ((void(*)(object_t*,object_t*))_exit_cont.f)(_exit_cont.o, status);
}


// step2 → io_create returned (success or error).  Always close on the
// success path so we exercise the close finisher in every iteration.
static void _stress_create_done(object_t* result) {
    if (result != NULL && PTR_IS_OBJECT(result)) {
        then(io_close(result), _stress_close_done);
    } else {
        // Error from io_create — still chain to next iteration.
        _stress_close_done(NULL);
    }
}


// One iteration of the stress loop.  Allocates a path string, kicks off
// io_create.  Each iteration churns an io_t (~8 KiB), an io_job_t, a
// worker_node_t, plus the small return-value strings/integers — enough
// allocator traffic to trigger several gc_fsa passes per thousand iters.
static void _do_iteration(void) {
    char buf[64];
    int n = snprintf(buf, sizeof(buf), "/tmp/yafl_io_stress_%d.tmp", _iter_remaining);
    _path = string_from_bytes((uint8_t*)buf, n);
    then(io_create(NULL, _path), _stress_create_done);
}


static roots_declaration_func_t _prev_roots;
static void _stress_declare_roots(void(*declare)(object_t**)) {
    _prev_roots(declare);
    declare(&_path);
    declare(&_in_flight_task);
}

static void _entrypoint(object_t* self, fun_t continuation) {
    (void)self;
    _exit_cont = continuation;
    _iter_remaining = REPRO_ITERATIONS;

    pthread_t watchdog;
    pthread_create(&watchdog, NULL, _watchdog_main, NULL);
    pthread_detach(watchdog);

    printf("test_io_stress: %d iterations\n", REPRO_ITERATIONS);
    fflush(stdout);
    _do_iteration();
}


int main(void) {
    _prev_roots = add_roots_declaration_func(_stress_declare_roots);
    thread_start(_entrypoint);
    return 0;
}
