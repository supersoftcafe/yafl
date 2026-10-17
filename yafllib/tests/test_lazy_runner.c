// Deterministic test: exactly one caller of lazy_thunk_enqueue runs the
// initialiser — the one that found the waiter chain EMPTY — even when the
// runner already in flight drains the chain between the enqueue's CAS and its
// return.
//
//   1. W1 enqueues on an empty chain: it is the runner (1).
//   2. W2 enqueues behind W1. Inside the window after its CAS (the probe,
//      compiled into this target alone: YAFL_LAZY_RACE_PROBE), the chain is
//      drained, as the runner does when the initialiser finishes; the drain
//      clears each waiter's next as it completes it.
//   3. W2 must be a waiter (0). Deciding from a re-read of W2->next instead
//      of from the head the CAS replaced sees NULL and makes W2 a second
//      runner, which would run the initialiser again through the closure the
//      first run has cleared.

#include "../yafl.h"
#include <stdio.h>
#include <stdlib.h>

static object_t*                _flag[1];   // a global lazy stub's flag: a declared root
static roots_declaration_func_t _prev;
static void _decl(void(*declare)(object_t**)) { _prev(declare); declare(&_flag[0]); }

static bool  g_armed;
static int   g_drained;
static fun_t _exit_cont;

void lazy_test_race_probe(object_t* flag_field) {
    if (!g_armed) return;
    g_armed = false;
    lazy_drain_waiters(flag_field);   // the runner finishing, inside the window
    g_drained = 1;
}

static void fail(const char* what, int got) {
    fprintf(stderr, "test_lazy_runner: FAIL %s (got %d)\n", what, got);
    fflush(stderr);
    abort();
}

static void _entrypoint(object_t* self, fun_t cont) {
    (void)self; _exit_cont = cont;
    object_t* w1 = task_create(NULL);
    int r1 = lazy_thunk_enqueue((object_t*)&_flag[0], w1);
    if (r1 != 1) fail("the first enqueue on an empty chain is not the runner", r1);

    object_t* w2 = task_create(NULL);
    g_armed = true;
    int r2 = lazy_thunk_enqueue((object_t*)&_flag[0], w2);
    if (!g_drained) fail("the probe did not run", 0);
    if (r2 != 0) fail("a waiter became a second runner after the chain was drained", r2);

    printf("test_lazy_runner: OK\n");
    fflush(stdout);
    ((void(*)(object_t*,object_t*))_exit_cont.f)(_exit_cont.o, integer_from_int32(0));
}

int main(void) {
    _prev = add_roots_declaration_func(_decl);
    thread_start(_entrypoint);
    return 0;
}
