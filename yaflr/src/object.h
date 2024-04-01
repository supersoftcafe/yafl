//
// Created by mbrown on 08/03/24.
//

#ifndef YAFLR_OBJECT_H
#define YAFLR_OBJECT_H

#include <stdint.h>

struct heap_node;
typedef struct heap_node heap_node_t;

typedef uint16_t field_index_t;


typedef struct shadow_stack_layout {
    field_index_t pointer_count;
    field_index_t pointer_indexes[0];    // Pointer index of each pointer
} shadow_stack_layout_t;

typedef struct shadow_stack_layout1 {
    shadow_stack_layout_t l;
    field_index_t pointer_indexes[1];    // Pointer index of each pointer
} shadow_stack_layout1_t;

typedef struct shadow_stack_layout2 {
    shadow_stack_layout_t l;
    field_index_t pointer_indexes[2];    // Pointer index of each pointer
} shadow_stack_layout2_t;

typedef struct shadow_stack {
    shadow_stack_layout_t *layout;
    struct shadow_stack   *next;
} shadow_stack_t;

struct heap {
    heap_node_t* current_head;
    size_t object_count;
    size_t used_space;
    size_t node_count;
    size_t countdown;
};
typedef struct heap heap_t;

typedef void(*func_t)(void*);

struct vtable_entry {
    uintptr_t function_id;
    func_t    function;
};
typedef struct vtable_entry vtable_entry_t;

struct layout {
    field_index_t size;
    field_index_t pointer_count;
    field_index_t pointer_indexes[0];    // Pointer index of each pointer
};
typedef struct layout layout_t;

struct vtable {
    layout_t*         object_layout;      // Required, layout of fields in the object
    layout_t*          array_layout;      // Optional, layout of array elements
    field_index_t  array_len_index;      // Pointer index of uint32_t array length field
    field_index_t   functions_mask;      // Size-1, must be n^2-1, is the bit mask used to lookup function pointers
    vtable_entry_t        functions[0];   // Each function has a prefix that is the ID
};
typedef struct vtable vtable_t;

struct object {
    vtable_t* vtable;
};
typedef struct object object_t;


object_t* object_create(heap_t *heap, shadow_stack_t *shadow_stack, vtable_t* vtable);

object_t* object_create_array(heap_t *heap, shadow_stack_t *shadow_stack, vtable_t* vtable, uint32_t length);



void object_init(int aggressive_compaction);

__attribute__((noinline))
void object_heap_create(heap_t *heap);

__attribute__((noinline))
void object_heap_destroy(heap_t *heap);

__attribute__((noinline))
void object_heap_compact2(heap_t *heap, shadow_stack_t *shadow_stack);

__attribute__((noinline))
void object_heap_compact(heap_t *heap, int count, object_t **array);

__attribute__((noinline))
void object_heap_append(heap_t *heap, heap_t* sub_heap);

func_t object_function_lookup(object_t* object, uintptr_t function_id);


#endif //YAFLR_OBJECT_H
