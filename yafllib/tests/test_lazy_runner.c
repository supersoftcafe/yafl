// Deterministic test of the lazy gate (lazy_acquire / lazy_release): exactly
// one caller holds it and runs the initialiser, and every waiter is completed —
// even one the holder releases between the waiter's enqueue and its return.
//
//   1. A acquires the free gate: it holds it (NULL), the flag is LAZY_HELD.
//   2. B acquires the held gate. Inside the window after its enqueue's CAS
//      (the probe, compiled into this target alone: YAFL_LAZY_RACE_PROBE), A
//      releases, as the holder does when the initialiser finishes.
//   3. B must come back a tagged waiter, completed by that release, and the
//      flag complete. A waiter lost there would leave B suspended for ever; a
//      waiter returned as a holder would run the initialiser a second time,
//      through the closure the first run has cleared.
//   4. C, acquiring the complete gate, goes straight on (NULL).

#include "../yafl.h"
#include <stdio.h>
#include <stdlib.h>


static object_t*                _flag[1];   // a global lazy stub's flag: a declared root
static roots_declaration_func_t _prev;
static void _decl(void(*declare)(object_t**)) { _prev(declare); declare(&_flag[0]); }

static bool  g_armed;
static int   g_released;
static fun_t _exit_cont;

void lazy_test_race_probe(object_t* flag_field) {
    if (!g_armed) return;
    g_armed = false;
    lazy_release(NULL, flag_field);   // the holder finishing, inside the window
    g_released = 1;
}

static void fail(const char* what, uintptr_t got) {
    fprintf(stderr, "test_lazy_runner: FAIL %s (got %#lx)\n", what, (unsigned long)got);
    fflush(stderr);
    abort();
}

static void _entrypoint(object_t* self, fun_t cont) {
    (void)self; _exit_cont = cont;
    object_t* flag = (object_t*)&_flag[0];

    object_t* a = lazy_acquire(NULL, flag);
    if (a != NULL) fail("the first acquire of a free gate does not hold it", (uintptr_t)a);
    if (_flag[0] != LAZY_HELD) fail("a held gate is not LAZY_HELD", (uintptr_t)_flag[0]);

    g_armed = true;
    object_t* b = lazy_acquire(NULL, flag);
    if (!g_released) fail("the probe did not run", 0);
    if (!PTR_IS_TASK(b)) fail("a waiter did not come back a task", (uintptr_t)b);
    task_t* w = (task_t*)TASK_UNTAG(b);
    if (atomic_load(&w->state) != TASK_COMPLETE) fail("the release did not complete the waiter", (uintptr_t)atomic_load(&w->state));
    if (_flag[0] != (object_t*)1) fail("a released gate is not complete", (uintptr_t)_flag[0]);

    object_t* c = lazy_acquire(NULL, flag);
    if (c != NULL) fail("an acquire of a complete gate does not go straight on", (uintptr_t)c);

    printf("test_lazy_runner: OK\n");
    fflush(stdout);
    ((void(*)(object_t*,object_t*))_exit_cont.f)(_exit_cont.o, integer_from_int32(0));
}

int main(void) {
    _prev = add_roots_declaration_func(_decl);
    thread_start(_entrypoint);
    return 0;
}
