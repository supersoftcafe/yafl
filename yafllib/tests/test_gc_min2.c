// Minimal cross-thread GC repro WITHOUT the task/queue machinery.
//
// Hypothesis under test: a "child" object created on thread Y and stored into a
// "holder" object created on thread X can be reclaimed when the holder's page is
// promoted into the scan set in a LATER cycle than the child's — the holder is
// marked (reachable via a root) but not yet SCANNED, so the holder->child edge
// is never traced before the child is pruned.
//
// No tasks, no worker queue. Raw pthreads share holders through rooted slots and
// hang fresh children off them, with throwaway string churn to keep the
// collector busy. Run with YAFL_GC_POISON=1 so a lost child becomes a crash.
//
// NWORKERS controls the number of mutator threads (each does BOTH produce and
// consume), so NWORKERS=1 is a genuine single-thread run:
//   NWORKERS=1 ./test_gc_min2     (expected: clean — holder & child same thread)
//   NWORKERS=4 ./test_gc_min2     (does it crash?)
// All mutator threads register with the GC and barrier before any sharing, so
// the collector knows every thread up-front (as the real worker pool does).

#include "../yafl.h"
#include <pthread.h>
#include <stdatomic.h>
#include <stdio.h>
#include <time.h>
#include <sched.h>

#ifndef NSLOTS
#define NSLOTS 16
#endif
#ifndef RUN_SECONDS
#define RUN_SECONDS 8
#endif
#ifndef MAX_WORKERS_T
#define MAX_WORKERS_T 32
#endif

static int NWORKERS = 4;

// A mutable holder with a single GC pointer field.
struct holder { object_t parent; object_t* child; };
static vtable_t holder_vt = {
    .object_size = sizeof(struct holder), .array_el_size = 0,
    .object_pointer_locations = maskof(struct holder, .child),
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 1, .name = "m2_holder", .implements_array = VTABLE_IMPLEMENTS(0),
};

static object_t*                _slots[NSLOTS];   // shared, rooted
static roots_declaration_func_t _prev;
static void _decl(void(*declare)(object_t**)) {
    _prev(declare);
    for (int i = 0; i < NSLOTS; ++i) declare(&_slots[i]);
}

static const char PAD[64] = "the quick brown fox jumps over the lazy dog 01234567 ABCDEFG";
static void burn(int n) { for (int i = 0; i < n; ++i) { GC_SAFE_POINT(); (void)string_from_bytes((uint8_t*)PAD, 8 + (i & 31)); } }

static atomic_llong _counter;
static atomic_int   _registered;
static atomic_bool  _finished;
static fun_t        _exit_cont;

static void _noop_roots(void* c, void(*d)(object_t**)) { (void)c; (void)d; }

static void* _worker(void* arg) {
    (void)arg;
    gc_declare_thread(_noop_roots, NULL);
    // Barrier: do not touch shared objects until every mutator is registered with
    // the GC, so no thread starts sharing while the collector is unaware of it.
    atomic_fetch_add(&_registered, 1);
    while (atomic_load(&_registered) < NWORKERS) sched_yield();

    while (!atomic_load(&_finished)) {
        GC_SAFE_POINT();   // loop backedge safe-point, as generated YAFL code has
        long long n = atomic_fetch_add(&_counter, 1);
        int sp = (int)(n % NSLOTS);
        int sc = (int)((n + 1) % NSLOTS);

        // PRODUCE: a holder created on THIS thread, published to a rooted slot.
        GC_SAFE_POINT();
        struct holder* h = (struct holder*)object_create(&holder_vt);
        GC_WRITE_BARRIER(_slots[sp], 1);
        _slots[sp] = (object_t*)h;

        // CONSUME: read a holder (maybe created on another thread) and hang a
        // fresh child — created on THIS thread — off it.
        object_t* o = _slots[sc];
        if (o && ((uintptr_t)o & PTR_TAG_MASK) == 0) {
            struct holder* hh = (struct holder*)o;
            GC_SAFE_POINT();
            object_t* c = string_from_bytes((uint8_t*)PAD, 24);   // heap string
            GC_WRITE_BARRIER(hh->child, 1);
            hh->child = c;
        }
        burn(4);
    }
    while (1) sched_yield();   // never return: would dangle this thread's GC info
    return NULL;
}

static void* _watchdog(void* arg) {
    (void)arg;
    struct timespec ts = { RUN_SECONDS, 0 };
    nanosleep(&ts, NULL);
    atomic_store(&_finished, true);
    printf("test_gc_min2: survived %ds, %lld ops, workers=%d\n",
           RUN_SECONDS, (long long)atomic_load(&_counter), NWORKERS);
    fflush(stdout);
    ((void(*)(object_t*,object_t*))_exit_cont.f)(_exit_cont.o, integer_from_int32(0));
    return NULL;
}

static void _entrypoint(object_t* self, fun_t cont) {
    (void)self;
    _exit_cont = cont;
    printf("test_gc_min2: workers=%d slots=%d\n", NWORKERS, NSLOTS);
    fflush(stdout);
    pthread_t wd; pthread_create(&wd, NULL, _watchdog, NULL); pthread_detach(wd);
    for (int i = 0; i < NWORKERS; ++i) {
        pthread_t t; pthread_create(&t, NULL, _worker, (void*)(intptr_t)i); pthread_detach(t);
    }
}

int main(void) {
    const char* e = getenv("NWORKERS");
    if (e && *e) { int n = atoi(e); if (n >= 1 && n <= MAX_WORKERS_T) NWORKERS = n; }
    _prev = add_roots_declaration_func(_decl);
    thread_start(_entrypoint);
    return 0;
}
