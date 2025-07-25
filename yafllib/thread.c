
#include "common.h"
#include "yafl.h"
#include <pthread.h>


typedef struct worker_node {
    object_t parent;
    _Atomic(struct worker_node*) next;
    fun_t action;
} worker_node_t;


HIDDEN vtable_t* _worker_node_vt = VTABLE_DECLARE(0){
    .object_size = sizeof(worker_node_t),
    .array_el_size = 0,
    .object_pointer_locations = maskof(worker_node_t, .next) | maskof(worker_node_t, .action.o),
    .array_el_pointer_locations = 0,
    .functions_mask = 0,
    .array_len_offset = 0,
    .implements_array = VTABLE_IMPLEMENTS(0),
};

// There isn't an alloc_aligned, but by giving this struct an alignment
// we guarantee that it'll at least be spaced out in RAM. If the payload
// is relatively small it'll still have a whole cache line to itself.
typedef struct worker_queue {
    _Atomic(worker_node_t*) local_queue_head;
    _Atomic(worker_node_t*) sideload_queue_tail;
    _Atomic(bool) consumer_waiting_flag;
    pthread_mutex_t lock;
    pthread_cond_t cond;

} __attribute__((aligned(CACHE_LINE_SIZE))) worker_queue_t;

typedef struct worker_queues {
    object_t parent;
    int32_t  length;
    worker_queue_t array[1];
} worker_queues_t;


HIDDEN vtable_t* _worker_queues_vt = VTABLE_DECLARE(0){
    .object_size = offsetof(worker_queues_t, array[0]),
    .array_el_size = sizeof(worker_queue_t),
    .object_pointer_locations = 0,
    .array_el_pointer_locations = maskof(worker_queue_t, .local_queue_head) | maskof(worker_queue_t, .sideload_queue_tail),
    .functions_mask = 0,
    .array_len_offset = offsetof(worker_queues_t, length),
    .implements_array = VTABLE_IMPLEMENTS(0),
};


HIDDEN void(*_thread_worker_hook)();

HIDDEN worker_queues_t* _queues;

thread_local struct {
    worker_node_t* local_queue_tail;
    worker_node_t* sideload_queue_head;
} _locals;


EXPORT void declare_roots_thread(void(*declare)(object_t**)) {
    declare((object_t**)&_queues);
}

EXPORT void declare_local_roots_thread(void(*declare)(object_t**)) {
    declare((object_t**)&_locals.local_queue_tail);
    declare((object_t**)&_locals.sideload_queue_head);
}

HIDDEN void _thread_wake(worker_queue_t* queue) {
    if (atomic_load(&queue->consumer_waiting_flag)) {
        pthread_mutex_lock(&queue->lock);
        pthread_cond_signal(&queue->cond);
        pthread_mutex_unlock(&queue->lock);
    }
}

HIDDEN void _thread_wait(worker_queue_t* queue) {
    atomic_store(&queue->consumer_waiting_flag, true);
    pthread_mutex_lock(&queue->lock);
    if (atomic_load(&queue->local_queue_head)->next == NULL) {
        pthread_cond_wait(&queue->cond, &queue->lock);
    }
    pthread_mutex_unlock(&queue->lock);
    atomic_store(&queue->consumer_waiting_flag, false);
}

EXPORT void thread_set_hook(void (*hook)()) {
    _thread_worker_hook = hook;
    for (intptr_t index = 0; index < _queues->length; ++index) {
        _thread_wake(&_queues->array[index]);
    }
}


HIDDEN worker_node_t* _thread_create_node() {
    worker_node_t* node = (worker_node_t*)object_create(_worker_node_vt);
    node->action = (fun_t){.f = NULL, .o = NULL};
    node->next = NULL;
    return node;
}

HIDDEN worker_node_t* _thread_local_queue_try_steal(worker_queue_t* queue) {
    worker_node_t* head = atomic_load(&queue->local_queue_head);
    worker_node_t* node = atomic_load(&head->next);
    if (node == NULL) {
        // Empty queue
        return NULL;
    }

    if (!atomic_compare_exchange_strong(&queue->local_queue_head, &head, node)) {
        // Another thread got there before us
        return NULL;
    }

    return node;
}

