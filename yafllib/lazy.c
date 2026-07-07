
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
    // Deletion barrier (same hazard as _queue_try_pop): the CAS moved the
    // displaced head's only edge from the stub's flag — which this cycle may
    // already have scanned — onto `waiter->next`, and `waiter` is a fresh
    // in-window allocation (black: marked but never SCANNED), so the marker
    // would never find the old head down that edge. Tell it directly, or a
    // parked waiter chained behind this one is collected while parked and
    // the drain later walks a freed chain. Exposed by `[future]`'s cross-
    // thread forcers under real GC pressure; latent for concurrent `[lazy]`
    // forcers all along.
    if (expected != NULL) {
        GC_MARK_SEEN((object_t*)expected);
    }
    return (atomic_load(&waiter->next) == NULL) ? 1 : 0;
}


// `[future]` bind-time spawn: post a worker task whose callback is the
// compiler-emitted per-type runner (`future_run$<T>`) bound to the stub —
// the runner calls `lazy_fetch$<T>` and discards, so winning the init race
// evaluates the thunk on the worker and drains waiters, while losing it is
// harmless (the readers own the protocol either way). Round-robin across
// workers like __parallel__, since the point is running elsewhere. When the
// pool is not accepting, do nothing: the binding degrades to exactly [lazy]
// — the first reader evaluates in place.
EXPORT object_t* future_post(fun_t cb) {
    if (thread_work_accepting()) {
        object_t* task = task_create(NULL);
        task_on_complete(task, cb);   // PENDING -> CALLBACK, fired when popped
        thread_work_post_parallel(task);
    }
    return NULL;
}
