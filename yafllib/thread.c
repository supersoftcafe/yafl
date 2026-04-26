
#include "yafl.h"
#include <pthread.h>
#include <time.h>

EXPORT vtable_t* _worker_node_vt = VTABLE_DECLARE(0){
    .object_size = sizeof(worker_node_t),
    .array_el_size = 0,
    .object_pointer_locations = maskof(worker_node_t, .next) | maskof(worker_node_t, .action.o),
    .array_el_pointer_locations = 0,
    .functions_mask = 0,
    .array_len_offset = 0,
    .is_mutable = 1,
    .name = "worker_node",
    .implements_array = VTABLE_IMPLEMENTS(0),
};

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
    worker_node_t*  head;   // oldest queued node; NULL when empty
    worker_node_t*  tail;   // newest queued node; == head when one item
} __attribute__((aligned(CACHE_LINE_SIZE))) worker_queue_t;

typedef struct worker_queues {
    object_t parent;
    int32_t  length;
    worker_queue_t array[16];
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

// Owner's queue — set by each worker in its main-loop prologue so that
// post_fast targets the owner's queue instead of round-robining.  Not GC-
// rooted because it aliases a slot inside the already-rooted _queues array.
static thread_local worker_queue_t* _my_queue = NULL;


EXPORT void declare_roots_thread(void(*declare)(object_t**)) {
    declare((object_t**)&_queues);
}

// No GC-tracked per-thread state in this file — each queue owns its head
// and tail under its mutex, and those live inside _queues which is already
// rooted.  Kept as a thin callback for gc_declare_thread's API.
static void declare_local_roots_thread(void* unused_ctx, void(*declare)(object_t**)) {
    (void)unused_ctx; (void)declare;
}


// Push `work` onto `queue` and wake any consumer waiting on it.  Serialises
// all producers against the consumer's empty-check + cond_wait.
static void _queue_push(worker_queue_t* queue, worker_node_t* work) {
    work->next = NULL;
    pthread_mutex_lock(&queue->lock);
    if (queue->tail) {
        queue->tail->next = work;
    } else {
        queue->head = work;
    }
    queue->tail = work;
    pthread_cond_signal(&queue->cond);
    pthread_mutex_unlock(&queue->lock);
}

// Pop the oldest entry from `queue`, or NULL if empty.  Non-blocking.
static worker_node_t* _queue_try_pop(worker_queue_t* queue) {
    pthread_mutex_lock(&queue->lock);
    worker_node_t* node = queue->head;
    if (node) {
        queue->head = node->next;
        if (queue->head == NULL) queue->tail = NULL;
        node->next = NULL;
    }
    pthread_mutex_unlock(&queue->lock);
    return node;
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


HIDDEN worker_node_t* _thread_create_node() {
    worker_node_t* node = (worker_node_t*)object_create(_worker_node_vt);
    node->action = (fun_t){.f = NULL, .o = NULL};
    node->next = NULL;
    return node;
}

HIDDEN void _thread_work_invoke(intptr_t thread_id, worker_node_t* node) {
    (void)thread_id;
    void(*fn)(void*) = (void(*)(void*))node->action.f;
    fn(node->action.o);
}

static struct timespec t_start;
static struct timespec t_end;
HIDDEN noreturn void __exit__(object_t* self, object_t* arg) {
    clock_gettime(CLOCK_MONOTONIC, &t_end);
    double seconds = (t_end.tv_sec - t_start.tv_sec) + (t_end.tv_nsec - t_start.tv_nsec) / 1e9;
    printf("Duration: %.2f s\n", seconds);

    // __entrypoint__ calls us either directly with main's integer result
    // (sync path) or via task_on_complete with main's task (async path).
    // Distinguish: tasks are untagged heap objects with TASK_OBJ_VTABLE.
    object_t* int_status = arg;
    if (arg != NULL && !((uintptr_t)arg & PTR_TAG_MASK)) {
        vtable_t* vt = VT_TAG_UNSET(arg->vtable);
        if (vt == (vtable_t*)&TASK_OBJ_VTABLE) {
            int_status = ((task_obj_t*)arg)->result;
        }
    }

    int overflow;
    int32_t value = integer_to_int32_with_overflow(int_status, &overflow);
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
    _my_queue = queue;

    if (thread_id == 0) {
        __entrypoint__(NULL, (fun_t){ .f=__exit__, .o=NULL });
    }

    if (atomic_fetch_sub(&_thread_countdown_to_gc_start, 1) == 1) {
        gc_start();
    }

    intptr_t length = _queues->length;
    for (;;) {
        // Fast path: pop one from our own queue.
        worker_node_t* node = _queue_try_pop(queue);
        if (node) {
            _thread_work_invoke(thread_id, node);
            continue;
        }

        // Try to steal from another worker.
        for (intptr_t offset = 1; offset < length; ++offset) {
            intptr_t victim = (thread_id + offset) % length;
            node = _queue_try_pop(&_queues->array[victim]);
            if (node) break;
        }
        if (node) {
            _thread_work_invoke(thread_id, node);
            continue;
        }

        // Nothing to do.  Wait on our own queue.  Re-check under the
        // mutex before sleeping so that a producer that pushed after our
        // last try_pop but before we acquire the lock wakes us here.
        _queue_wait_for_work(queue);
    }

    return NULL;
}

static void _thread_init() {
    intptr_t thread_count = 2;
    _thread_countdown_to_gc_start = thread_count;

    object_gc_init(); // Initialise the GC system

    // Allocation is only allowed on worker threads. The launch thread is a worker thread.
    _queues = array_create(_worker_queues_vt, thread_count);

    // Initialise the queues
    for (intptr_t index = 0; index < thread_count; ++index) {
        worker_queue_t* queue = &_queues->array[index];
        pthread_mutex_init(&queue->lock, NULL);
        pthread_cond_init(&queue->cond, NULL);
        queue->head = NULL;
        queue->tail = NULL;
    }

    // Launch thread_count-1 threads
    for (intptr_t index = 1; index < thread_count; ++index) {
        pthread_t thread;
        pthread_create(&thread, NULL, _thread_main_loop, (void*)index);
    }

    // Private IO threadpool — started after the worker queues exist so it
    // can post to them; before __entrypoint__ so the first IO call has
    // somewhere to dispatch to.
    _io_threadpool_init();
}

EXPORT worker_node_t* thread_work_prepare(fun_t action) {
    worker_node_t* node = (worker_node_t*)object_create(_worker_node_vt);
    node->next = (worker_node_t*)NULL;
    node->action = action;
    return node;
}

// Post to the owner's own queue.  The owner is the running worker thread;
// the mutex is uncontended most of the time on the self-post path.
EXPORT void thread_work_post_fast(worker_node_t* work) {
    _queue_push(_my_queue, work);
}

static _Atomic(uint32_t) _io_post_counter;

// Cross-thread post (IO threads, interrupts).  Picks a worker round-robin,
// starting at 1 so the entry thread receives IO work only as a fallback
// when there is no other worker.
EXTERN void thread_work_post_io(worker_node_t* work) {
    uint32_t idx = (1 + atomic_fetch_add(&_io_post_counter, 1)) % (uint32_t)_queues->length;
    _queue_push(&_queues->array[idx], work);
}

EXPORT void thread_dispatch_io(fun_t action) {
    thread_work_post_io(thread_work_prepare(action));
}

EXPORT void thread_dispatch_fast(fun_t action) {
    thread_work_post_fast(thread_work_prepare(action));
}

EXPORT void thread_start(void(*entrypoint)(object_t*, fun_t)) {
    clock_gettime(CLOCK_MONOTONIC, &t_start);
    __entrypoint__ = entrypoint;
    _thread_main_loop((void*)0);
}
