//
// Created by Michael Brown on 18/02/2023.
//

#ifndef YAFLC1_OBJECT_H
#define YAFLC1_OBJECT_H

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

extern struct object global_unit;

struct object* obj_create(size_t size, struct vtable* vtable);
void obj_release(struct object*);
void obj_acquire(struct object*);

#endif //YAFLC1_OBJECT_H
