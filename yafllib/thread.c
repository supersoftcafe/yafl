
#include "yafl.h"
#include <pthread.h>
#include <time.h>
#include <unistd.h>
#include <stdlib.h>

// One queue per worker.  All producers — the owner posting its own work,
// other workers returning stolen-result callbacks, IO threads posting
// completions — take the mutex to push and signal.  All consumers (the
// owner, and stealing neighbours) take the mutex to pop.  A single wake-up
// channel per worker: the empty-check and the cond_wait happen under the
// same mutex the producer takes to push and signal, so the classic
// sideload/flag lost-wakeup race cannot occur.
typedef struct worker_queue {
    pthread_mutex_t lock;
    pthread_cond_t  cond;
    task_t*         head;   // oldest queued task; NULL when empty
    task_t*         tail;   // newest queued task; == head when one item
} __attribute__((aligned(CACHE_LINE_SIZE))) worker_queue_t;

// Upper bound on the worker pool. The static `array` declaration is just
// a placeholder for the GC's variable-length array allocation (object_size
// is taken from offsetof(.., array[0])); raising MAX_WORKERS only requires
// growing the placeholder size to match.
#define MAX_WORKERS 16

typedef struct worker_queues {
    object_t parent;
    int32_t  length;
    worker_queue_t array[MAX_WORKERS];
} worker_queues_t;


HIDDEN vtable_t* _worker_queues_vt = VTABLE_DECLARE(0){
    .object_size = offsetof(worker_queues_t, array[0]),
    .array_el_size = sizeof(worker_queue_t),
    .object_pointer_locations = 0,
    .array_el_pointer_locations = maskof(worker_queue_t, .head) | maskof(worker_queue_t, .tail),
    .functions_mask = 0,
    .array_len_offset = offsetof(worker_queues_t, length),
    .is_mutable = 1,
    .name = "worker_queues",
    .implements_array = VTABLE_IMPLEMENTS(0),
};


HIDDEN worker_queues_t* _queues;

// Owner's queue and thread index — set by each worker in its main-loop
// prologue.  Not GC-rooted because _my_queue aliases a slot inside the
// already-rooted _queues array.
static thread_local worker_queue_t* _my_queue    = NULL;
static thread_local int32_t         _my_thread_id = 0;


EXPORT void declare_roots_thread(void(*declare)(object_t**)) {
    declare((object_t**)&_queues);
}

static void declare_local_roots_thread(void* unused_ctx, void(*declare)(object_t**)) {
    (void)unused_ctx; (void)declare;
}

EXPORT int32_t thread_current_id(void) {
    return _my_thread_id;
}


// Tasks currently sitting in worker queues, waiting to run. Suspended tasks
// (parked on a callback) deliberately do NOT count: backpressure is about
// runnable backlog, not about how much work is in flight overall.
static _Atomic(int_fast32_t) _queued_count = 0;
static int_fast32_t          _backlog_limit = 0;   // set in _thread_init

// Advisory backpressure signal for __parallel__ call sites: true while the
// runnable backlog is below ~YAFL_TASK_BACKLOG (default 4) tasks per worker.
// Callers fork new parallel work when it returns true and fall back to plain
// chained evaluation when it returns false. Purely advisory — a stale answer
// costs one extra fork or one extra sequential step, and recursive call sites
// re-ask at every level.
EXPORT bool thread_work_accepting(void) {
    return atomic_load_explicit(&_queued_count, memory_order_relaxed) <= _backlog_limit;
}

// Push `task` onto `queue` and wake any consumer waiting on it.
static void _queue_push(worker_queue_t* queue, task_t* task) {
    // Insertion barrier (same hazard as task_on_complete): once pushed, the
    // queue linkage may be this task's only reference, and the poster's stack
    // — the marker's only other way to see it — may already have been scanned
    // this cycle. Tell the marker directly or it prunes a queued task.
    GC_MARK_SEEN((object_t*)task);
    atomic_store(&task->next, (task_t*)NULL);
    atomic_fetch_add_explicit(&_queued_count, 1, memory_order_relaxed);
    pthread_mutex_lock(&queue->lock);
    if (queue->tail) {
        atomic_store(&queue->tail->next, task);
    } else {
        queue->head = task;
    }
    queue->tail = task;
    pthread_cond_signal(&queue->cond);
    pthread_mutex_unlock(&queue->lock);
}

