// YAFL_TASK_BACKLOG=0 (set by CMake) closes the pool to new work: nothing is
// ever posted for parallel evaluation, so a [future] runs in place — its
// entry yield answers at once — and a `let [future]` degrades to `[lazy]`.
// The compilers' tests force that path through this variable, so it has to
// mean what it says.

#include "test_framework.h"

static void run_tests(object_t* self, fun_t continuation) {
    (void)self;
    struct test_results r = {0, 0, NULL};
    struct test_results* _r = &r;
    printf("=== backlog zero ===\n");

    printf("  %-50s ", "pool_not_accepting");
    if (!thread_work_accepting()) { printf("OK\n"); r.passed++; }
    else { printf("FAIL\n    thread_work_accepting() with YAFL_TASK_BACKLOG=0\n"); r.failed++; }

    printf("  %-50s ", "future_yield_answers_in_place");
    if (future_yield(NULL) == NULL) { printf("OK\n"); r.passed++; }
    else { printf("FAIL\n    future_yield() handed work to the pool\n"); r.failed++; }

    PRINT_RESULTS("backlog zero", _r);
    ((void(*)(object_t*,object_t*))continuation.f)(continuation.o, integer_from_int32(r.failed ? 1 : 0));
}

int main(void) {
    thread_start(run_tests);
}
