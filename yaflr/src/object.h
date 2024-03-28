//
// Created by mbrown on 08/03/24.
//

#ifndef YAFLR_OBJECT_H
#define YAFLR_OBJECT_H

#include <stdint.h>

struct heap_node;
typedef struct heap_node heap_node_t;

struct heap {
    heap_node_t* current_head;
    size_t object_count;
    size_t used_space;
    size_t node_count;
};
typedef struct heap heap_t;

typedef void(*func_t)(void*);

struct vtable_entry {
    uintptr_t function_id;
    func_t    function;
};
typedef struct vtable_entry vtable_entry_t;

struct layout {
    uint32_t size;
    uint32_t pointer_count;
    uint32_t pointer_offsets[0];    // Byte offsets of each pointer
};
typedef struct layout layout_t;

struct vtable {
    layout_t*   object_layout;      // Required, layout of fields in the object
    layout_t*    array_layout;      // Optional, layout of array elements
    uint32_t array_len_offset;      // Byte offset of uint32_t array length field
    uint32_t  functions_mask;      // Size-1, must be n^2-1, is the bit mask used to lookup function pointers
    vtable_entry_t  functions[0];   // Each function has a prefix that is the ID
};
typedef struct vtable vtable_t;

struct object {
    vtable_t* vtable;
};
typedef struct object object_t;


object_t* object_create(heap_t* heap, vtable_t* vtable);

object_t* object_create_array(heap_t* heap, vtable_t* vtable, uint32_t length);



void object_init();

__attribute__((noinline))
void object_heap_create(heap_t* heap);

__attribute__((noinline))
void object_heap_destroy(heap_t* heap);

__attribute__((noinline))
void object_heap_compact(heap_t* heap, int root_count, object_t** roots);

__attribute__((noinline))
void object_heap_append(heap_t* heap, heap_t* sub_heap);

func_t object_function_lookup(object_t* object, uintptr_t function_id);


#endif //YAFLR_OBJECT_H
