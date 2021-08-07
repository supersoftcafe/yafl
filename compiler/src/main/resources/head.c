
#include <stdlib.h>
#include <stddef.h>
#include <assert.h>
#include <memory.h>


typedef struct vtable vtable_t;
struct vtable {
    uint32_t typeId;
    uint32_t parentId;
    uint32_t size;
    uint32_t pointerCount;
    uint32_t pointerOffsets[1];
};

typedef struct object object_t;
struct object {
    size_t    rcount;
    vtable_t* vtable;
};

typedef struct released released_t;
struct released {
    released_t* next;
    vtable_t*   vtable;
};


static object_t* Create(vtable_t* vtable) __attribute__((noinline)) {
    object_t* object;

    object = (object_t*)malloc(vtable->size);
    if (object == NULL) abort();
    object->rcount = 1;
    object->vtable = vtable;

    return object;
}

static void Destroy(object_t* object) __attribute__((noinline)) {
    vtable_t*   vtable;
    int         index;
    released_t* head;
    object_t*   temp;

    head = (released_t*)object;
    while (head != NULL) {
        object = (object_t*)head;
        head = head->next;

        vtable = object->vtable;
        index = vtable->pointerCount;
        while (--index >= 0) {
            temp = ((object_t**)object)[vtable->pointerOffsets[index]];
            if (temp != NULL && --temp->rcount == 0) {
                ((released_t*)temp)->next = head;
                head = (released_t*)temp;
            }
        }

        free(object);
    }
}

static inline void Retain(object_t* object) {
    object->rcount++;
}

static inline void Release(object_t* object) {
    if (--object->rcount == 0)
        Destroy(object);
}

static inline void ReleaseNullable(object_t* object) {
    if (object != NULL)
        Release(object);
}



