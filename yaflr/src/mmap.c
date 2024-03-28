//
// Created by mbrown on 24/02/24.
//

#include "settings.h"
#include "mmap.h"
#include "blitz.h"
#include <sys/mman.h>
#include <unistd.h>
#include <assert.h>



size_t PAGE_SIZE = 0;


void mmap_init() {
    PAGE_SIZE = getpagesize();
}


static size_t fix_size(size_t size) {
    assert(size > 0);           // Must have a size
    assert(PAGE_SIZE > 0);      // Library must have been initialised

    // Fix the size to be a multiple of page size
    size_t size_difference = size & (PAGE_SIZE - 1);
    if (size_difference > 0)
        size += PAGE_SIZE - size_difference;
    assert(size % PAGE_SIZE == 0);

    return size;
}

static int fix_align(int align_log2) {
    assert(PAGE_SIZE > 0);      // Library must have been initialised
    assert(align_log2 > 0);     // Must have an alignment
    assert(align_log2 < 32);    // Just to have a sensible upper limit on alignment

    while ((((size_t)1) << align_log2) < PAGE_SIZE ) ++align_log2;

    return align_log2;
}


__attribute__((noinline))
void* mmap_alloc(size_t size, int align_log2) {
    size = fix_size(size);
    align_log2 = fix_align(align_log2);

#ifdef MAP_ALIGNED
    char* ptr = mmap(0, size, PROT_READ|PROT_WRITE, MAP_PRIVATE|MAP_ANON|MAP_NORESERVE|MAP_ALIGNED(align_log2), -1, 0);
#else
    size_t align_request = ((size_t)1) << align_log2;
    size_t overalloc_size = size + align_request - PAGE_SIZE;

    char* ptr = mmap(0, overalloc_size, PROT_READ|PROT_WRITE, MAP_PRIVATE|MAP_ANON|MAP_NORESERVE, -1, 0);

    if (ptr == MAP_FAILED)
        ERROR("mmap");

    size_t align_actual = ((size_t)ptr) & (align_request - 1);
    size_t  trim_before = align_actual == 0 ? 0 : (align_request - align_actual);
    size_t  trim_after  = overalloc_size - trim_before - size;

    if (trim_before > 0) {
        munmap(ptr, trim_before);
        ptr += trim_before;
    }

    if (trim_after > 0) {
        munmap(ptr + size, trim_after);
    }
#endif

    return ptr;
}

__attribute__((noinline))
void mmap_release(size_t size, void* ptr) {
    size = fix_size(size);

    int result = munmap(ptr, size);

    if (result == -1)
        ERROR("munmap");
}

__attribute__((noinline))
void mmap_protect(size_t size, void* ptr) {
    size = fix_size(size);

    int result = mprotect(ptr, size, PROT_NONE);

    if (result == -1)
        ERROR("mprotect");
}
