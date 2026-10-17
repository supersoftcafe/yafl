
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
    _Atomic(object_t*)* flag = (_Atomic(object_t*)*)flag_field;
    task_t* waiter = (task_t*)waiter_obj;
    object_t* expected = atomic_load(flag);
    do {
        if (expected == (object_t*)1) return 2;
        // `waiter` is not yet visible, so its link is a plain store; what it
        // links, the head the CAS displaces, GC_CAS shades before the CAS:
        // the displaced head's only edge moves from the stub's flag — which
        // this cycle may already have scanned — onto `waiter->next`, and
        // `waiter` may already be marked without ever being SCANNED
        // (allocated black, or just published). GC_CAS also escapes `waiter`
        // from this thread's nursery before it is visible, and publishes a
        // GLOBAL stub's flag, a declared root, once the CAS lands: when this
        // thread wins the init race the caller drops `waiter` at once, leaving
        // the flag its only reference (test_gc_lazy_step).
        atomic_store(&waiter->next, (task_t*)expected);
    } while (!GC_CAS(*flag, &expected, waiter_obj));
#ifdef YAFL_LAZY_RACE_PROBE
    // Test-only hook (tests/test_lazy_runner.c), compiled into that target
    // alone: called once `waiter` is published, where the runner already in
    // flight can drain the chain before this caller decides whether it runs.
    { extern void lazy_test_race_probe(object_t*); lazy_test_race_probe(flag_field); }
#endif
    // The runner is whoever found the chain EMPTY — `expected`, the head the
    // CAS replaced. Not a re-read of waiter->next: once the CAS publishes
    // `waiter`, the runner already in flight can finish and drain the chain,
    // and the drain clears each waiter's next as it completes it
    // (lazy_chain_step). A re-read then sees NULL, and this caller — already
    // completed as a waiter — would run the initialiser a second time, through
    // the closure the first run has cleared.
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
