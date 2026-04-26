
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

EXPORT struct task_vtable TASK_OBJ_VTABLE = {
    .object_size              = sizeof(task_obj_t),
    .array_el_size            = 0,
    .object_pointer_locations = maskof(task_obj_t, .parent.callback.o)
                              | maskof(task_obj_t, .result),
    .array_el_pointer_locations = 0,
    .functions_mask           = 0,
    .array_len_offset         = 0,
    .is_mutable               = 1,
    .name                     = "task_obj",
    .implements_array         = VTABLE_IMPLEMENTS(0),
};

// Alias exposed under the compiler's naming convention so NewObject("task_obj")
// resolves to our pre-declared vtable at link time.
EXPORT vtable_t* const obj_task_obj = (vtable_t*)&TASK_OBJ_VTABLE;


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
        thread_dispatch_fast((fun_t){.f=_task_call_complete, .o=task});
    return NULL;
}


EXPORT void task_complete_io(void* self, worker_node_t* node) {
    task_t* task = (task_t*)self;
    int_fast32_t old = atomic_exchange(&task->state, TASK_COMPLETE);
    if (old == TASK_CALLBACK) {
        node->action = (fun_t){.f=_task_call_complete, .o=task};
        thread_work_post_io(node);
    }
}


EXPORT object_t* task_on_complete(void* self, fun_t callback) {
    task_t* task = (task_t*)self;
    task->callback = callback;
    int_fast32_t expected = TASK_PENDING;
    if (atomic_compare_exchange_strong(&task->state, &expected, TASK_CALLBACK))
        return NULL;
    return ((object_t*(*)(object_t*,object_t*))callback.f)(callback.o, (object_t*)task);
}
