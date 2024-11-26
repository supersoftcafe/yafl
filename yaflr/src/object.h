//
// Created by mbrown on 08/03/24.
//

#ifndef YAFLR_OBJECT_H
#define YAFLR_OBJECT_H

#include <stdint.h>
#include <stddef.h>



struct heap_node;
typedef struct heap_node heap_node_t;


struct heap {
    heap_node_t *current_head;
    size_t node_count;
    uintptr_t next; // Subtract object size, and mask to align. If still >= base, you've got a new object.
    uintptr_t base; // Lowest allocatable address in the current pool
};
typedef struct heap heap_t;

typedef void(*func_t)(void*);

struct vtable_entry {
    uintptr_t function_id;
    func_t    function;
};
typedef struct vtable_entry vtable_entry_t;


struct vtable {
    uint16_t object_size;
    uint16_t array_el_size;
    uint32_t object_pointer_locations;
    uint32_t array_el_pointer_locations;
    uint32_t functions_mask;      // Size-1, must be n^2-1, is the bit mask used to lookup function pointers
    uint16_t array_len_offset;    // Offset of uint32_t array length field
    uint16_t implements_count;    // How many classes are in the list below. List can be null if this is zero.
    uint32_t implements_offset;   // Offset to list of *all* classes that this class extends, ordered depth first.
    vtable_entry_t functions[0];  // Each function has a prefix that is the ID
};
typedef struct vtable vtable_t;

struct object {
    vtable_t* vtable;
};
typedef struct object object_t;



void object_init(void);

__attribute__((noinline))
void object_heap_create(heap_t* heap);

__attribute__((noinline))
void object_heap_select(heap_t* heap);

__attribute__((noinline))
void object_heap_destroy(heap_t* heap);

__attribute__((noinline))
void object_heap_compact(heap_t* heap, ...);

__attribute__((noinline))
void object_heap_append(heap_t* heap, heap_t* sub_heap);



func_t object_vlookup(object_t* object, uintptr_t function_id);
object_t* object_create_internal(size_t size);
#define object_create(type) (type*)object_create_internal(sizeof(type))
#define object_create_array(type, array_field, size) (type*)object_create_internal((size_t)&(((type*)0)->array_field[size]))



#endif //YAFLR_OBJECT_H
