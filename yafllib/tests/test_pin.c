// Object pinning: a pinned object survives compaction AT ITS ADDRESS while
// its neighbours evacuate; after unpin it is movable again. The pin exists
// so a runtime primitive (ListBuilder) can mutate a not-yet-published field
// through a raw pointer without racing lazy relocation.
#include "../yafl.h"
#include <stdio.h>
#include <stdlib.h>

extern void *object_alloc_fast_raw(size_t size, bool is_mutable);
extern void _gc_safe_point2(void);

static vtable_t TEST_VT = { .object_size = 2*sizeof(void*), .is_mutable = 0, .name = "pin_test" };

static object_t* alloc_obj(void) {
    object_t* o = (object_t*)object_alloc_fast_raw(2*sizeof(void*), false);
    o->vtable = vtable_tag(&TEST_VT);
    ((uintptr_t*)o)[1] = 0xC0FFEE;
    return o;
}

#define CHECK(cond, msg) do { if (!(cond)) { printf("FAIL: %s\n", msg); exit(1); } } while (0)

static void run_tests(object_t* _, fun_t continuation) {
    (void)_; (void)continuation;
    enum { CHURN = 200000 };
    printf("=== object pin test ===\n");

    object_t* pinned = alloc_obj();
    object_pin(pinned);
    object_t* before = pinned;

    for (int i = 0; i < CHURN; ++i) {
        (void)alloc_obj();
        if ((i & 1023) == 0) _gc_safe_point2();
    }

    CHECK(pinned == before, "pinned object moved");
    CHECK(vtable_is_pinned(pinned->vtable), "pin bit lost");
    CHECK(vtable_untag(pinned->vtable) == &TEST_VT, "vtable corrupted under pin");
    CHECK(((uintptr_t*)pinned)[1] == 0xC0FFEE, "payload corrupted");

    object_unpin(pinned);
    CHECK(!vtable_is_pinned(pinned->vtable), "unpin failed");
    CHECK(vtable_untag(pinned->vtable) == &TEST_VT, "vtable wrong after unpin");

    for (int i = 0; i < CHURN; ++i) {
        (void)alloc_obj();
        if ((i & 1023) == 0) _gc_safe_point2();
    }
    CHECK(object_get_vtable(pinned) == &TEST_VT, "resolution broken after unpin churn");

    printf("  pinned_object_survives_compaction_in_place    OK\n");
    printf("pin: 1 passed, 0 failed\n");
    exit(0);
}

int main(void) {
    thread_start(run_tests);
    return 1;   // unreachable: run_tests exits
}
