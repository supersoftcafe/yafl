#include "test_framework.h"

/* ---- callback helpers ---- */

/* Atomic flag used by async tests to detect callback invocation */
static _Atomic(int32_t) _callback_fired;
static object_t*        _callback_task_arg;

static object_t* _record_callback(object_t* self, object_t* task_arg) {
    _callback_task_arg = task_arg;
    atomic_store(&_callback_fired, 1);
    return NULL;
}

static void _reset_callback(void) {
    atomic_store(&_callback_fired, 0);
    _callback_task_arg = NULL;
}

#define CALLBACK ((fun_t){.f = _record_callback, .o = NULL})

/* ---- tests ----
 *
 * Task continuations are DEFERRED: every callback fires from a worker's
 * clean dispatch frame, never nested in the completer's or registrant's
 * frames. So no test may spin-wait for a callback — on a single worker the
 * spinner IS the thread that must pop the continuation. Tests that need a
 * fired callback chain the rest of the suite into the callback instead. */

TEST(task_create_returns_object)
    object_t* t = task_create(NULL);
    ASSERT(t != NULL);
    ASSERT(PTR_IS_OBJECT(t));
TEST_END()

TEST(task_complete_no_callback_returns_null)
    object_t* t = task_create(NULL);
    object_t* r = task_complete(t);
    ASSERT(r == NULL);
TEST_END()

TEST(task_on_complete_pending_returns_null)
    _reset_callback();
    object_t* t = task_create(NULL);
    object_t* r = task_on_complete(t, CALLBACK);
    ASSERT(r == NULL);
    ASSERT(!atomic_load(&_callback_fired));
TEST_END()

TEST(task_tagged_ptr_round_trip)
    object_t* t = task_create(NULL);
    object_t* tagged = (object_t*)((uintptr_t)t | PTR_TAG_TASK);
    ASSERT(PTR_IS_TASK(tagged));
    ASSERT(TASK_UNTAG(tagged) == t);
TEST_END()

/* ---- entrypoint: chained async stages ---- */

static struct test_results _async_r;
static fun_t _async_continuation;
static object_t* _async_expected_task;

static roots_declaration_func_t prev_roots;
static void declare_roots(void(*declare)(object_t**)) {
    prev_roots(declare);
    declare(&_callback_task_arg);
    declare(&_async_expected_task);
}

static void _finish(void) {
    struct test_results* _r = &_async_r;
    PRINT_RESULTS("task", _r);
    object_t* status = integer_from_int32(_r->failed ? 1 : 0);
    ((void(*)(object_t*,object_t*))_async_continuation.f)(_async_continuation.o, status);
}

static void _check_stage(const char* name, object_t* task_arg) {
    struct test_results* _r = &_async_r;
    printf("  %-50s ", name);
    if (task_arg == _async_expected_task) {
        printf("OK\n"); _r->passed++;
    } else {
        printf("FAIL\n    callback task arg mismatch\n"); _r->failed++;
    }
}

/* Stage 3: verify the idempotent-complete fire, then finish. */
static object_t* _stage_idempotent_done(object_t* self, object_t* task_arg) {
    (void)self;
    _check_stage("task_complete_idempotent", task_arg);
    _finish();
    return NULL;
}

/* Stage 2: verify the already-complete deferred fire, then run the
 * idempotent test: completing twice must not fire more than once — the
 * single fire of this stage's callback IS the assertion (a double fire
 * would run _stage_idempotent_done twice and double-finish loudly). */
static object_t* _stage_already_complete_done(object_t* self, object_t* task_arg) {
    (void)self;
    _check_stage("task_on_complete_already_complete_fires_deferred", task_arg);

    object_t* t = task_create(NULL);
    _async_expected_task = t;
    task_complete(t);   /* PENDING -> COMPLETE, no callback */
    task_complete(t);   /* already COMPLETE, must be a no-op */
    task_on_complete(t, (fun_t){.f=_stage_idempotent_done, .o=NULL});
    return NULL;
}

/* Stage 1: verify register-then-complete fired, then run the
 * already-complete case: complete first, register after — the continuation
 * must be POSTED (deferred-resumption contract), reaching stage 2 on a
 * clean dispatch frame. */
static object_t* _stage_post_complete_done(object_t* self, object_t* task_arg) {
    (void)self;
    _check_stage("task_complete_after_on_complete_posts_callback", task_arg);

    object_t* t = task_create(NULL);
    _async_expected_task = t;
    task_complete(t);
    object_t* r = task_on_complete(t, (fun_t){.f=_stage_already_complete_done, .o=NULL});
    if (r != NULL) {
        printf("  task_on_complete on complete task returned non-NULL\n");
        _async_r.failed++;
    }
    return NULL;
}

static void run_tests(object_t* _, fun_t continuation) {
    _async_r.passed = 0; _async_r.failed = 0; _async_r.current_test = NULL;
    _async_continuation = continuation;
    struct test_results* _r = &_async_r;

    printf("=== task tests ===\n");

    RUN(task_create_returns_object);
    RUN(task_complete_no_callback_returns_null);
    RUN(task_on_complete_pending_returns_null);
    RUN(task_tagged_ptr_round_trip);

    /* Async stages: register, complete, return to the dispatch loop; each
       stage's callback verifies the previous and launches the next. */
    _reset_callback();
    object_t* t = task_create(NULL);
    _async_expected_task = t;
    task_on_complete(t, (fun_t){.f=_stage_post_complete_done, .o=NULL});
    task_complete(t);
}

int main(void) {
    prev_roots = add_roots_declaration_func(declare_roots);
    thread_start(run_tests);
}
