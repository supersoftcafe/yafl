//
// Created by mbrown on 23/03/24.
//

#undef NDEBUG
#include <assert.h>
#include "../src/mmap.h"


static char* test_alloc(size_t size, int bits, int offset) {
    size_t mask = (((size_t)1) << bits) - 1;
    char* ptr = mmap_alloc_aligned(size, bits);

    assert( ptr != NULL );
    assert( (mask & (size_t)ptr) == 0 );

    for (size_t index = 0; index < size; ++index) {
        char value = ptr[index];
        assert(value == 0);
        ptr[index] = (char)(index + offset);
    }

    return ptr;
}

static void test_content(size_t size, const char* ptr, int offset) {
    for (size_t index = 0; index < size; ++index) {
        char value = ptr[index];
        char expected = (char)(index + offset);
        assert(value == expected);
    }
}

static char* array[1000];

void test_mmap_alloc() {
    mmap_init();

    int offset = 0;
    for (size_t size = 10000; size < 10000000; size *= 3) {
        for (int bits = 8; bits < 20; ++bits) {
            array[offset] = test_alloc(size, bits, offset);
            offset += 1;
        }
    }

    offset = 0;
    for (size_t size = 10000; size < 10000000; size *= 3) {
        for (int bits = 8; bits < 20; ++bits) {
            test_content(size, array[offset], offset);
            offset += 1;
        }
    }

    offset = 0;
    for (size_t size = 10000; size < 10000000; size *= 3) {
        for (int bits = 8; bits < 20; ++bits) {
            mmap_release(size, array[offset]);
            offset += 1;
        }
    }
}
