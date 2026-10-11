
#include "yafl.h"


// Atomic chain helpers shared by every compiler-emitted `lazy_fetch$<T>`.
// Per-IR-type chain drain is compiler-generated (see
// lowering/lazy_thunks.py); the runtime side is just the two atomic
// primitives `lazy_chain_swap_sentinel` and `lazy_chain_step` in
// yafl.h, plus this no-result drain (kept for symmetry — the lazy
// framework itself uses the per-type drain).

EXPORT object_t* lazy_drain_waiters(object_t* flag_field) {
    task_t* head = (task_t*)lazy_chain_swap_sentinel(flag_field);   // barriered, see yafl.h
    while (head) {
        task_t* next = (task_t*)lazy_chain_step((object_t*)head);
        task_complete_deferred((object_t*)head);
        head = next;
    }
    return NULL;
}


EXPORT int32_t lazy_thunk_enqueue(object_t* flag_field, object_t* waiter_obj) {
    _Atomic(task_t*)* flag = (_Atomic(task_t*)*)flag_field;
    task_t* waiter = (task_t*)waiter_obj;
    // Thread-local nursery: the CAS below publishes `waiter` into a shared
    // chain with no write barrier, so it ESCAPES here, before it is visible.
    if (gc_local_live) gc_local_escape(waiter_obj);
    task_t* expected = atomic_load(flag);
    do {
        if (expected == (task_t*)1) return 2;
        // Deletion barrier (same hazard as _queue_try_pop): the CAS moves the
        // displaced head's only edge from the stub's flag — which this cycle
        // may already have scanned — onto `waiter->next`, and `waiter` may
        // already be marked without ever being SCANNED (allocated black, or
        // just published), so the marker would never find the old head down
        // that edge, and a parked waiter chained behind this one is collected
        // while parked. Shade it BEFORE the CAS, not after: a thread whose
        // root scan is done holds the cycle up for nothing, so preempted
        // between the two it can see the head pruned before it shades it.
        // Exposed by `[future]`'s cross-thread forcers under real GC
        // pressure; latent for concurrent `[lazy]` forcers all along.
        if (expected != NULL) GC_MARK_SEEN((object_t*)expected);
        atomic_store(&waiter->next, expected);
    } while (!atomic_compare_exchange_weak(flag, &expected, waiter));
    // A GLOBAL stub's flag is a declared root, and the CAS was a root store:
    // publish it (see gc_root_publish). When this thread wins the init race
    // the caller drops `waiter` at once, leaving the flag its only reference;
    // a cycle whose snapshot read the flag before the CAS would otherwise
    // never mark it (test_gc_lazy_step). A heap stub's flag needs nothing: the
    // stub is scanned after every thread's take, and finds `waiter` there.
    if (!gc_in_heap(flag_field)) gc_root_publish((object_t**)flag, 1);
    // The runner is whoever found the chain EMPTY — `expected`, the head the
    // CAS replaced. Not a re-read of waiter->next: once the CAS publishes
    // `waiter`, the runner already in flight can finish and drain the chain,
    // and the drain clears each waiter's next as it completes it
    // (lazy_chain_step). A re-read then sees NULL, and this caller — already
    // completed as a waiter — runs the initialiser a second time, through the
    // closure the first run has cleared: a call through NULL (gc_stress's
    // release build on aarch64 segfaulted there about one run in six).
    return expected == NULL ? 1 : 0;
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
