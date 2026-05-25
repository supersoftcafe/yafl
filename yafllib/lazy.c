
#include "yafl.h"


// Drain the waiter chain after init completes.  Each waiter is a real
// task_t whose awaiter registered task_on_complete; task_complete_deferred
// posts to a worker so the awaiter's continuation runs in a fresh stack
// frame, avoiding a deep cascade across many concurrent waiters.
HIDDEN void _lazy_global_init_continue(object_t* self, int32_t ignore) {
    (void)ignore;
    _Atomic(task_t*)* flag_ptr = (_Atomic(task_t*)*)((intptr_t)self & ~1);

    task_t* head = atomic_exchange(flag_ptr, (task_t*)1);

    while (head) {
        task_t* next = atomic_load(&head->next);
        atomic_store(&head->next, NULL);
        task_complete_deferred((object_t*)head);
        head = next;
    }
}


EXPORT object_t* lazy_global_init(object_t** self, object_t* _flag_ptr, fun_t init) {
    (void)self;
    _Atomic(task_t*)* flag_ptr = (_Atomic(task_t*)*)_flag_ptr;

    task_t* waiter = (task_t*)task_create(NULL);
    task_t* expected = atomic_load(flag_ptr);

    do {
        if (expected == (task_t*)1) {
            // Already initialised — resolve waiter immediately; the awaiter's
            // task_on_complete will detect TASK_COMPLETE and fire inline.
            task_complete((object_t*)waiter);
            return (object_t*)((uintptr_t)waiter | PTR_TAG_TASK);
        }
        atomic_store(&waiter->next, expected);
    } while (!atomic_compare_exchange_weak(flag_ptr, &expected, waiter));

    // We were appended.  If we replaced NULL, we won the init race.
    if (atomic_load(&waiter->next) == NULL) {
        // Invoke init under the YAFL async ABI: it returns object_t*.
        // PTR_IS_TASK true → init suspended; chain our continue.
        // PTR_IS_TASK false → init completed inline; fire continue now.
        object_t* result = ((object_t*(*)(object_t*))init.f)(init.o);
        object_t* tagged_flag = (object_t*)(1 | (intptr_t)flag_ptr);
        if (PTR_IS_TASK(result)) {
            task_t* init_task = (task_t*)TASK_UNTAG(result);
            task_on_complete((object_t*)init_task,
                             (fun_t){.f = (void*)_lazy_global_init_continue,
                                     .o = tagged_flag});
        } else {
            _lazy_global_init_continue(tagged_flag, 0);
        }
    }

    return (object_t*)((uintptr_t)waiter | PTR_TAG_TASK);
}
