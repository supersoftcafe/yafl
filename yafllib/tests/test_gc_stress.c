// IO-free reproducer for the GC fragility seen in test_io_stress.
//
// The hypothesis from that test is that the IO library is just the
// carrier — the actual stress on the GC is the cross-thread post
// pattern combined with allocation-driven gc_fsa_mark_sweep.  This
// test substitutes a "fake IO" pthread pool that does no IO at all:
// it dequeues a pre-allocated worker_node_t from a plain mutex/condvar
// queue and immediately re-posts it via thread_work_post_io.
//
// Per iteration, on a worker:
//   1. Allocate task_obj_t.
//   2. Allocate worker_node_t (action = finisher, action.o = task).
//   3. Root both via static GC roots declared with
//      add_roots_declaration_func.
//   4. Register the user callback via task_on_complete (in `then`).
//   5. Hand the node to a fake-IO pthread.
//
// On the fake-IO pthread:
//   6. Dequeue the node and call thread_work_post_io(node).
//
// On a worker (action picked off the worker queue):
//   7. _finisher allocates several short strings — enough to drive the
//      FSA into mark+sweep some of the time.  Stores last result into
//      task->result via the GC write barrier and calls task_complete.
//
// If this reproduces the same crash/hang as test_io_stress, the bug is
// in the GC + thread/task machinery, not in io.c / io_thread.c.  If it
// does not, the IO library is doing something the GC objects to
// (writing through io->buf / in_flight, mutable-page allocation, etc.)
// and the search narrows accordingly.

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

// Allocations the finisher does per iteration.  Tuned so a few thousand
// iterations cross gc_fsa_mark_sweep boundaries multiple times.
#ifndef ALLOCS_PER_ITER
#define ALLOCS_PER_ITER 32
#endif

#ifndef FAKE_IO_THREAD_COUNT
#define FAKE_IO_THREAD_COUNT 4
#endif


// ---- Fake-IO threadpool ------------------------------------------------
//
// Plain mutex+condvar MPMC queue of worker_node_t pointers.  The node's
// own `next` field provides queue linkage — it's unused while the node
// is in transit (before being posted to a worker queue), so re-using
// it is safe.  No GC roots live here: the node is rooted via the
// static `_in_flight_node` while it's in this queue.

static pthread_mutex_t _fq_lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t  _fq_cond = PTHREAD_COND_INITIALIZER;
static worker_node_t*  _fq_head = NULL;
static worker_node_t*  _fq_tail = NULL;

static void _fq_enqueue(worker_node_t* node) {
    atomic_store(&node->next, (worker_node_t*)NULL);
    pthread_mutex_lock(&_fq_lock);
    if (_fq_tail) {
        atomic_store(&_fq_tail->next, node);
        _fq_tail = node;
    } else {
        _fq_head = node;
        _fq_tail = node;
    }
    pthread_cond_signal(&_fq_cond);
    pthread_mutex_unlock(&_fq_lock);
}

static worker_node_t* _fq_dequeue(void) {
    pthread_mutex_lock(&_fq_lock);
    while (_fq_head == NULL) {
        pthread_cond_wait(&_fq_cond, &_fq_lock);
    }
    worker_node_t* node = _fq_head;
    worker_node_t* next = atomic_load(&node->next);
    _fq_head = next;
    if (next == NULL) _fq_tail = NULL;
    atomic_store(&node->next, (worker_node_t*)NULL);
    pthread_mutex_unlock(&_fq_lock);
    return node;
}

static void* _fq_thread_main(void* arg) {
    (void)arg;
    for (;;) {
        worker_node_t* node = _fq_dequeue();
        thread_work_post_io(node);
    }
    return NULL;
}

static void _fq_init(void) {
    for (int i = 0; i < FAKE_IO_THREAD_COUNT; ++i) {
        pthread_t t;
        pthread_create(&t, NULL, _fq_thread_main, NULL);
        pthread_detach(t);
    }
}


// ---- CPS chaining helper (same shape as test_io_stress) ----------------

static void          (*_next_step)(object_t*);
static object_t*       _in_flight_task;   // GC root: task whose callback we're awaiting
static worker_node_t*  _in_flight_node;   // GC root: node currently on the fake-IO queue

static object_t* _trampoline(object_t* self_unused, object_t* task) {
    (void)self_unused;
    object_t* value = ((task_obj_t*)task)->result;
    void (*next)(object_t*) = _next_step;
    _next_step       = NULL;
    _in_flight_task  = NULL;
    _in_flight_node  = NULL;
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
                "after %d seconds.\n"
                "Likely a GC mark-sweep deadlock or lost-wakeup in the cross-thread post path.\n",
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


// Finisher.  Runs on a worker after the fake-IO thread re-posts the
// node.  Drives the FSA hard: ALLOCS_PER_ITER short strings per call,
// each one possibly triggering gc_page_alloc → gc_fsa → gc_fsa_mark_sweep.
// Finisher.  Single-arg: `_thread_work_invoke` invokes `node->action.f`
// with `node->action.o` as its only argument.  We arrange `action.o` to
// be the task pointer.
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


// One iteration.  Allocate task + node on this worker, root both, hand
// node to a fake-IO thread.  The chain resumes on the worker that the
// fake-IO thread eventually posts the node to.
static void _do_iteration(void) {
    task_obj_t* task = (task_obj_t*)object_create((vtable_t*)&TASK_OBJ_VTABLE);
    atomic_store(&task->parent.state, 0);   // TASK_PENDING
    task->result = NULL;

    worker_node_t* node = thread_work_prepare((fun_t){
        .f = (void*)_finisher,
        .o = (object_t*)task,
    });

    _in_flight_task = (object_t*)task;
    _in_flight_node = node;

    // Register the user-side callback BEFORE handing the node off, so
    // task_complete on the worker side can see CALLBACK rather than
    // PENDING and dispatch the trampoline.
    object_t* tagged = (object_t*)((uintptr_t)task | PTR_TAG_TASK);
    then(tagged, _step_done);

    _fq_enqueue(node);
}


static roots_declaration_func_t _prev_roots;
static void _stress_declare_roots(void(*declare)(object_t**)) {
    _prev_roots(declare);
    declare(&_in_flight_task);
    declare((object_t**)&_in_flight_node);
}


static void _entrypoint(object_t* self, fun_t continuation) {
    (void)self;
    _exit_cont = continuation;
    _iter_remaining = REPRO_ITERATIONS;

    _fq_init();

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
