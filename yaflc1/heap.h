//
// Created by Michael Brown on 11/02/2023.
//

#ifndef YAFLC1_HEAP_H
#define YAFLC1_HEAP_H

#include <stdlib.h>
#include <stdatomic.h>

struct vtable;
struct object;

struct vtable {
    struct {
        size_t lookup_mask;
        void(*delete)(struct object*);
    } head;
    size_t* methods[0];
};

struct object {
    struct vtable* vtable;
    atomic_size_t  refcnt;
};

void heap_init();
struct object* heap_alloc(struct vtable* vtable, size_t size);
void heap_release(struct object*);
void heap_acquire(struct object*);
void heap_free(struct object* object, size_t size);


#endif //YAFLC1_HEAP_H
