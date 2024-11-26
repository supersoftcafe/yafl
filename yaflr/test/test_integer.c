
#undef NDEBUG
#include <assert.h>
#include <string.h>
#include "../src/mmap.h"
#include "../src/integer.h"

object_t* create_from_native(intptr_t value) {
    object_t* a = integer_create_from_native(value);
    assert(integer_compare_with_native(a, value) == 0);
    return a;
}

void test_integer() {
    mmap_init();
    object_init();

    heap_t heap;
    object_heap_create(&heap);
    object_heap_select(&heap);

    object_t* a = create_from_native(1000000000);
    object_t* b = create_from_native(0x3fffffffffffffffL);
    object_t* c = create_from_native(0x7fffffffffffffffL);
    object_t* d = create_from_native(-0x7fffffffffffffffL);

    object_t* r1 = integer_add(a, b);
    object_t* r2 = integer_add(r1, c);
    object_t* r3 = integer_add(r2, d);

    assert(integer_compare_with_native(r1, 0) > 0);
    assert(integer_compare_with_native(r1, 0x3fffffffffffffffL + 1000000000) == 0);

    assert(integer_compare_with_native(r2, 0) > 0);
    assert(integer_compare_with_native(r2, 0x3fffffffffffffffL + 1000000000) > 0);

    assert(integer_compare_with_native(r3, 0) > 0);
    assert(integer_compare_with_native(r3, 0x3fffffffffffffffL + 1000000000) == 0);

}
