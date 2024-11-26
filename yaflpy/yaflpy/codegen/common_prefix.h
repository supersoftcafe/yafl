#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <assert.h>

#define maskof(type, field)\
        ((uint32_t)(((uint32_t)1)<<(offsetof(struct {type o;}, o field)/sizeof(void*))))

typedef struct {
    void* f;
    void* o;
} fun_t;

typedef struct {
    intptr_t i;
    void*    f;
} vtable_entry_t;

typedef struct {
    uint16_t object_size;
    uint16_t array_el_size;
    uint32_t object_pointer_locations;
// 8 bytes
    uint32_t array_el_pointer_locations;
    uint32_t functions_mask;      // Size-1, must be n^2-1, is the bit mask used to lookup function pointers
// 16 bytes
    uint16_t array_len_offset;    // Offset of uint32_t array length field
    uint16_t implements_count;    // How many classes are in the list below. List can be null if this is zero.
    uint32_t implements_offset;   // Offset to list of *all* classes that this class extends, ordered depth first.
// 48 bytes
    vtable_entry_t lookup[16];    // Each function has a prefix that is the ID. The array size is nominal to help with debugging, in reality it's variable length.
} vtable_t;

typedef struct {
    vtable_t* vtable;
} object_t;

// This calculation needs to work with positive signed 32 bit numbers
#define rotate_function_id(id)\
        ((id * sizeof(intptr_t) * 2) | (id / (134217728 / sizeof(intptr_t) * 8)))

static
fun_t vtable_lookup(void* object, intptr_t id) {
    vtable_t* vtable = ((object_t*)object)->vtable;
    intptr_t index = id & vtable->functions_mask;
    vtable_entry_t* entry = (vtable_entry_t*)(((char*)&(vtable->lookup[-1])) + index);
    do {entry++;
        // Blank entries have -1 as the id, which will cause this loop to exit
    } while ((entry->i ^ id) > 0);
    return (fun_t){.f=entry->f, .o=object};
}

static
void* object_create(vtable_t* vtable) {
    assert(vtable->array_el_size == 0);
    void* object = malloc(vtable->object_size);
    assert(object != NULL);
    ((object_t*)object)->vtable = vtable;
    return object;
}

static
void* array_create(vtable_t* vtable, int32_t length) {
    assert(length >= 0);
    assert(vtable->array_el_size != 0);
    void* object = malloc(vtable->object_size + vtable->array_el_size*length);
    assert(object != NULL);
    ((object_t*)object)->vtable = vtable;
    *((int32_t*)(((char*)object)+(vtable->array_len_offset))) = length;
    return object;
}

#define __OP_add_int8__ (a, b)        ( int8_t)((( int8_t)(a)) + (( int8_t)(b)))
#define __OP_add_int16__(a, b)        (int16_t)(((int16_t)(a)) + ((int16_t)(b)))
#define __OP_add_int32__(a, b)        (int32_t)(((int32_t)(a)) + ((int32_t)(b)))
#define __OP_add_int64__(a, b)        (int64_t)(((int64_t)(a)) + ((int64_t)(b)))
#define __OP_sign_extend_int32__(a)   (int32_t)(a)
#define __OP_sign_extend_int64__(a)   (int64_t)(a)
