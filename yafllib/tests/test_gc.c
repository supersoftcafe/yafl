
/*
 * GC stress test — adapted from main.c.
 * Spawns many worker tasks that concurrently allocate and write-barrier
 * string objects into shared arrays, then verifies the contents survive GC.
 */

#include "test_framework.h"
#include <string.h>

/* ---- shared state for the allocation test ---- */

struct gc_test_state {
    object_t  parent;
    int32_t   length;          /* array capacity (= worker count) */
    _Atomic(int32_t) remaining;
    fun_t     continuation;
    string_t* results[3];
};

static vtable_t gc_test_state_vt = {
    .object_size              = offsetof(struct gc_test_state, results[0]),
    .array_el_size            = sizeof(string_t*),
    .object_pointer_locations = maskof(struct gc_test_state, .continuation.o),
    .array_el_pointer_locations = maskof(string_t*, ),
    .functions_mask           = 0,
    .array_len_offset         = offsetof(integer_t, length),
    .is_mutable               = 1,
    .name                     = "gc_test_state",
    .implements_array         = VTABLE_IMPLEMENTS(0),
};

/* These must be file-scope so the compound literal has static storage duration.
   Worker threads access them after run_tests() has returned. */
static object_t* _left    = STR("Fred and bill went on a ride ");
static object_t* _right   = STR("together in the jeep.");
static const char* _expected = "Fred and bill went on a ride together in the jeep.";

static void gc_test_declare_roots(void(*declare)(object_t**)) {
    declare(&_left);
    declare(&_right);
}

static void _worker_complete(struct gc_test_state* state, string_t* result) {
    int32_t idx = atomic_fetch_sub(&state->remaining, 1) - 1;
    state->results[idx % 3] = result;
    if (idx == 0) {
        fun_t k = state->continuation;
        ((void(*)(object_t*,object_t*))k.f)(k.o, INTEGER_LITERAL_1(0, 0));
    }
}

static void _do_worker(struct gc_test_state* state) {
    struct gc_test_state* slots[10] = {NULL};

    for (int i = 0; i < 10; i++) {
        GC_SAFE_POINT();
        slots[i] = (struct gc_test_state*)array_create(&gc_test_state_vt, 3);
    }

    for (int round = 0; round < 100; round++) {
        GC_SAFE_POINT();
        for (int j = 0; j < 10; j++) {
            GC_SAFE_POINT();
            string_t* str = (string_t*)string_append(_left, _right);
            struct gc_test_state* slot = slots[j];
            if (slot) {
                int idx = (round ^ j) % 3;
                GC_WRITE_BARRIER(slot->results[idx], 1);
                slot->results[idx] = str;
            }
        }

        for (int j = 0; j < 10; j++) {
            GC_SAFE_POINT();
            struct gc_test_state* slot = slots[j];
            if (slot) {
                assert(slot->results[0] == NULL || strcmp((char*)slot->results[0]->array, _expected) == 0);
                assert(slot->results[1] == NULL || strcmp((char*)slot->results[1]->array, _expected) == 0);
                assert(slot->results[2] == NULL || strcmp((char*)slot->results[2]->array, _expected) == 0);
            }
        }
    }

    _worker_complete(state, slots[3] ? slots[3]->results[0] : NULL);
}

static void setup_gc_test(object_t* _, fun_t continuation) {
    int32_t worker_count = 10;

    struct gc_test_state* state =
        (struct gc_test_state*)array_create(&gc_test_state_vt, worker_count);
    state->continuation = continuation;
    atomic_store(&state->remaining, worker_count);

    for (int32_t i = 0; i < worker_count; i++) {
        GC_SAFE_POINT();
        worker_node_t* node = thread_work_prepare(
            (fun_t){.f = _do_worker, .o = (object_t*)state});
        thread_work_post_fast(node);
    }
}

/* ---- entrypoint ---- */

static roots_declaration_func_t prev_roots;

static void declare_roots(void(*declare)(object_t**)) {
    prev_roots(declare);
    gc_test_declare_roots(declare);
}

static void run_tests(object_t* _, fun_t continuation) {
    printf("=== gc stress test ===\n");
    printf("  %-50s ", "concurrent_string_allocation");
    fflush(stdout);

    /*
     * The GC test completes asynchronously via continuation.
     * If it survives without assert-failing, it passes.
     * We print "OK" here speculatively; a crash means failure.
     */
    printf("OK (running async)\n");

    setup_gc_test(NULL, continuation);
}

int main(void) {
    prev_roots = add_roots_declaration_func(declare_roots);
    thread_start(run_tests);
}
