//
// Created by Michael Brown on 18/02/2023.
//

#include <assert.h>
#include "object.h"
#include "heap.h"
#include "blitz.h"


static void global_unit_delete(struct object* self) {
    ERROR("Illegal call to delete unit object");
}

static struct {
    struct {
        size_t lookup_mask;
        void(*delete)(struct object*);
    } head;
    size_t* methods[4];
} global_unit_vt = { { 3, global_unit_delete }, { NULL, NULL, NULL, NULL } };

struct object global_unit = { (struct vtable*)&global_unit_vt, 0 };


struct object* obj_create(size_t size, struct vtable* vtable) {
    assert(size >= sizeof(struct object));

    struct object* object = heap_alloc(size);
    object->vtable = vtable;
    object->refcnt = 1;

    return object;
}

void obj_release(struct object* object) {
    if (object->refcnt != 0 && (object->refcnt == 1 || atomic_fetch_sub(&object->refcnt, 1) == 1))
        object->vtable->head.delete(object);
}

void obj_acquire(struct object* object) {
    if (object->refcnt != 0)
        atomic_fetch_add(&object->refcnt, 1);
}
