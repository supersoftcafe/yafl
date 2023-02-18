//
// Created by Michael Brown on 11/02/2023.
//

#include <stdlib.h>
#include <assert.h>
#include <stdatomic.h>
#include "blitz.h"
#include "heap.h"


static atomic_size_t total_memory_usage = 0;

static void heap_dump_status() {
    DEBUG("Final memory usage is %ld\n", total_memory_usage);
}

void heap_init() {
    atexit(heap_dump_status);
}

__attribute__((noinline))
void heap_free(size_t size, void* pointer) {
    atomic_fetch_sub(&total_memory_usage, size);
    free(pointer);
}

__attribute__((noinline, malloc))
void* heap_alloc(size_t size) {
    struct object* pointer = malloc(size);
    if (pointer == NULL)
        ERROR("malloc");

    atomic_fetch_add(&total_memory_usage, size);

    return pointer;
}
