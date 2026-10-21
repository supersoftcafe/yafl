
#include "yafl.h"

#define TASK_PENDING  0
#define TASK_CALLBACK 1
#define TASK_COMPLETE 2
// Complete, and registering a continuation posts it to ANOTHER worker's queue
// (future_yield) instead of this one's.
#define TASK_YIELDED  3

VTABLE_DECLARE_STRUCT(task_vtable, 0);
EXPORT struct task_vtable TASK_VTABLE = {
    .object_size              = sizeof(task_t),
    .array_el_size            = 0,
    .object_pointer_locations = maskof(task_t, .callback.o)
                              | maskof(task_t, .next),
    .array_el_pointer_locations = 0,
    .functions_mask           = 0,
    .array_len_offset         = 0,
    .is_mutable               = 1,
    .name                     = "task",
    .implements_array         = VTABLE_IMPLEMENTS(0),
};

EXPORT struct task_vtable TASK_OBJ_VTABLE = {
    .object_size              = sizeof(task_obj_t),
    .array_el_size            = 0,
    .object_pointer_locations = maskof(task_obj_t, .callback.o)
                              | maskof(task_obj_t, .next)
                              | maskof(task_obj_t, .result),
    .array_el_pointer_locations = 0,
    .functions_mask           = 0,
    .array_len_offset         = 0,
    .is_mutable               = 1,
    .name                     = "task_obj",
    .implements_array         = VTABLE_IMPLEMENTS(0),
};

// A String result: its GC word is result.head.
EXPORT struct task_vtable TASK_STR_VTABLE = {
    .object_size              = sizeof(task_str_t),
    .array_el_size            = 0,
    .object_pointer_locations = maskof(task_str_t, .callback.o)
                              | maskof(task_str_t, .next)
                              | maskof(task_str_t, .result.head),
    .array_el_pointer_locations = 0,
    .functions_mask           = 0,
    .array_len_offset         = 0,
    .is_mutable               = 1,
    .name                     = "task_str",
    .implements_array         = VTABLE_IMPLEMENTS(0),
};

// Compiler-facing vtable aliases (obj_task, obj_task_obj, obj_task_str) are defined as
// macros in yafl.h so they expand to constant expressions usable inside
// VTABLE_IMPLEMENTS' static initializer.


// Fire a queued task's callback exactly once. This is the WORKER LOOP's
// entry — continuations only ever run from a clean dispatch frame. Keying on
// callback presence (not task state) lets one queue carry both spawned tasks
// (callback = the body) and deferred completions (state already COMPLETE).
HIDDEN void _task_fire(void* self) {
    task_t* task = (task_t*)self;
    atomic_store(&task->state, TASK_COMPLETE);
    fun_t cb = task->callback;
    if (cb.f) {
        // Single-fire: clear the stored copy before invoking. A fired
        // callback left in place RETAINS the whole continuation graph (the
        // state object, its captured locals, and through them every
        // intermediate structure the suspended function ever held —
        // observed: a returned function's state object keeping two
        // 480k-cell lists alive for the process lifetime).
        GC_STORE_MUTABLE_IN(task, task->callback, 1, (fun_t){ NULL, NULL });
        ((object_t*(*)(object_t*,object_t*))cb.f)(cb.o, (object_t*)task);
    }
}


// All task_t subclasses must initialise through here to ensure thread_id is set.
EXPORT object_t* task_init(object_t* self) {
    task_t* task = (task_t*)self;
    atomic_store(&task->state, TASK_PENDING);
    task->thread_id = thread_current_id();
    atomic_store(&task->next, (task_t*)NULL);
    return NULL;
}


EXPORT object_t* task_create(object_t* self) {
    (void)self;
    object_t* task = object_create((vtable_t*)&TASK_VTABLE);
    task_init(task);
    return task;
}


EXPORT object_t* task_obj_create(object_t* self) {
    (void)self;
    task_obj_t* task = (task_obj_t*)object_create((vtable_t*)&TASK_OBJ_VTABLE);
    task_init((object_t*)task);
    GC_STORE_MUTABLE_IN(task, task->result, 1, NULL);   // object_create zeroed it; mark-old is a no-op but keeps every store uniform
    return (object_t*)task;
}


EXPORT object_t* task_str_create(object_t* self) {
    (void)self;
    task_str_t* task = (task_str_t*)object_create((vtable_t*)&TASK_STR_VTABLE);
    task_init((object_t*)task);   // object_create zeroed result: None
    return (object_t*)task;
}


EXPORT object_t* task_complete(object_t* self) {
    task_t* task = (task_t*)self;
    int32_t old = atomic_exchange(&task->state, TASK_COMPLETE);
    // DEFERRED resumption: the continuation is queued, never called nested
    // inside the completer's frame. A synchronous cascade keeps the entire
    // await-resumption ancestry alive on the C stack — every ancestor's
    // callback locals (state objects, and everything they captured) become
    // conservatively pinned for as long as the continuation runs, and a
    // deep chain can overflow the stack outright. Suspensions go through
    // the queue; so do resumptions. (Exchange BEFORE post closes the lost
    // wake-up race the old load-then-store deferred path had: an awaiter
    // registering concurrently either sees COMPLETE and posts itself, or
    // its CALLBACK state is seen here.)
    if (old == TASK_CALLBACK)
        thread_work_post(self);
    return NULL;
}


// Like task_complete, but if a callback is registered, queue the task for
// the worker loop to fire instead of running it inline. The caller's frame
// returns immediately; the callback runs in a clean stack later. Use this
// when finishing a task inside another callback — synchronous task_complete
// would cascade through the callback chain and overflow the C stack on
// deep trampoline recursion.
EXPORT object_t* task_complete_deferred(object_t* self) {
    return task_complete(self);   // completion always defers now
}


EXPORT object_t* task_on_complete(object_t* self, fun_t callback) {
    task_t* task = (task_t*)self;
    // Publishes the continuation: once the caller suspends, the task's
    // callback.o is the only reference to that continuation state, and the
    // task may be one this cycle never scans (born after its thread's root scan).
    GC_STORE_PUBLISH_IN(task, task->callback, 1, callback);
    int32_t expected = TASK_PENDING;
    if (atomic_compare_exchange_strong(&task->state, &expected, TASK_CALLBACK))
        return NULL;
    // Task already complete: defer all the same — running the continuation
    // here would nest it in the REGISTRANT's frames with the same pinned
    // ancestry problem as a completion-side cascade.
    if (expected == TASK_YIELDED) {
        atomic_store(&task->state, TASK_COMPLETE);
        thread_work_post_parallel(self);
    } else {
        thread_work_post(self);
    }
    return NULL;
}


// A `[future]` function's first step: hand the rest of the body to a worker.
// The returned task is already complete, so the caller suspends on it and
// returns its own task; registering the continuation (task_on_complete) is
// what posts it, round-robin like any spawn — idle workers sleep on their own
// queues, so this thread's queue would wake nobody. Registering BEFORE posting
// is the point: a task posted first could fire while its continuation is
// still being stored, and run it twice. When the pool is not accepting, the
// body runs in place: NULL is an ordinary sync None.
EXPORT object_t* future_yield(object_t* self) {
    (void)self;
    if (!thread_work_accepting())
        return NULL;
    object_t* task = task_create(NULL);
    atomic_store(&((task_t*)task)->state, TASK_YIELDED);
    return (object_t*)((uintptr_t)task | PTR_TAG_TASK);
}
