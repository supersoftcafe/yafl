
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

/* Spin-wait for the async callback to fire (used only where task_complete
   posts to the thread system rather than calling inline). */
#define AWAIT_CALLBACK() \
    do { while (!atomic_load(&_callback_fired)) GC_SAFE_POINT(); } while (0)

/* ---- tests ---- */

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

TEST(task_on_complete_already_complete_calls_immediately)
    /* task_complete first, then register — fires inline (tail call path) */
    _reset_callback();
    object_t* t = task_create(NULL);
    task_complete(t);
    task_on_complete(t, CALLBACK);
    ASSERT(atomic_load(&_callback_fired));
    ASSERT(_callback_task_arg == t);
TEST_END()

/* task_complete after task_on_complete fires asynchronously via the thread
   system. YAFL never does a synchronous wait, so instead of spin-waiting we
   chain the remainder of the test suite into the callback itself. */

TEST(task_complete_idempotent)
    /* Completing a task twice must not fire the callback more than once.
       First two completes set state to COMPLETE with no callback registered.
       Registering after both completes fires exactly once (inline path). */
    _reset_callback();
    object_t* t = task_create(NULL);
    task_complete(t);   /* PENDING -> COMPLETE, no callback */
    task_complete(t);   /* already COMPLETE, no-op */
    task_on_complete(t, CALLBACK);  /* fires inline: task already complete */
    ASSERT(atomic_load(&_callback_fired));
    ASSERT(_callback_task_arg == t);
TEST_END()

TEST(task_tagged_ptr_round_trip)
    object_t* t = task_create(NULL);
    object_t* tagged = (object_t*)((uintptr_t)t | PTR_TAG_TASK);
    ASSERT(PTR_IS_TASK(tagged));
    ASSERT(TASK_UNTAG(tagged) == t);
TEST_END()

/* ---- entrypoint ---- */

static struct test_results _async_r;
static fun_t _async_continuation;
static object_t* _async_expected_task;

static roots_declaration_func_t prev_roots;
static void declare_roots(void(*declare)(object_t**)) {
    prev_roots(declare);
    declare(&_callback_task_arg);
    declare(&_async_expected_task);
}

static object_t* _async_after_complete(object_t* self, object_t* task_arg) {
    struct test_results* _r = &_async_r;

    /* Verify the async-complete test first, in the callback itself. */
    printf("  %-50s ", "task_complete_after_on_complete_posts_callback");
    if (task_arg == _async_expected_task) {
        printf("OK\n"); _r->passed++;
    } else {
        printf("FAIL\n    callback task arg mismatch\n"); _r->failed++;
    }

    /* Remaining synchronous tests run inline. */
    RUN(task_complete_idempotent);
    RUN(task_tagged_ptr_round_trip);

    PRINT_RESULTS("task", _r);
    object_t* status = integer_create_from_int32(_r->failed ? 1 : 0);
    ((void(*)(object_t*,object_t*))_async_continuation.f)(_async_continuation.o, status);
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
    RUN(task_on_complete_already_complete_calls_immediately);

    /* Async case: register our completion-aware callback, complete the task,
       and return. The callback runs on a worker (possibly this one, after
       we return to the main loop), finishes the remaining tests, and
       invokes the exit continuation. */
    _reset_callback();
    object_t* t = task_create(NULL);
    _async_expected_task = t;
    task_on_complete(t, (fun_t){.f=_async_after_complete, .o=NULL});
    task_complete(t);
}

int main(void) {
    prev_roots = add_roots_declaration_func(declare_roots);
    thread_start(run_tests);
}
