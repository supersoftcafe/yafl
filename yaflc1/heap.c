//
// Created by Michael Brown on 11/02/2023.
//

#include <stdlib.h>
#include <assert.h>
#include "blitz.h"
#include "heap.h"


static atomic_size_t total_memory_usage = 0;

static void heap_dump_status() {
    DEBUG("Final memory usage is %ld\n", total_memory_usage);
}

void heap_init() {
    atexit(heap_dump_status);
}

struct object* heap_alloc(struct vtable* vtable, size_t size) {
    assert(size >= sizeof(struct object));

    struct object* object = malloc(size);
    if (object == NULL)
        ERROR("malloc");

    atomic_fetch_add(&total_memory_usage, size);

    object->vtable = vtable;
    object->refcnt = 1;

    return object;
}

void heap_release(struct object* object) {
    if (atomic_fetch_sub(&object->refcnt, 1) == 1)
        object->vtable->head.delete(object);
}

void heap_acquire(struct object* object) {
    atomic_fetch_add(&object->refcnt, 1);
}

void heap_free(struct object* object, size_t size) {
    atomic_fetch_sub(&total_memory_usage, size);
    free(object);
}
