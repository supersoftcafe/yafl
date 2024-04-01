//
// Created by Michael Brown on 04/02/2023.
//

#include <threads.h>

#include <unistd.h>
#include <stdlib.h>
#include <signal.h>
#include <assert.h>

#include "lists.h"
#include "settings.h"
#include "fiber.h"
#include "blitz.h"
#include "mmap.h"
#include "threads.h"
#include "platform.h"






struct thread;
typedef struct thread thread_t;

static const int32_t MAGIC = 0x745ba28f;


struct fiber {
    __attribute__((aligned(16)))
    list_node_t l;

    int32_t magic;
    int use_count;

    uint_fast32_t join_count;     // Number of fibers to complete before scheduling this fiber again.
    struct fiber *exit_listener;  // Pointer to fiber that is waiting for a set of other fibers.

    heap_t heap;

    void **source;
    void **target;
};

struct thread {
    list_node_t l;

    atomic_flag lock;
    list_head_t free_fibers;
    list_head_t work_fibers;

    pthread_t thread_handle;
    // Local queues will go here
};


static void mutex_init(atomic_flag *lock_ptr) {
    atomic_flag_clear(lock_ptr);
}
static void mutex_lock(atomic_flag *lock_ptr) {
    while (atomic_flag_test_and_set(lock_ptr));
}
static void mutex_release(atomic_flag *lock_ptr) {
    atomic_flag_clear(lock_ptr);
}




static atomic_flag threads_lock;
static list_head_t threads;






enum { trim_count = 10000000 };
thread_local thread_t* thread_context = NULL;




object_t* fiber_object_create(vtable_t* vtable) {
    return object_create(&fiber_self()->heap, vtable);
}

object_t* fiber_object_create_array(vtable_t* vtable, uint32_t length) {
    return object_create_array(&fiber_self()->heap, vtable, length);
}

void fiber_object_heap_compact2(shadow_stack_t *shadow_stack) {
    object_heap_compact2(&fiber_self()->heap, shadow_stack);
}

void fiber_object_heap_compact(int count, object_t **array) {
    object_heap_compact(&fiber_self()->heap, count, array);
}






void fiber_schedule(fiber_t* fiber) {
    thread_t* thread = thread_context;
    if (thread == NULL) {
        // Probably called from a non-managed thread. Pick a random thread and schedule to that.
        thread = (thread_t*) lists_get_head(&threads); // Technically, the first thread is random.
    }

    mutex_lock(&thread->lock);
    lists_push(&thread->work_fibers, &fiber->l);
    mutex_release(&thread->lock);
}

static void fiber_free(struct fiber* fiber) {
    fiber->use_count ++;
    fiber->source = fiber->target = NULL; // Crap on it so any attempt to use it crashes
    fiber->magic = 0; // If we accidentally re-use this memory elsewhere, don't allow it to look like a fiber

    object_heap_destroy(&fiber->heap);

    if (fiber->use_count >= trim_count) {
        char* start = (char*)fiber + sizeof(struct fiber) - FIBER_SIZE;
        mmap_release(FIBER_SIZE, start);
    } else {
        thread_t* thread = thread_context;
        mutex_lock(&thread->lock);
        lists_push(&thread->free_fibers, &fiber->l);
        mutex_release(&thread->lock);
    }
}

static void fiber_terminate(void) {
    DEBUG("Terminating\n");
    exit(0);
}

static void fiber_init_struct(struct fiber* fiber, void(*exit_func)(void), void(*func)(void*), void* param) {
    object_heap_create(&fiber->heap);

    fiber->magic = MAGIC;
    fiber->use_count = 0;
    fiber->source = NULL;          // No saved source exists yet
    fiber->target = (void**)fiber; // Word after top of stack so next push brings RSP into actual stack space

    fiber_init_stack(&fiber->target, exit_func, func, param);
}

/**
 * Allocate a block of stacks and fill the TLS list of stacks. Each stack must be
 * aligned to a multiple of stack size, which itself is a power of two. There must
 * be a single protected page around each stack, so the usable size of the stack
 * becomes STACK_SIZE - PAGE_SIZE.
 */
fiber_t* fiber_create_from_mmap_heap() {
    char* ptr = mmap_alloc(FIBER_SIZE, FIBER_SIZE_LOG2);
    mmap_protect(PAGE_SIZE, ptr);    // Trap page for stack overflow
    fiber_t* fiber = (struct fiber*)(ptr + FIBER_SIZE - sizeof(struct fiber));
    return fiber;
}

static fiber_t* fiber_create(void(*func)(void*), void* param, void(*on_exit)(void)) {
    thread_t* thread = thread_context;
#ifndef NDEBUG
    if (thread == NULL)
        ERROR("fiber_create must only be called from fiber contexts\n");
#endif

    mutex_lock(&thread->lock);
    fiber_t *fiber = (fiber_t*) lists_pop_oldest(&thread->free_fibers);
    mutex_release(&thread->lock);

    if (fiber == NULL)
        fiber = fiber_create_from_mmap_heap();

    fiber_init_struct(fiber, on_exit, func, param);

    return fiber;
}