// Pop the oldest entry from `queue`, or NULL if empty.  Non-blocking.
static task_t* _queue_try_pop(worker_queue_t* queue) {
    pthread_mutex_lock(&queue->lock);
    task_t* task = queue->head;
    if (task) {
        queue->head = atomic_load(&task->next);
        if (queue->head == NULL) queue->tail = NULL;
        // Deletion barrier before clearing the chain link: the successor's
        // snapshot reachability runs through task->next, and after this store
        // its only reference is queue->head. Erasing the edge unbarriered lets
        // the marker lose the rest of the queue if `task` is walked after the
        // clear — the successor is then pruned while still queued.
        GC_WRITE_BARRIER(task->next, 1);
        atomic_store(&task->next, (task_t*)NULL);
        atomic_fetch_sub_explicit(&_queued_count, 1, memory_order_relaxed);
    }
    pthread_mutex_unlock(&queue->lock);
    return task;
}

// Block until the queue has work.  Wrapped in a NOINLINE'd helper so that
// gc_update_stack_and_registers (called from gc_io_begin) captures a stack
// address deeper than gc_declare_thread's captured address — the GC relies
// on stack_lower < stack_upper and using a separate function here
// guarantees the extra frame.
static void __attribute__((noinline)) _queue_wait_for_work(worker_queue_t* queue) {
    gc_io_begin();
    pthread_mutex_lock(&queue->lock);
    while (queue->head == NULL) {
        pthread_cond_wait(&queue->cond, &queue->lock);
    }
    pthread_mutex_unlock(&queue->lock);
    gc_io_end();
}


// Set by thread_start when YAFL_DURATION is non-empty; gates the timing
// instrumentation so production runs don't print to stdout.
static bool _print_duration = false;
static struct timespec t_start;
static struct timespec t_end;
HIDDEN noreturn void __exit__(object_t* self, object_t* arg) {
    (void)self;   // ABI receiver, unused here
    if (_print_duration) {
        clock_gettime(CLOCK_MONOTONIC, &t_end);
        double seconds = (t_end.tv_sec - t_start.tv_sec) + (t_end.tv_nsec - t_start.tv_nsec) / 1e9;
        printf("Duration: %.2f s\n", seconds);
    }

    // __entrypoint__ calls us either directly with main's integer result
    // (sync path) or via task_on_complete with main's task (async path).
    // Distinguish: tasks are untagged heap objects with TASK_OBJ_VTABLE.
    object_t* int_status = arg;
    if (arg != NULL && !((uintptr_t)arg & PTR_TAG_MASK)) {
        // Forwarding-aware vtable read (compaction may have relocated arg).
        vtable_t* vt = object_get_vtable(arg);
        if (vt == (vtable_t*)&TASK_OBJ_VTABLE) {
            int_status = ((task_obj_t*)arg)->result;
        }
    }

    int overflow;
    int32_t value = int32_from_integer_with_overflow(int_status, &overflow);
    exit(value);
    __builtin_unreachable();
}

static void _thread_init();
HIDDEN void _io_threadpool_init(void);   // forward decl from io_thread.c

static atomic_intptr_t _thread_countdown_to_gc_start;

