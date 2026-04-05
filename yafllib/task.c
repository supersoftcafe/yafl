
#include "yafl.h"

#define TASK_PENDING  0
#define TASK_CALLBACK 1
#define TASK_COMPLETE 2

VTABLE_DECLARE_STRUCT(task_vtable, 0);
EXPORT struct task_vtable TASK_VTABLE = {
    .object_size              = sizeof(task_t),
    .array_el_size            = 0,
    .object_pointer_locations = maskof(task_t, .callback.o),
    .array_el_pointer_locations = 0,
    .functions_mask           = 0,
    .array_len_offset         = 0,
    .is_mutable               = 1,
    .name                     = "task",
    .implements_array         = VTABLE_IMPLEMENTS(0),
};


HIDDEN void _task_call_complete(void* self) {
    task_t* task = (task_t*)self;
    fun_t cb = task->callback;
    ((object_t*(*)(object_t*,object_t*))cb.f)(cb.o, (object_t*)task);
}


EXPORT object_t* task_create(void* self) {
    task_t* task = (task_t*)object_create((vtable_t*)&TASK_VTABLE);
    atomic_store(&task->state, TASK_PENDING);
    return (object_t*)task;
}


EXPORT object_t* task_complete(void* self) {
    task_t* task = (task_t*)self;
    int_fast32_t old = atomic_exchange(&task->state, TASK_COMPLETE);
    if (old == TASK_CALLBACK)
        thread_work_post_io(thread_work_prepare((fun_t){.f=_task_call_complete, .o=task}));
    return NULL;
}


EXPORT object_t* task_on_complete(void* self, fun_t callback) {
    task_t* task = (task_t*)self;
    task->callback = callback;
    int_fast32_t expected = TASK_PENDING;
    if (atomic_compare_exchange_strong(&task->state, &expected, TASK_CALLBACK))
        return NULL;
    return ((object_t*(*)(object_t*,object_t*))callback.f)(callback.o, (object_t*)task);
}
