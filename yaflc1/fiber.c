//
// Created by Michael Brown on 04/02/2023.
//

#include <unistd.h>
#include <stdlib.h>
#include <stdio.h>
#include <stdatomic.h>
#include <pthread.h>
#include <stdarg.h>

#include "context.h"
#include "queue.h"
#include "fiber.h"
#include "blitz.h"

void fiber_swap_context(void*** source_sp_ptr, void*** target_sp_ptr);

#ifndef __STDC_NO_THREADS__
#include <threads.h>
#endif

#ifndef __STDC_NO_ATOMICS__
#include <stdatomic.h>
#endif


#ifndef thread_local
# if __STDC_VERSION__ >= 201112 && !defined __STDC_NO_THREADS__
#  define thread_local _Thread_local
# elif defined _WIN32 && ( \
       defined _MSC_VER || \
       defined __ICL || \
       defined __DMC__ || \
       defined __BORLANDC__ )
#  define thread_local __declspec(thread)
/* note that ICC (linux) and Clang are covered by __GNUC__ */
# elif defined __GNUC__ || \
       defined __SUNPRO_C || \
       defined __xlC__
#  define thread_local __thread
# else
#  error "Cannot define thread_local"
# endif
#endif



#define likely(x)       __builtin_expect((x),1)
#define unlikely(x)     __builtin_expect((x),0)





struct fiber {
    uint32_t magic;

    // Count down to trim unused pages. Remove all pages, so that it uses no memory unless actually used again.
    // Also put at end of list, so unlikely to be used again.
    int32_t trim_counter;


    atomic_intptr_t exit_flag;      // Set by exit func so scheduler knows to delete this fiber.
    atomic_intptr_t join_count;     // Number of fibers to complete before scheduling this fiber again.
    struct fiber*   exit_listener;  // Pointer to fiber that is waiting for a set of other fibers.


    // Priority on queue. Initially 0 which means "give me a priority when enqueued".
    intptr_t priority;

    void**  source;
    void**  target;

    struct fiber* next;
} __attribute__((aligned(16)));

struct thread {
    struct fiber* next_free_fiber;
    pthread_t thread_handle;
    // Local queues will go here
};



static int      MAX_FIBER_COUNT;
static size_t   FIBER_SIZE;
static int      PAGE_SIZE;
static int32_t  TRIM_COUNT;
static size_t   FIBER_SIZE_ROUNDUP;
static int      THREAD_COUNT;
static const uint32_t MAGIC = 0xc948fe81;

static atomic_int_fast32_t fiber_count = 0;
static struct thread* threads;
static atomic_intptr_t next_priority = 0;


// Make fiber memory allocation only create one fiber.
// Have max number of fibers and return null when we hit max.
// Single priority queue and use pthread_mutex/pthread_cond to access it.
// Fiber priority is chosen when it is allocated, and priority++.
// Priority-global priority is used for sorting to get rid of overflow problem.
// Signal handler should correctly report stack overflow when trip page is hit.
// Fiber stack size can be any value > 8192 and multiple of 4096.
// Top of stack must align to 2^n for fiber_self() to work.
// Wrap mmap in a fast fail version that uses perror.


/* Queue logic
 *  Maximum number of fibers that can exist is N.
 *  Per thread queue size is >N so we can never overflow.
 *  Reader needs no lock, it just advances whilst non-null and spins on null.
 *  Reader can suspend, after setting a suspend flag with a write barrier.
 *  Writer uses an atomic increment to allocate a writing slot. It then just writes, with no checks.
 *  If suspend flag is set, it also wakes the thread. Spurious wakes are ok.
 *
 *  To avoid all CAS operations each thread, including tertiary IO threads, has nominated 4
 *  workers with whom it has a direct 1:1 short queue. It will always prioritise those 4
 *  threads with messages. The readers on those threads will always check the 1:1 queues
 *  as well as its main queue.
 */






thread_local struct thread* thread_context = NULL;


void fiber_schedule(fiber_t* fiber) {
    // Can be called from any thread in the system
    queue_push(fiber, fiber->priority);
}

