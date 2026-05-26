
#include "yafl.h"


// Atomic chain helpers shared by every compiler-emitted `lazy_fetch$<T>`.
// Per-IR-type chain drain is compiler-generated (see
// lowering/lazy_thunks.py); the runtime side is just the two atomic
// primitives `lazy_chain_swap_sentinel` and `lazy_chain_step` in
// yafl.h, plus this no-result drain (kept for symmetry — the lazy
// framework itself uses the per-type drain).

EXPORT object_t* lazy_drain_waiters(object_t* flag_field) {
    _Atomic(task_t*)* flag = (_Atomic(task_t*)*)flag_field;
    task_t* head = atomic_exchange(flag, (task_t*)1);
    while (head) {
        task_t* next = atomic_load(&head->next);
        atomic_store(&head->next, NULL);
        task_complete_deferred((object_t*)head);
        head = next;
    }
    return NULL;
}


EXPORT int32_t lazy_thunk_enqueue(object_t* flag_field, object_t* waiter_obj) {
    _Atomic(task_t*)* flag = (_Atomic(task_t*)*)flag_field;
    task_t* waiter = (task_t*)waiter_obj;
    task_t* expected = atomic_load(flag);
    do {
        if (expected == (task_t*)1) return 2;
        atomic_store(&waiter->next, expected);
    } while (!atomic_compare_exchange_weak(flag, &expected, waiter));
    return (atomic_load(&waiter->next) == NULL) ? 1 : 0;
}
