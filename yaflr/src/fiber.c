//
// Created by Michael Brown on 04/02/2023.
//

#include <threads.h>
#include <unistd.h>
#include <stdlib.h>
#include <signal.h>
#include <assert.h>

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
    int32_t magic;
    int use_count;

    uint_fast32_t join_count;     // Number of fibers to complete before scheduling this fiber again.
    struct fiber* exit_listener;  // Pointer to fiber that is waiting for a set of other fibers.

    heap_t    heap;

    void**  source;
    void**  target;

    struct fiber* next;
} __attribute__((aligned(16)));

struct thread {
    thread_t* next_thread;

    atomic_flag lock;
    fiber_t* free_fibers;
    fiber_t* work_fibers;

    pthread_t thread_handle;
    // Local queues will go here
};


static inline void mutex_init(atomic_flag* lock_ptr) {
    atomic_flag_clear(lock_ptr);
}
static inline void mutex_lock(atomic_flag* lock_ptr) {
    while (atomic_flag_test_and_set(lock_ptr));
}
static inline void mutex_release(atomic_flag* lock_ptr) {
    atomic_flag_clear(lock_ptr);
}



static thread_t* threads;






enum { trim_count = 10000 };
thread_local thread_t* thread_context = NULL;




object_t* fiber_object_create(vtable_t* vtable) {
    return object_create(&fiber_self()->heap, vtable);
}

object_t* fiber_object_create_array(vtable_t* vtable, uint32_t length) {
    return object_create_array(&fiber_self()->heap, vtable, length);
}

void fiber_object_heap_compact(int root_count, object_t** roots) {
    object_heap_compact(&fiber_self()->heap, root_count, roots);
}






void fiber_schedule(fiber_t* fiber) {
    thread_t* thread = thread_context;
    if (thread == NULL) {
        // Probably called from a non-managed thread. Pick a random thread and schedule to that.
        thread = threads; // Technically, the first thread is random...  ahem...
    }

    mutex_lock(&thread->lock);
    fiber->next = thread->work_fibers;
    thread->work_fibers = fiber;
    mutex_release(&thread->lock);
}

static void fiber_free(struct fiber* fiber) {
    DEBUG("Deleting %lx\n", (intptr_t)fiber);

    fiber->use_count ++;
    fiber->source = fiber->target = NULL; // Crap on it so any attempt to use it crashes
    object_heap_destroy(&fiber->heap);

    if (unlikely(fiber->use_count >= trim_count)) {
        char* start = (char*)fiber + sizeof(struct fiber) - FIBER_SIZE;
        mmap_release(FIBER_SIZE, start);
    } else {
        fiber->magic = 0; // If we accidentally re-use this memory elsewhere, don't allow it to look like a fiber

        thread_t* thread = thread_context;
        mutex_lock(&thread->lock);
        fiber->next = thread->free_fibers;
        thread->free_fibers = fiber;
        mutex_release(&thread->lock);
    }
}

static void fiber_terminate(void) {
    DEBUG("Terminating\n");
    exit(0);
}

static void fiber_donothing(void) {
    // It's only purpose is to call 'ret' and pop one more item off of the stack
}

static void fiber_init_struct(struct fiber* fiber, void(*exit_func)(void), void(*func)(void*), void* param) {
    object_heap_create(&fiber->heap);

    fiber->magic = MAGIC;
    fiber->use_count = 0;
    fiber->source = NULL;          // No saved source exists yet
    fiber->target = (void**)fiber; // Word after top of stack so next push brings RSP into actual stack space

    void** target = fiber->target -= 11;
    target[10] = NULL;
    target[9] = exit_func; // When entry function exits, it'll automatically branch to the exit function. Neat!
    target[8] = fiber_donothing;    // Filler. It pops the next item, that's all.
    target[7] = func;
    target[6] = param;
    target[5] = NULL;
    target[4] = NULL;
    target[3] = NULL;
    target[2] = NULL;
    target[1] = NULL;
    target[0] = NULL;
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

    fiber_t* fiber = thread->free_fibers;
    if (unlikely(fiber == NULL)) {
        fiber = fiber_create_from_mmap_heap();
    } else {
        thread->free_fibers = fiber->next;
    }

    fiber_init_struct(fiber, on_exit, func, param);
    return fiber;
}

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
    thread->next_thread = NULL;
    thread->work_fibers = initial_fiber;
    thread->free_fibers = NULL;
    thread->thread_handle = pthread_self();
    atomic_flag_clear(&thread->lock);

    // Add it to the circular list of threads
    thread_t* existing;
    do {
        existing = threads;
        if (existing == NULL) {
            thread->next_thread = thread;
        } else {
            thread->next_thread = existing;
        }
    } while (atomic_compare_exchange_weak(&threads, &existing, thread));

    // Store a thread local reference to the struct
    thread_context = thread;
}

static fiber_t* find_work(thread_t* thread) {
    // Hopefully our local thread has some jobs, but if not we'll scour the neighbouring threads for jobs.
    for (thread_t* start = thread; thread->work_fibers == NULL && start != (thread = thread->next_thread); );

    // The situation might have changed by the time we get here, but it doesn't matter, since we'll just try again later.
    mutex_lock(&thread->lock);
    fiber_t* fiber = thread->work_fibers;
    if (fiber != NULL)
        thread->work_fibers = fiber->next;
    mutex_release(&thread->lock);

    return fiber;
}

_Noreturn __attribute__((noinline))
static void* fiber_scheduler(fiber_t* initial_fiber) {
    thread_t thread;
    initialise_and_register_thread(&thread, initial_fiber);

    for (;;) {
        fiber_t* fiber = find_work(&thread);

        if (fiber != NULL) {
            fiber_swap_context(&fiber->source, &fiber->target);
        } else {
            usleep(100000);
        }
    }
}

void fiber_start(void(*init_func)(void*), void* init_param) {
    int thread_count = atoi(getenv("THREAD_COUNT") ?: "") ?: sysconf(_SC_NPROCESSORS_ONLN);
    if (thread_count <= 0)
        ERROR("sysconf(_SC_NPROCESSORS_ONLN)");
    DEBUG("THREAD_COUNT=%d\n", thread_count);

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

__attribute__((noinline))
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