HIDDEN void _thread_work_invoke(worker_node_t* node) {
    void(*fn)(void*) = (void(*)(void*))node->action.f;
    fn(node->action.o);
}

HIDDEN noreturn void __exit__(object_t* self, object_t* int_status) {
    int overflow;
    int32_t value = integer_to_int32(int_status, &overflow);
    exit(value);
    __builtin_unreachable();
}

static void _thread_init();

static void(*__entrypoint__)(object_t*, fun_t);
HIDDEN void* _thread_main_loop(void* param) {
    object_allocator_init();

    if (param == NULL) {
        _thread_init();
    }

    intptr_t thread_id = (intptr_t)param;
    worker_queue_t* queue = &_queues->array[thread_id];
    worker_queue_t* pre_queue = &_queues->array[(thread_id + _queues->length - 1) % _queues->length];
    worker_queue_t* post_queue = &_queues->array[(thread_id + 1) % _queues->length];
    _locals.local_queue_tail = queue->local_queue_head;
    _locals.sideload_queue_head = queue->sideload_queue_tail;

    if (thread_id == 0) {
        __entrypoint__(NULL, (fun_t){ .f=__exit__, .o=NULL });
    }

    for (;;) {
        // TODO: Check the compiled codegen to see that all paths are fast fail
        void(*hook)() = _thread_worker_hook;
        if (hook) {
            hook();
        }

        // Is there something on the IO queue
        worker_node_t* head = _locals.sideload_queue_head;
        worker_node_t* node = head->next;
        if (node) {
            _locals.sideload_queue_head = node;
            _thread_work_invoke(node);
            break;
        }

        // Is there something on the local work queue
        node = _thread_local_queue_try_steal(queue);
        if (node) {
            // If our neighbour is starved, wake it up
            _thread_wake(pre_queue);
            _thread_work_invoke(node);
            break;
        }

        // Can we steal from a neighbour
        node = _thread_local_queue_try_steal(post_queue);
        if (node) {
            _thread_work_invoke(node);
            break;
        }

        // TODO: This is all a bit dodgy... need to think through the logic to see if this won't deadlock
        _thread_wait(queue);
    }

    return NULL;
}

static void _thread_init() {
    intptr_t thread_count = 4;

    // Allocation is only allowed on worker threads. The launch thread is a worker thread.
    _queues = array_create(_worker_queues_vt, thread_count);

    // Initialise the queues
    for (intptr_t index = 0; index < thread_count; ++index) {
        worker_queue_t* queue = &_queues->array[index];
        atomic_store(&queue->local_queue_head, _thread_create_node());
        atomic_store(&queue->sideload_queue_tail, _thread_create_node());
        atomic_store(&queue->consumer_waiting_flag, false);
    }

    // Launch thread_count-1 threads
    for (intptr_t index = 1; index < thread_count; ++index) {
        pthread_t thread;
        pthread_create(&thread, NULL, _thread_main_loop, (void*)index);
    }
}


EXTERN object_t* thread_work_prepare(fun_t action) {
    worker_node_t* node = _thread_create_node();
    node->action = action;
    return &node->parent;
}

EXPORT void thread_work_post_fast(object_t* work) {
    // This is only ever called from the local thread, which means that we are in
    // an event currently. Therefore there is never a need to wake up the consumer.
    // It's already awake.
    worker_node_t* node = (worker_node_t*)work;
    node->next = _locals.local_queue_tail;
    _locals.local_queue_tail = node;
}

EXTERN void thread_work_post_io(object_t* work) {
    // This could be called from anywhere, but it's really designed for use from
    // interrupt contexts or IO threads, where we don't have a work queue. Instead
    // we post this to one of the existing sideload queues on a worker thread, and
    // notify it if it is sleeping. Threads will always take a sideload job in
    // preference to a normal work unit.
    worker_node_t* node = (worker_node_t*)work;
    worker_queue_t* queue = &_queues->array[(intptr_t)work % _queues->length];
    atomic_exchange(&queue->sideload_queue_tail, node)->next = node;
    if (atomic_load(&queue->consumer_waiting_flag)) {
        _thread_wake(queue);
    }
}

EXPORT void thread_start(void(*entrypoint)(object_t*, fun_t)) {
    __entrypoint__ = entrypoint;
    _thread_main_loop((void*)0);
}