__attribute__((noinline))
static void initialise_and_register_thread(thread_t* thread, fiber_t* initial_fiber) {
    // Don't permit signal delivery to this thread.
    sigset_t mask;
    sigfillset(&mask);
    int sig_result = pthread_sigmask(SIG_BLOCK, &mask, NULL);
#ifndef NDEBUG
    if (sig_result != 0)
        ERROR("failed to block signals");
#endif

    // Initialise our thread struct
    lists_init(&thread->work_fibers);
    lists_init(&thread->free_fibers);
    thread->thread_handle = pthread_self();
    mutex_init(&thread->lock);

    if (initial_fiber)
        lists_push(&thread->work_fibers, &initial_fiber->l);

    // Add it to the circular list of threads
    mutex_lock(&threads_lock);
    lists_push(&threads, &thread->l);
    mutex_release(&threads_lock);

    // Store a thread local reference to the struct
    thread_context = thread;
}

_Noreturn __attribute__((noinline))
static void* fiber_scheduler2(thread_t *thread) {
    thread_t *mark = thread;
    for (;;) {
        // Take the newest job
        mutex_lock(&thread->lock);
        fiber_t* fiber = (fiber_t*) lists_pop_newest(&thread->work_fibers);
        mutex_release(&thread->lock);

        if (fiber == NULL && (mark = (thread_t*) lists_get_next(&threads, &mark->l)) != thread) {
            // Steal the oldest job
            mutex_lock(&mark->lock);
            fiber = (fiber_t*) lists_pop_oldest(&mark->work_fibers);
            mutex_release(&mark->lock);
        }

        if (fiber != NULL) {
            fiber_swap_context(&fiber->source, &fiber->target);
        } else {
            usleep(100000);
        }
    }
}

_Noreturn
static void* fiber_scheduler(fiber_t* initial_fiber) {
    thread_t thread;
    initialise_and_register_thread(&thread, initial_fiber);
    fiber_scheduler2(&thread);
}

void fiber_start(void(*init_func)(void*), void* init_param) {
    mutex_init(&threads_lock);
    lists_init(&threads);

    int thread_count = atoi(getenv("THREAD_COUNT") ?: "") ?: sysconf(_SC_NPROCESSORS_ONLN);
    if (thread_count <= 0)
        ERROR("sysconf(_SC_NPROCESSORS_ONLN)");
    DEBUG("THREAD_COUNT=%d\n", thread_count);
//    thread_count = 4;

    // Cannot use fiber_create as it must be called from fiber contexts. This isn't one.
    fiber_t* first_fiber = fiber_create_from_mmap_heap();
#ifndef NDEBUG
    if (first_fiber == NULL)
        ERROR("This is embarrassing. fiber_create_from_mmap_heap() returned NULL during startup.\n");
#endif
    fiber_init_struct(first_fiber, fiber_terminate, init_func, init_param);

    while (--thread_count >= 0) {
        pthread_t dont_care;
        int thread_result = pthread_create(&dont_care, NULL, (void*(*)(void*))fiber_scheduler, first_fiber);
        if (thread_result != 0)
            ERROR("Failed to create a worker thread with error %d\n", thread_result);
        first_fiber = NULL;
    }
}

fiber_t* fiber_self() {
    intptr_t mask = FIBER_SIZE - 1;
    fiber_t* fiber = (struct fiber*)((((intptr_t)&mask) & ~mask) + FIBER_SIZE - sizeof(struct fiber));
#ifndef NDEBUG
    if (unlikely(fiber->magic != MAGIC))
        ERROR("fiber_self() called from non-fiber context\n");
#endif
    return fiber;
}

void fiber_yield() {
#ifndef NDEBUG
    if (unlikely(thread_context == NULL))
        ERROR("fiber_yield can only be called from a fiber context\n");
#endif

    struct fiber* fiber = fiber_self();
    fiber_swap_context(&fiber->target, &fiber->source);
}

static void fiber_on_exit() {
    fiber_t* exit_listener = fiber_self()->exit_listener;
    if (atomic_fetch_sub(&exit_listener->join_count, 1) == 1)
        fiber_schedule(exit_listener);
    fiber_yield();
}

void fiber_parallel(void* param, void(**funcs)(void*), int count) {
#ifndef NDEBUG
    if (thread_context == NULL)
        ERROR("fiber_schedule_and_join can only be called from a fiber context\n");
#endif
    if (count <= 0)
        return;

    struct fiber* self = fiber_self();

    self->join_count = count;
    fiber_t** fibers = alloca(sizeof(fiber_t*) * count);

    for (int index = 0; index < count; ++index) {
        fiber_t* fiber = fiber_create(funcs[index], param, fiber_on_exit);
        fibers[index] = fiber;
        fiber->exit_listener = self;
        fiber_schedule(fiber);
    }

    fiber_yield();

    for (int index = 0; index < count; ++index) {
        fiber_t* fiber = fibers[index];
        object_heap_append(&self->heap, &fiber->heap);
        fiber_free(fiber);
    }
}



