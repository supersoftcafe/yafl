// test_gc_stale_mark: a remote conservative mark landing on an object that a
// thread-local nursery has just found dead.
//
// The CHURNER (thread 0) keeps a small ring of live strings ON ITS STACK (so
// the conservative scan keeps them, and dropping one is a plain store that
// does not escape it) and keeps replacing them, so its nursery pages hold live and dead objects side by
// side and survive collection with dead slots struck out of `objects`. It
// leaks the address of each string it drops into a plain integer (NOT a
// root). The HOLDER (another worker) keeps copying that address into a stack
// variable — exactly what a stale stack word is — and passes safe points, so
// global root scans resolve it and mark the object in the churner's nursery.
//
// When that mark lands after the churner's collection has read the page's
// marks, the slot is struck while carrying a mark bit. The global collector
// must treat such a bit as meaningless: scanning the slot (or letting the
// prune turn it back into an object) reads a dead object — under
// YAFL_GC_POISON, a 0x42-filled one, which the dangle check aborts on.

#include "../yafl.h"
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>

#ifndef STALE_ITERATIONS
#define STALE_ITERATIONS 400000
#endif
#define RING 64

static _Atomic(uintptr_t) _leak;               // NOT a root: a stale word source
static _Atomic(bool) _done;
static fun_t _exit_cont;

static object_t *_make_string(int i) {
    static const char PAD[] = "stale-mark-test-padding-0123456789abcdefghijklmnop";
    int len = 16 + (i & 15);
    return str_from_bytes((const uint8_t *)PAD, len).head;
}

static object_t *_holder(object_t *self, object_t *task) {
    (void)self; (void)task;
    while (!atomic_load_explicit(&_done, memory_order_relaxed)) {
        // A stack slot the conservative scan will see; never dereferenced.
        object_t * volatile stale = (object_t *)atomic_load_explicit(&_leak, memory_order_relaxed);
        for (int spin = 0; spin < 64; ++spin) {
            GC_SAFE_POINT();
            __asm__ volatile("" ::: "memory");
        }
        (void)stale;
    }
    return NULL;
}

static void _entrypoint(object_t *self, fun_t continuation) {
    (void)self;
    _exit_cont = continuation;

    task_t *holder = (task_t *)task_create(NULL);
    task_on_complete((object_t *)holder, (fun_t){ .f = (void *)_holder, .o = NULL });
    thread_work_post_parallel((object_t *)holder);

    object_t * volatile ring[RING] = { 0 };
    uint32_t seed = 12345;
    for (int i = 0; i < STALE_ITERATIONS; ++i) {
        seed = seed * 1103515245u + 12345u;
        unsigned slot = (seed >> 16) % RING;
        object_t *dropped = ring[slot];
        ring[slot] = _make_string(i);
        if (dropped) atomic_store_explicit(&_leak, (uintptr_t)dropped, memory_order_relaxed);
        _make_string(i + 1);                    // plain garbage between live ones
        GC_SAFE_POINT();
    }
    atomic_store(&_done, true);
    printf("test_gc_stale_mark: OK\n");
    fflush(stdout);
    ((void (*)(object_t *, object_t *))_exit_cont.f)(_exit_cont.o, integer_from_int32(0));
}

int main(void) {
    setenv("YAFL_THREADS", "2", 0);
    thread_start(_entrypoint);
    return 0;
}
