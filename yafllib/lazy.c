
#include "common.h"
#include "yafl.h"





HIDDEN void _lazy_global_init_continue(object_t* self, int32_t ignore) {
    // Untag flag_ptr
    _Atomic(worker_node_t*)* flag_ptr = (_Atomic(worker_node_t*)*)((intptr_t)self &~ 1);

    // Take the whole list of listers as a single atomic op and replace with a flag to indiciate initialisation complete.
    // That flag looks like a tagged pointer to the GC so it'll ignore it.
    worker_node_t* expected = atomic_load(flag_ptr);
    worker_node_t* initial;

    do {
        initial = expected;
    } while (atomic_compare_exchange_weak(flag_ptr, &expected, (worker_node_t*)1));

    object_gc_mark_as_seen((object_t*)initial); // Because we're mutating, we need to be GC aware

    // Notify all listeners
    while (initial != NULL) {
        worker_node_t* next = initial->next;
        object_gc_mark_as_seen((object_t*)next); // Because we're mutating, we need to be GC aware
        initial->next = (worker_node_t*)0;

        thread_work_post_fast(initial);
        initial = next;
    }
}

EXPORT void lazy_global_init(object_t** self, object_t* _flag_ptr, fun_t init, fun_t callback) {
    _Atomic(worker_node_t*)* flag_ptr = (_Atomic(worker_node_t*)*)_flag_ptr;
    worker_node_t* expected = atomic_load(flag_ptr);
    worker_node_t* desired = thread_work_prepare(callback);

    do {
        if (expected == (worker_node_t*)1) {
            thread_work_post_fast(desired);
            return; // Some other thread fully initialised it before we got started
        }
        desired->next = expected;
    } while (atomic_compare_exchange_weak(flag_ptr, &expected, desired));

    if (desired->next == NULL) {
        // Our thread has won the contest to do the initialisation.
        // flag_ptr will be tagged so that the garbage collector will ignore it.
        ((void(*)(void*,fun_t))init.f)(init.o, (fun_t){.f=_lazy_global_init_continue,.o=(void*)(1|(intptr_t)flag_ptr)});
    }
}
