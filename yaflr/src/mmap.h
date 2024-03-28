//
// Created by mbrown on 24/02/24.
//
// Chunky allocations from the host memory map or mmap via OS calls.
// Memory is assumed to be lazily allocated on a modern OS.
//

#ifndef YAFLR_MMAP_H
#define YAFLR_MMAP_H

#include <stddef.h>

extern size_t PAGE_SIZE;

void* mmap_alloc(size_t size, int align_log2);
void mmap_release(size_t size, void* ptr);
void mmap_protect(size_t size, void* ptr);
void mmap_init();

#endif //YAFLR_MMAP_H
