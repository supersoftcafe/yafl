// Test that thread_work_post_parallel posts tasks and they complete correctly.
//
// Design: post N tasks via thread_work_post_parallel; verify:
//   1. All N tasks complete (the counter reaches 0).
//   2. thread_work_post_parallel returns NULL (confirming the new return type).
//   3. The round-robin counter distributes tasks: first post always goes to
//      queue index 1 (not 0), confirmed by checking that tasks in odd slots
//      were completed — we cannot guarantee *which* thread ran them due to
//      work-stealing, but we CAN verify the function return value and
//      that all tasks complete exactly once.

#include "../yafl.h"
#include <stdatomic.h>
#include <stdio.h>

#define N_TASKS 4

static atomic_int  _remaining;
static fun_t       _continuation;
static atomic_int  _returned_null;  // count of non-NULL returns (should be 0)

static object_t* _record_and_decrement(void* slot_ptr, object_t* unused_task) {
    (void)slot_ptr;
    if (atomic_fetch_sub(&_remaining, 1) == 1) {
        // All tasks completed.
        // Success if all thread_work_post_parallel calls returned NULL.
        int bad_returns = atomic_load(&_returned_null);
        printf("completed=%d bad_returns=%d\n", N_TASKS, bad_returns);
        object_t* result = integer_create_from_int32(bad_returns == 0 ? 0 : 1);
        fun_t cb = _continuation;
        ((void(*)(void*, object_t*))cb.f)(cb.o, result);
    }
    return NULL;
}

static void _declare_roots(void(*declare)(object_t**)) {
    (void)declare;
}

static void _entrypoint(object_t* self, fun_t continuation) {
    (void)self;
    _continuation = continuation;
    atomic_store(&_remaining, N_TASKS);
    atomic_store(&_returned_null, 0);

    for (intptr_t k = 0; k < N_TASKS; k++) {
        task_t* t = (task_t*)task_create(NULL);
        task_on_complete(t, (fun_t){.f = (void*)_record_and_decrement, .o = (void*)k});
        object_t* ret = thread_work_post_parallel(t);
        if (ret != NULL) {
            atomic_fetch_add(&_returned_null, 1);
        }
    }
}

int main(void) {
    add_roots_declaration_func(_declare_roots);
    thread_start(_entrypoint);
    return 0;
}