static __attribute__((noinline))
void fiber_free(struct fiber* fiber) {
    DEBUG("Deleting %lx\n", (uintptr_t)fiber);

    if (unlikely(--fiber->trim_counter == 0)) {
        char* start = (char*)fiber + sizeof(struct fiber) - FIBER_SIZE;
        munmap_or_fail(start, FIBER_SIZE);
        atomic_fetch_add(&fiber_count, 1);
    } else {
        struct thread* tlp = thread_context;
        fiber->source = fiber->target = NULL; // Crap on it so any attempt to use it crashes
        fiber->next = tlp->next_free_fiber;
        tlp->next_free_fiber = fiber;
    }
}

static void fiber_exit(void) {
    struct fiber* fiber = fiber_self();
    DEBUG("Exiting %lx\n", (uintptr_t)fiber);
    fiber->exit_flag = 1;
    fiber_yield();
}

static void fiber_terminate(void) {
    struct fiber* fiber = fiber_self();
    DEBUG("Terminating %lx\n", (uintptr_t)fiber);
    exit(0);
}

static void fiber_donothing(void) {
    // It's only purpose is to call 'ret' and pop one more item off of the stack
}

static void fiber_init_struct(struct fiber* fiber, void(*exit_func)(void), void(*func)(void*), void* param) {
    fiber->source = NULL;          // No saved source exists yet
    fiber->target = (void**)fiber; // Word after top of stack so next push brings RSP into actual stack space
    fiber->exit_flag = 0;
    fiber->priority = atomic_fetch_add(&next_priority, 1); // This will wrap sometimes. Oh well.

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
static __attribute__((noinline))
struct fiber* fiber_create_from_heap() {
    if (atomic_fetch_sub(&fiber_count, 1) == 0) {
        atomic_fetch_add(&fiber_count, 1);
        return NULL;
    }

    uintptr_t mask = FIBER_SIZE_ROUNDUP - 1;
    size_t    size = FIBER_SIZE_ROUNDUP * 2 - PAGE_SIZE;
    char*      ptr = mmap_or_fail(0, size, PROT_READ|PROT_WRITE, MAP_PRIVATE|MAP_ANON, -1, 0);

    char* end = (char*) ((((uintptr_t)ptr) + mask) & ~mask) + FIBER_SIZE_ROUNDUP;
    char* start = end - FIBER_SIZE;

    if (ptr != start) {
        munmap_or_fail(ptr, start - ptr);
        size -= start - ptr;
    }

    if (size > FIBER_SIZE) {
        munmap_or_fail(end, size - FIBER_SIZE);
    }

    mprotect_or_fail(start, PAGE_SIZE, PROT_NONE);    // Trap page for stack overflow
    struct fiber* fiber = (struct fiber*)(end - sizeof(struct fiber));
    fiber->trim_counter = TRIM_COUNT;
    fiber->magic = MAGIC;

    DEBUG("fiber_create_from_heap %lx\n", (uintptr_t)fiber);

    return fiber;
}

__attribute__((noinline))
struct fiber* fiber_create(void(*func)(void*), void* param) {
    struct thread* tlp = thread_context;

#ifndef NDEBUG
    if (tlp == NULL)
        ERROR("fiber_create must only be called from fiber contexts\n");
#endif

    struct fiber* fiber = tlp->next_free_fiber;
    if (unlikely(fiber == NULL)) {
        fiber = fiber_create_from_heap();
        if (fiber == NULL) return NULL;
    } else {
        tlp->next_free_fiber = fiber->next;
    }

    fiber_init_struct(fiber, fiber_exit, func, param);

    return fiber;
}

__attribute__((noinline))
static void* fiber_scheduler(struct thread* thread) {
    thread_context = thread;
    for (;;) {
        struct fiber* fiber = queue_pop();
        if (fiber == NULL) break;

        fiber_swap_context(&fiber->source, &fiber->target);

        if (fiber->exit_flag) {
            struct fiber* exit_listener = fiber->exit_listener;
            fiber_free(fiber);

            if (exit_listener != NULL) {
                if (atomic_fetch_sub(&exit_listener->join_count, 1) == 1) {
                    fiber_schedule(exit_listener);
                }
            }
        }
    }
    return NULL;
}

void fiber_init(void(*init_func)(void*), void* init_param) {
    THREAD_COUNT = atoi(getenv("THREAD_COUNT") ?: "") ?: sysconf(_SC_NPROCESSORS_ONLN);
    if (THREAD_COUNT <= 0)
        ERROR("sysconf(_SC_NPROCESSORS_ONLN)");
    DEBUG("THREAD_COUNT=%d\n", THREAD_COUNT);

    PAGE_SIZE = getpagesize();
    if (PAGE_SIZE <= 0)
        ERROR("Page size unknown\n");
    DEBUG("PAGE_SIZE=%d\n", PAGE_SIZE);

    TRIM_COUNT = atoi(getenv("TRIM_COUNT") ?: "") ?: 10000;
    if (TRIM_COUNT <= 0)
        ERROR("Invalid trim count\n");
    DEBUG("TRIM_COUNT=%d\n", TRIM_COUNT);

    FIBER_SIZE = atoi(getenv("FIBER_SIZE") ?: "") ?: (256 * 1024);
    if (FIBER_SIZE < PAGE_SIZE * 2)
        ERROR("FIBER_SIZE must be >= %uld\n", PAGE_SIZE * 2);
    DEBUG("FIBER_SIZE=%ld\n", FIBER_SIZE);

    MAX_FIBER_COUNT = atoi(getenv("MAX_FIBER_COUNT") ?: "") ?: 10000;
    if (MAX_FIBER_COUNT <= 0 )
        ERROR("MAX_FIBER_COUNT must be > 0\n");
    DEBUG("MAX_FIBER_COUNT=%d\n", MAX_FIBER_COUNT);
    fiber_count = MAX_FIBER_COUNT;

    // Round up to the nearest whole page size.
    FIBER_SIZE = (FIBER_SIZE + PAGE_SIZE - 1) / FIBER_SIZE * FIBER_SIZE;

    // Calculate 2^n size so that we can mmap enough memory to ensure alignment of the tail.
    FIBER_SIZE_ROUNDUP = 1ul << __builtin_ctz(FIBER_SIZE);
    if (FIBER_SIZE_ROUNDUP < FIBER_SIZE)
        FIBER_SIZE_ROUNDUP *= 2;

    threads = malloc(sizeof(struct thread) * THREAD_COUNT);
    if (threads == NULL)
        ERROR("Failed to allocate threads array\n");
    for (int thread_index = 0; thread_index < THREAD_COUNT; ++thread_index) {
        threads[thread_index].next_free_fiber = NULL;
        pthread_create(
                &threads[thread_index].thread_handle, NULL,
                (void*(*)(void*))fiber_scheduler, &threads[thread_index]);
    }

    queue_init(MAX_FIBER_COUNT);

    struct fiber* fiber = fiber_create_from_heap();
#ifndef NDEBUG
    if (fiber == NULL)
        ERROR("This is embarrassing. fiber_create_from_heap() returned NULL during startup.\n");
#endif

    fiber_init_struct(fiber, fiber_terminate, init_func, init_param);

    queue_push(fiber, fiber->priority);
}

__attribute__((noinline))
struct fiber* fiber_self() {
    uintptr_t mask = FIBER_SIZE_ROUNDUP - 1;
    struct fiber* fiber = (struct fiber*)((((uintptr_t)&mask) & ~mask) + FIBER_SIZE_ROUNDUP - sizeof(struct fiber));
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


void fiber_parallel(void* param, void(**funcs)(void*), size_t count) {
#ifndef NDEBUG
    if (unlikely(thread_context == NULL))
        ERROR("fiber_schedule_and_join can only be called from a fiber context\n");
#endif

    struct fiber* self = fiber_self();
    self->join_count = count;

    if (count > 0) {
        for (size_t index = 0; index < count; ++index) {
            void(*func)(void*) = funcs[index];
            struct fiber* fiber = fiber_create(func, param);

            if (unlikely(fiber == NULL)) {
                func(param); // Just do it immediately on this thread
                if (atomic_fetch_sub(&self->join_count, 1) == 1) {
                    // We must be at the end of the loop
                    // And this thread is the final one to bring count to zero
                    // Instead of fiber_schedule, we'll skip fiber_yield and carry on
                    return;
                }
            } else {
                fiber->exit_listener = self;
                fiber_schedule(fiber);
            }
        }
    }

    fiber_yield();
}



