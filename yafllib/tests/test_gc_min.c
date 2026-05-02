// Minimal GC reproducer derived from test_gc_stress.c.
// Compile-time knobs control which factors are present.
//
// USE_TASKS=1        — include task machinery (default 1)
// USE_CROSS_THREAD=1 — use thread_work_post_parallel vs thread_dispatch (default 1)
// N_WORKERS=2        — number of worker threads (default 2)
// ALLOC_TYPE=0       — 0=strings, 1=integers, 2=mutable task_obj (default 0)
// ALLOC_STR_LEN=16   — length of strings allocated per iteration (default 16)
// ALLOCS_PER_ITER=32 — allocations per iteration (default 32)

#include "../yafl.h"
#include <pthread.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#ifndef REPRO_ITERATIONS
#define REPRO_ITERATIONS 50000
#endif

#ifndef REPRO_TIMEOUT_SECONDS
#define REPRO_TIMEOUT_SECONDS 300
#endif

#ifndef ALLOCS_PER_ITER
#define ALLOCS_PER_ITER 64
#endif

#ifndef USE_TASKS
#define USE_TASKS 1
#endif

#ifndef USE_CROSS_THREAD
#define USE_CROSS_THREAD 1
#endif

// ALLOC_TYPE: 0=string, 1=integer, 2=mutable(task_obj)
#ifndef ALLOC_TYPE
#define ALLOC_TYPE 0
#endif

#ifndef ALLOC_STR_LEN
#define ALLOC_STR_LEN 16
#endif

// ---- helpers ---------------------------------------------------------------

static object_t* _do_alloc(int i) {
#if ALLOC_TYPE == 1
    (void)i;
    return integer_create_from_int32(i);
#elif ALLOC_TYPE == 2
    (void)i;
    task_obj_t* t = (task_obj_t*)task_obj_create(NULL);
    return (object_t*)t;
#else
    static const char PAD[256] =
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789--"
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789--"
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789--"
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789--";
    int len = ALLOC_STR_LEN <= 255 ? ALLOC_STR_LEN : 255;
    return string_from_bytes((uint8_t*)PAD, len);
#endif
}


// ---- task chaining helper --------------------------------------------------

#if USE_TASKS
static void          (*_next_step)(object_t*);
static object_t*       _in_flight_task;        // GC root
static task_t*         _in_flight_completion;  // GC root

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
    task_on_complete((object_t*)t, (fun_t){.f=(void*)_trampoline, .o=NULL});
}
#endif // USE_TASKS


// ---- watchdog --------------------------------------------------------------

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
                "test_gc_min: WATCHDOG TIMEOUT — chain stalled at iteration %d/%d "
                "after %d seconds.\n",
                atomic_load(&_iters_completed), REPRO_ITERATIONS,
                REPRO_TIMEOUT_SECONDS);
            abort();
        }
    }
    pthread_mutex_unlock(&mu);
    return NULL;
}


// ---- driver ----------------------------------------------------------------

static fun_t   _exit_cont;
static int32_t _iter_remaining;

static void _do_iteration(void);


#if USE_TASKS
// Finisher: runs on a worker; allocates to stress GC then resolves the task.
static void _finisher(task_obj_t* task) {
    object_t* result = NULL;
    for (int i = 0; i < ALLOCS_PER_ITER; ++i) {
        result = _do_alloc(i);
    }
    GC_WRITE_BARRIER(task->result, 1);
    task->result = result;
    task_complete((object_t*)task);
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

    object_t* tagged = (object_t*)((uintptr_t)task | PTR_TAG_TASK);
    then(tagged, _step_done);   // task is now CALLBACK

    task_t* ct = (task_t*)task_create(NULL);
    task_on_complete((object_t*)ct, (fun_t){.f=(void*)_run_finisher, .o=(object_t*)task});
    _in_flight_completion = ct;

#if USE_CROSS_THREAD
    thread_work_post_parallel((object_t*)ct);
#else
    thread_work_post((object_t*)ct);
#endif
}

#else // !USE_TASKS

static void _finisher_notask(object_t* unused) {
    (void)unused;
    for (int i = 0; i < ALLOCS_PER_ITER; ++i) {
        _do_alloc(i);
    }
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
    fun_t action = (fun_t){.f=(void*)_finisher_notask, .o=NULL};
#if USE_CROSS_THREAD
    // Create a dispatch task and post it to a (possibly different) worker.
    task_t* ct = (task_t*)task_create(NULL);
    task_on_complete((object_t*)ct, action);
    thread_work_post_parallel((object_t*)ct);
#else
    thread_dispatch(action);
#endif
}

#endif // USE_TASKS


#if USE_TASKS
static roots_declaration_func_t _prev_roots;
static void _stress_declare_roots(void(*declare)(object_t**)) {
    _prev_roots(declare);
    declare(&_in_flight_task);
    declare((object_t**)&_in_flight_completion);
}
#endif


static void _entrypoint(object_t* self, fun_t continuation) {
    (void)self;
    _exit_cont = continuation;
    _iter_remaining = REPRO_ITERATIONS;

    pthread_t watchdog;
    pthread_create(&watchdog, NULL, _watchdog_main, NULL);
    pthread_detach(watchdog);

    printf("test_gc_min: iters=%d allocs_per=%d tasks=%d cross=%d alloc_type=%d str_len=%d\n",
           REPRO_ITERATIONS, ALLOCS_PER_ITER,
           USE_TASKS, USE_CROSS_THREAD, ALLOC_TYPE, ALLOC_STR_LEN);
    fflush(stdout);
    _do_iteration();
}


int main(void) {
#if USE_TASKS
    _prev_roots = add_roots_declaration_func(_stress_declare_roots);
#endif
    thread_start(_entrypoint);
    return 0;
}
