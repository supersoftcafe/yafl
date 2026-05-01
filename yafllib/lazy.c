
#include "yafl.h"




HIDDEN void _lazy_global_init_continue(object_t* self, int32_t ignore) {
    (void)ignore;
    // Untag flag_ptr
    _Atomic(task_t*)* flag_ptr = (_Atomic(task_t*)*)((intptr_t)self &~ 1);

    // Atomically swap the waiting list with the sentinel (1), indicating init is complete.
    task_t* expected = atomic_load(flag_ptr);
    task_t* initial;

    do {
        initial = expected;
    } while (atomic_compare_exchange_weak(flag_ptr, &expected, (task_t*)1));

    // Resume each waiter on its originating thread.
    while (initial != NULL) {
        task_t* next = atomic_load(&initial->next);
        atomic_store(&initial->next, (task_t*)NULL);
        thread_work_post(initial);
        initial = next;
    }
}

EXPORT void lazy_global_init(object_t** self, object_t* _flag_ptr, fun_t init, fun_t callback) {
    (void)self;
    _Atomic(task_t*)* flag_ptr = (_Atomic(task_t*)*)_flag_ptr;
    task_t* expected = atomic_load(flag_ptr);

    // Create a task that will resume with `callback` once init is done.
    task_t* desired = (task_t*)task_create(NULL);
    task_on_complete(desired, callback);   // PENDING → CALLBACK

    do {
        if (expected == (task_t*)1) {
            thread_work_post(desired);   // already initialized; resume immediately
            return;
        }
        atomic_store(&desired->next, expected);
    } while (atomic_compare_exchange_weak(flag_ptr, &expected, desired));

    if (atomic_load(&desired->next) == NULL) {
        // This thread won the initialisation contest.  Tag flag_ptr so the GC
        // ignores it while the init callback is outstanding.
        ((void(*)(void*,fun_t))init.f)(init.o, (fun_t){.f=_lazy_global_init_continue,.o=(void*)(1|(intptr_t)flag_ptr)});
    }
}
