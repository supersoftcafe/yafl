//
// Created by mbrown on 23/03/24.
//

#undef NDEBUG
#include <assert.h>
#include <stdlib.h>
#include <signal.h>
#include "../src/mmap.h"


static void handle_segfault(int) {
    exit(0); // Success
}

void test_mmap_protect() {
    mmap_init();

    char* ptr = mmap_alloc(0x10000, 16);
    mmap_protect(PAGE_SIZE, ptr);

    signal(SIGSEGV, handle_segfault);
    ptr[100] = 100;

    exit(1);
}