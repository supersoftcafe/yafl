
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


EXPORT object_t* task_on_complete(object_t* self, fun_t callback) {
    task_t* task = (task_t*)self;
    task->callback = callback;
    int32_t expected = TASK_PENDING;
    if (atomic_compare_exchange_strong(&task->state, &expected, TASK_CALLBACK))
        return NULL;
    return ((object_t*(*)(object_t*,object_t*))callback.f)(callback.o, (object_t*)task);
}
