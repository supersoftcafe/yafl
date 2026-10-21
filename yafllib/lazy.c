
#include "yafl.h"


// The gate every compiler-emitted `lazy_fetch$<T>` takes before running a
// stub's initialiser (the flag's states are in yafl.h, lazy_thunk_t). Both are
// foreign functions to the compilers: lazy_acquire may suspend — its None result
// is the task pointer alone, NULL when the caller may go on — and lazy_release
// is [sync].

#define LAZY_DONE ((object_t*)1)

EXPORT bool lazy_enqueue_waiter(object_t* flag_field, object_t* waiter_obj) {
    _Atomic(object_t*)* flag = (_Atomic(object_t*)*)flag_field;
    task_t* waiter = (task_t*)waiter_obj;
    object_t* expected = atomic_load(flag);
    do {
        if (expected == NULL || expected == LAZY_DONE)
            return false;
        // `waiter` is not yet visible, so its link is a plain store; what it
        // links, the head the CAS displaces, GC_CAS shades before the CAS:
        // the displaced head's only edge moves from the stub's flag — which
        // this cycle may already have scanned — onto `waiter->next`, and
        // `waiter` may already be marked without ever being SCANNED
        // (allocated black, or just published). GC_CAS also escapes `waiter`
        // from this thread's nursery before it is visible, and publishes a
        // GLOBAL stub's flag, a declared root, once the CAS lands: the
        // caller keeps only the tagged task, which the collector does not
        // see, leaving the flag the waiter's only reference (test_gc_lazy_step).
        atomic_store(&waiter->next, expected == LAZY_HELD ? NULL : (task_t*)expected);
    } while (!GC_CAS(*flag, &expected, waiter_obj));
#ifdef YAFL_LAZY_RACE_PROBE
    // Test-only hook (tests/test_lazy_runner.c), compiled into that target
    // alone: called once `waiter` is published, where the holder can release
    // — completing it — before this caller returns.
    { extern void lazy_test_race_probe(object_t*); lazy_test_race_probe(flag_field); }
#endif
    return true;
}


EXPORT object_t* lazy_acquire(object_t* self, object_t* flag_field) {
    (void)self;
    _Atomic(object_t*)* flag = (_Atomic(object_t*)*)flag_field;
    object_t* waiter = NULL;
    for (;;) {
        object_t* expected = atomic_load(flag);
        if (expected == LAZY_DONE)
            return NULL;
        // Free: this caller holds the gate and runs the initialiser. The
        // marker is a scalar, so the CAS owes the collector nothing.
        if (expected == NULL) {
            if (atomic_compare_exchange_weak(flag, &expected, LAZY_HELD))
                return NULL;
            continue;
        }
        // Held: queue a waiter and suspend on it. Allocated once, on the first
        // pass that needs it; one left over when the gate completes meanwhile
        // is garbage like any other. Completed already, by a release since the
        // enqueue, its continuation is simply queued at once (task_on_complete).
        if (waiter == NULL)
            waiter = task_create(NULL);
        if (lazy_enqueue_waiter(flag_field, waiter))
            return (object_t*)((uintptr_t)waiter | PTR_TAG_TASK);
    }
}


EXPORT object_t* lazy_release(object_t* self, object_t* flag_field) {
    (void)self;
    // The value is stored before this exchange, which publishes it: a reader
    // that sees LAZY_DONE (lazy_global_init_complete, with its acquire fence)
    // reads the value after. Both exchanges DELETE a reference — the stub's
    // edge to the chain, a waiter's edge to the next — so both owe the
    // snapshot barrier, as any overwrite does: during a cycle, a chain
    // reachable at the snapshot through a stub not yet scanned would otherwise
    // live on only in this thread's locals, which its root scan may already
    // have passed, and be freed mid-walk. GC_EXCHANGE pays it.
    object_t* head = GC_EXCHANGE(*(_Atomic(object_t*)*)flag_field, LAZY_DONE);
    task_t*   w    = head == LAZY_HELD ? NULL : (task_t*)head;
    while (w) {
        task_t* next = (task_t*)GC_EXCHANGE(w->next, NULL);
        task_complete_deferred((object_t*)w);
        w = next;
    }
    return NULL;
}


// `[future]` bind-time spawn: post a worker task whose callback is the
// compiler-emitted per-type runner (`future_run$<T>`) bound to the stub —
// the runner calls `lazy_fetch$<T>` and discards, so taking the gate
// evaluates the thunk on the worker and releases the waiters, while finding
// it held or done is harmless (the readers own the protocol either way).
// Round-robin across workers like __parallel__, since the point is running
// elsewhere. When the
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
