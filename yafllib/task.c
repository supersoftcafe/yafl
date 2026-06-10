
#include "yafl.h"

#define TASK_PENDING  0
#define TASK_CALLBACK 1
#define TASK_COMPLETE 2

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

// Compiler-facing vtable aliases (obj_task, obj_task_obj) are defined as
// macros in yafl.h so they expand to constant expressions usable inside
// VTABLE_IMPLEMENTS' static initializer.


HIDDEN void _task_call_complete(void* self) {
    task_t* task = (task_t*)self;
    fun_t cb = task->callback;
    ((object_t*(*)(object_t*,object_t*))cb.f)(cb.o, (object_t*)task);
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
    GC_WRITE_BARRIER(task->result, 1);   // object_create zeroed it; mark-old is a no-op but keeps every store uniform
    task->result = NULL;
    return (object_t*)task;
}


EXPORT object_t* task_complete(object_t* self) {
    task_t* task = (task_t*)self;
    int32_t old = atomic_exchange(&task->state, TASK_COMPLETE);
    if (old == TASK_CALLBACK)
        _task_call_complete(task);
    return NULL;
}


// Like task_complete, but if a callback is registered, queue the task for
// the worker loop to fire instead of running it inline. The caller's frame
// returns immediately; the callback runs in a clean stack later. Use this
// when finishing a task inside another callback — synchronous task_complete
// would cascade through the callback chain and overflow the C stack on
// deep trampoline recursion.
EXPORT object_t* task_complete_deferred(object_t* self) {
    task_t* task = (task_t*)self;
    int32_t old = atomic_load(&task->state);
    if (old == TASK_CALLBACK) {
        thread_work_post(self);   // worker will task_complete; that fires the callback
    } else {
        atomic_store(&task->state, TASK_COMPLETE);
    }
    return NULL;
}


EXPORT object_t* task_on_complete(object_t* self, fun_t callback) {
    task_t* task = (task_t*)self;
    // Deletion barrier: mark the callback we are overwriting (provably NULL on a
    // fresh task, but uniform with every other pointer-slot store).
    GC_WRITE_BARRIER(task->callback.o, 1);
    task->callback = callback;
    // Insertion barrier: publish the continuation. Once the caller suspends, the
    // task's callback.o is the only reference to that continuation state, and the
    // caller's stack copy is gone — so an incremental collector that has already
    // scanned the caller's roots must be told about it.
    GC_MARK_SEEN(callback.o);
    int32_t expected = TASK_PENDING;
    if (atomic_compare_exchange_strong(&task->state, &expected, TASK_CALLBACK))
        return NULL;
    return ((object_t*(*)(object_t*,object_t*))callback.f)(callback.o, (object_t*)task);
}
