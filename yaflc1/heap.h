//
// Created by Michael Brown on 11/02/2023.
//

#ifndef YAFLC1_HEAP_H
#define YAFLC1_HEAP_H

#include <stdlib.h>

void heap_init();

__attribute__((noinline))
void heap_free(size_t size, void* pointer);

__attribute__((noinline, malloc))
void* heap_alloc(size_t size);

#endif //YAFLC1_HEAP_H
