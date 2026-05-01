// IO-free reproducer for the GC fragility seen in test_io_stress.
//
// Simulates the cross-thread task dispatch pattern: each iteration creates a
// task_obj_t and a completion_task, posts the completion_task to a (possibly
// different) worker via thread_work_post_parallel.  That worker runs the
// finisher (which drives allocation-heavy GC stress), then completes the io
// task, triggering the trampoline.  This exercises the same GC paths as the
// real IO subsystem without requiring actual file operations.

#include "../yafl.h"
#include <pthread.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>


// ---- Tunables ----------------------------------------------------------

#ifndef REPRO_ITERATIONS
#define REPRO_ITERATIONS 20000
#endif

#ifndef REPRO_TIMEOUT_SECONDS
#define REPRO_TIMEOUT_SECONDS 30
#endif

// Allocations the finisher does per iteration.
#ifndef ALLOCS_PER_ITER
#define ALLOCS_PER_ITER 32
#endif


// ---- Task chaining helper -----------------------------------------------

static void          (*_next_step)(object_t*);
static object_t*       _in_flight_task;        // GC root: task whose callback we're awaiting
static task_t*         _in_flight_completion;  // GC root: completion task pending on another worker

static object_t* _trampoline(object_t* self_unused, object_t* task) {
    (void)self_unused;
    object_t* value = ((task_obj_t*)task)->result;
    void (*next)(object_t*) = _next_step;
    _next_step            = NULL;
    _in_flight_task       = NULL;
    _in_flight_completion = NULL;
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

static _Atomic(bool)    _finished = false;
static _Atomic(int32_t) _iters_completed;

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
                "test_gc_stress: WATCHDOG TIMEOUT — chain stalled at iteration %d/%d "
                "after %d seconds.\n",
                atomic_load(&_iters_completed), REPRO_ITERATIONS,
                REPRO_TIMEOUT_SECONDS);
            abort();
        }
    }
    pthread_mutex_unlock(&mu);
    return NULL;
}


// ---- Driver ------------------------------------------------------------

static fun_t   _exit_cont;
static int32_t _iter_remaining;

static void _do_iteration(void);


// Finisher: runs on a worker (possibly different from creator) after
// thread_work_post_parallel.  Does ALLOCS_PER_ITER allocations to stress
// the GC, then resolves the io task, triggering the trampoline.
static void _finisher(task_obj_t* task) {
    object_t* result = NULL;
    for (int i = 0; i < ALLOCS_PER_ITER; ++i) {
        char buf[32];
        int n = snprintf(buf, sizeof(buf), "stress-%d-%d", _iter_remaining, i);
        result = string_from_bytes((uint8_t*)buf, n);
    }

    GC_WRITE_BARRIER(task->result, 1);
    task->result = result;
    task_complete(&task->parent);
}

static object_t* _run_finisher(void* task_ptr, object_t* unused) {
    (void)unused;
    _finisher((task_obj_t*)task_ptr);
    return NULL;
}


static void _step_done(object_t* result) {
    (void)result;
    atomic_fetch_add(&_iters_completed, 1);
    if (--_iter_remaining > 0) {
        _do_iteration();
        return;
    }
    atomic_store(&_finished, true);
    object_t* status = integer_create_from_int32(0);
    ((void(*)(object_t*,object_t*))_exit_cont.f)(_exit_cont.o, status);
}


static void _do_iteration(void) {
    task_obj_t* task = (task_obj_t*)task_obj_create(NULL);

    // Register the trampoline — task is now CALLBACK.
    object_t* tagged = (object_t*)((uintptr_t)task | PTR_TAG_TASK);
    then(tagged, _step_done);

    // Pre-allocate a completion task that will run the finisher on whichever
    // worker dequeues it.  Using thread_work_post_parallel simulates the
    // cross-thread completion pattern of the real IO subsystem.
    task_t* ct = (task_t*)task_create(NULL);
    task_on_complete(ct, (fun_t){.f=(void*)_run_finisher, .o=(object_t*)task});
    _in_flight_completion = ct;

    thread_work_post_parallel(ct);
}


static roots_declaration_func_t _prev_roots;
static void _stress_declare_roots(void(*declare)(object_t**)) {
    _prev_roots(declare);
    declare(&_in_flight_task);
    declare((object_t**)&_in_flight_completion);
}


static void _entrypoint(object_t* self, fun_t continuation) {
    (void)self;
    _exit_cont = continuation;
    _iter_remaining = REPRO_ITERATIONS;

    pthread_t watchdog;
    pthread_create(&watchdog, NULL, _watchdog_main, NULL);
    pthread_detach(watchdog);

    printf("test_gc_stress: %d iterations\n", REPRO_ITERATIONS);
    fflush(stdout);
    _do_iteration();
}


int main(void) {
    _prev_roots = add_roots_declaration_func(_stress_declare_roots);
    thread_start(_entrypoint);
    return 0;
}
