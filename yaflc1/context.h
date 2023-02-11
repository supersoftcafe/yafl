//
// Created by Michael Brown on 09/02/2023.
//

#ifndef YAFLC1_CONTEXT_H
#define YAFLC1_CONTEXT_H

#include <sys/mman.h>

void* mmap_or_fail(void* addr, size_t len, int prot, int flags, int fd, off_t offset);
void munmap_or_fail(void* ptr, size_t size);
void mprotect_or_fail(void* ptr, size_t size, int prot);

#endif //YAFLC1_CONTEXT_H
