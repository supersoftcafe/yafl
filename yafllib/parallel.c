#include "yafl.h"

EXPORT object_t* task_par_decrement(object_t* self) {
    task_par_base_t* par = (task_par_base_t*)self;
    if (atomic_fetch_sub(&par->remaining, 1) == 1)
        task_complete(self);
    return NULL;
}