static void(*__entrypoint__)(object_t*, fun_t);
HIDDEN void* _thread_main_loop(void* param) {
    gc_declare_thread((void*)declare_local_roots_thread, NULL);

    if (param == (void*)0) {
        _thread_init();
    }

    intptr_t thread_id = (intptr_t)param;
    worker_queue_t* queue = &_queues->array[thread_id];
    _my_queue     = queue;
    _my_thread_id = (int32_t)thread_id;

    // Start the GC once every worker has registered its stack — but BEFORE
    // thread 0 runs the entry point. A fully-synchronous main() never returns
    // from __entrypoint__ (it runs to completion and exits there), so decrementing
    // after the entry-point call left the countdown stuck at 1 and the collector
    // never started — the heap then just filled until OOM.
    if (atomic_fetch_sub(&_thread_countdown_to_gc_start, 1) == 1) {
        gc_start();
    }

    if (thread_id == 0) {
        __entrypoint__(NULL, (fun_t){ .f=__exit__, .o=NULL });
    }

    intptr_t length = _queues->length;
    for (;;) {
        // Fast path: pop one from our own queue.
        task_t* task = _queue_try_pop(queue);
        if (task) {
            task_complete((object_t*)task);
            continue;
        }

        // Try to steal from another worker.
        for (intptr_t offset = 1; offset < length; ++offset) {
            intptr_t victim = (thread_id + offset) % length;
            task = _queue_try_pop(&_queues->array[victim]);
            if (task) break;
        }
        if (task) {
            task_complete((object_t*)task);
            continue;
        }

        // Nothing to do.  Wait on our own queue.
        _queue_wait_for_work(queue);
    }

    return NULL;
}

// Decide how many workers to spawn. YAFL_THREADS overrides; otherwise use
// the OS-reported online CPU count. Clamped to [1, MAX_WORKERS].
static intptr_t _detect_thread_count(void) {
    const char* env = getenv("YAFL_THREADS");
    if (env && *env) {
        long n = strtol(env, NULL, 10);
        if (n >= 1) return n > MAX_WORKERS ? MAX_WORKERS : (intptr_t)n;
    }
    long n = sysconf(_SC_NPROCESSORS_ONLN);
    if (n < 1) n = 1;
    if (n > MAX_WORKERS) n = MAX_WORKERS;
    return (intptr_t)n;
}

static void _thread_init() {
    intptr_t thread_count = _detect_thread_count();
    _thread_countdown_to_gc_start = thread_count;

    // Backpressure threshold: YAFL_TASK_BACKLOG (default 4) queued tasks per
    // worker. Above this, thread_work_accepting() asks __parallel__ sites to
    // evaluate sequentially instead of forking.
    {
        int_fast32_t per_worker = 4;
        const char* env = getenv("YAFL_TASK_BACKLOG");
        if (env && *env) {
            long n = strtol(env, NULL, 10);
            if (n >= 1) per_worker = (int_fast32_t)n;
        }
        _backlog_limit = per_worker * (int_fast32_t)thread_count;
    }

    object_gc_init();

    _queues = array_create(_worker_queues_vt, thread_count);

    for (intptr_t index = 0; index < thread_count; ++index) {
        worker_queue_t* queue = &_queues->array[index];
        pthread_mutex_init(&queue->lock, NULL);
        pthread_cond_init(&queue->cond, NULL);
        queue->head = NULL;
        queue->tail = NULL;
    }

    for (intptr_t index = 1; index < thread_count; ++index) {
        pthread_t thread;
        pthread_create(&thread, NULL, _thread_main_loop, (void*)index);
    }

    _io_threadpool_init();
}

EXPORT void thread_work_post(object_t* self) {
    task_t* task = (task_t*)self;
    _queue_push(&_queues->array[task->thread_id], task);
}

static _Atomic(uint32_t) _parallel_post_counter;

EXPORT object_t* thread_work_post_parallel(object_t* self) {
    uint32_t idx = (1 + atomic_fetch_add(&_parallel_post_counter, 1)) % (uint32_t)_queues->length;
    _queue_push(&_queues->array[idx], (task_t*)self);
    return NULL;
}

EXPORT object_t* thread_dispatch(fun_t action) {
    object_t* task = task_create(NULL);
    task_on_complete(task, action);   // PENDING → CALLBACK
    thread_work_post(task);
    return NULL;
}

EXPORT void thread_start(void(*entrypoint)(object_t*, fun_t)) {
    const char* dur = getenv("YAFL_DURATION");
    _print_duration = (dur != NULL && *dur != '\0');
    if (_print_duration) clock_gettime(CLOCK_MONOTONIC, &t_start);
    __entrypoint__ = entrypoint;
    _thread_main_loop((void*)0);
}
