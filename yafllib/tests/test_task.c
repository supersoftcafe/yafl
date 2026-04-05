
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

TEST(task_complete_after_on_complete_posts_callback)
    /* Register callback first, then complete — fires asynchronously via thread system */
    _reset_callback();
    object_t* t = task_create(NULL);
    task_on_complete(t, CALLBACK);
    task_complete(t);
    AWAIT_CALLBACK();
    ASSERT(_callback_task_arg == t);
TEST_END()

TEST(task_tagged_ptr_round_trip)
    object_t* t = task_create(NULL);
    object_t* tagged = (object_t*)((uintptr_t)t | PTR_TAG_TASK);
    ASSERT(PTR_IS_TASK(tagged));
    ASSERT(TASK_UNTAG(tagged) == (task_t*)t);
TEST_END()

/* ---- entrypoint ---- */

static roots_declaration_func_t prev_roots;
static void declare_roots(void(*declare)(object_t**)) {
    prev_roots(declare);
    declare(&_callback_task_arg);
}

static void run_tests(object_t* _, fun_t continuation) {
    struct test_results r = {0, 0, NULL};
    struct test_results* _r = &r;

    printf("=== task tests ===\n");

    RUN(task_create_returns_object);
    RUN(task_complete_no_callback_returns_null);
    RUN(task_on_complete_pending_returns_null);
    RUN(task_on_complete_already_complete_calls_immediately);
    RUN(task_complete_after_on_complete_posts_callback);
    RUN(task_tagged_ptr_round_trip);

    PRINT_RESULTS("task", _r);

    object_t* status = integer_create_from_int32(r.failed ? 1 : 0);
    ((void(*)(object_t*,object_t*))continuation.f)(continuation.o, status);
}

int main(void) {
    prev_roots = add_roots_declaration_func(declare_roots);
    thread_start(run_tests);
}
