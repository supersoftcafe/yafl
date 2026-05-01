#include "yafl.h"

EXPORT object_t* parallel_join_decrement(void* par_task_vp) {
    task_par_base_t* par = (task_par_base_t*)par_task_vp;
    if (atomic_fetch_sub(&par->remaining, 1) == 1)
        task_complete(par);
    return NULL;
}
