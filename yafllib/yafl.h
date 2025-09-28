#pragma once


#include <stdatomic.h>
#include <stdnoreturn.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <stddef.h>
#include <assert.h>


#if defined(_WIN32) || defined(__CYGWIN__)
#  define EXTERN __declspec(dllimport)
#  define EXPORT __declspec(dllexport)
#  define HIDDEN
#elif __GNUC__ >= 4
#  define EXTERN extern
#  define EXPORT __attribute__((visibility("default")))
#  define HIDDEN __attribute__((visibility("hidden")))
#endif


#if defined(_MSC_VER)
#  define INLINE static __forceinline
#  define NOINLINE      __declspec(noinline)
#  define NORETURN      __declspec(noreturn)
#  define COLD          __declspec(code_seg(".text$cold"))
#elif defined(__GNUC__)
#  define INLINE static __attribute__((always_inline)) inline
#  define NOINLINE      __attribute__((noinline))
#  define NORETURN      __attribute__((noreturn))
#  define COLD          __attribute__((cold))
#else
#  define INLINE
#  define NOINLINE
#  define NORETURN
#  define COLD
#endif


#if defined(__GNUC__)
  #define LIKELY(x)   __builtin_expect(!!(x), 1)
  #define UNLIKELY(x) __builtin_expect(!!(x), 0)
#else
  #define LIKELY(x)   (x)
  #define UNLIKELY(x) (x)
#endif


#define indexof(type, field) (offsetof(type, field) / sizeof(((type*)NULL)->field))
#define total_bits(type) (sizeof(type) * 8)


#if defined(__GNUC__)
#  define index_of_lowest_bit(value)             \
        _Generic( (value),                       \
            unsigned long long: __builtin_ctzll, \
            unsigned long: __builtin_ctzl,       \
            unsigned int: __builtin_ctz          \
        )(value)
#else
#  error "No implementation for index_of_lowest_bit"
#endif


#if UINTPTR_MAX == 0xFFFFFFFF
#  define WORD_SIZE 32
#elif UINTPTR_MAX == 0xFFFFFFFFFFFFFFFF
#  define WORD_SIZE 64
#else
#  error "Unknown pointer size or unsupported platform."
#endif


#define ALIGNED     __attribute__((aligned(32)))


#if defined(__BYTE_ORDER__) && __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__
#  define IS_LITTLE_ENDIAN 1
#elif defined(__BYTE_ORDER__) && __BYTE_ORDER__ == __ORDER_BIG_ENDIAN__
#  define IS_LITTLE_ENDIAN 0
#elif defined(_WIN32)
#  define IS_LITTLE_ENDIAN 1
#else
#  error "Cannot determine endianness"
#endif


#if defined(__aarch64__) && defined(__APPLE__)
#  define CACHE_LINE_SIZE 128
#elif defined(__x86_64__) || defined(_M_X64)
#  define CACHE_LINE_SIZE 64
#else
#  define CACHE_LINE_SIZE 64
#endif


EXTERN void log_error(char const* format, ...);
EXTERN noreturn void log_error_and_exit(char const* format, ...);
#define ERROR(...)  log_error_and_exit(__VA_ARGS__)
#ifndef NDEBUG
#  define DEBUG(...)  log_error(__VA_ARGS__)
#else
#  define DEBUG(...)
#endif


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

typedef struct vtable {
    uint16_t object_size;
    uint16_t array_el_size;
    uint32_t object_pointer_locations;
    uint32_t array_el_pointer_locations;
    uint32_t functions_mask;     // Size-1, must be n^2-1, is the bit mask used to lookup function pointers
    uint16_t array_len_offset;   // Offset of uint32_t array length field
    uint16_t is_mutable:1;
    struct vtable** implements_array; // Array of all classes that this class extends
#ifdef NDEBUG
    vtable_entry_t lookup[0];
#else
    vtable_entry_t lookup[16];   // The array size is nominal to help with debugging
#endif
} vtable_t;

#define VTABLE_DECLARE_STRUCT(NAME, LOOKUP_COUNT)\
        struct NAME {\
            uint16_t object_size;\
            uint16_t array_el_size;\
            uint32_t object_pointer_locations;\
            uint32_t array_el_pointer_locations;\
            uint32_t functions_mask;\
            uint16_t array_len_offset;\
            uint16_t is_mutable:1;\
            struct vtable** implements_array;\
            vtable_entry_t lookup[LOOKUP_COUNT];\
        }

#define VTABLE_DECLARE(LOOKUP_COUNT)\
        (struct vtable*)&(const VTABLE_DECLARE_STRUCT(, LOOKUP_COUNT))

#define VTABLE_IMPLEMENTS(COUNT, ...) (vtable_t**)&(struct{vtable_t*p[COUNT];vtable_t*t;}){.p = {__VA_ARGS__}, .t = (vtable_t*)0 }

typedef struct {
    vtable_t* vtable;
} object_t;


// This calculation needs to work with positive signed 32 bit numbers
#define rotate_function_id(id)\
        ((id * sizeof(intptr_t) * 2) | (id / (134217728 / sizeof(intptr_t) * 8)))

enum {
    VT_TAG_UNMANAGED = 0x0,    // Out of managed heap
    VT_TAG_MANAGED   = 0x1,    // Heap allocated object, not a static defined object
    VT_TAG_FORWARD   = 0x2,    // VTable is really a forwarding pointer
    VT_TAG_UNUSED    = 0x3,    // Unused
    VT_TAG_MASK      = 0x3
};

#define VT_TAG_GET(vt)      ((uintptr_t)(vt) & VT_TAG_MASK)
#define VT_TAG_UNSET(vt)    ((vtable_t*)((uintptr_t)(vt) & ~(uintptr_t)VT_TAG_MASK))
#define VT_TAG_SET(vt, tag) ((vtable_t*)((uintptr_t)(vt) & ~((uintptr_t)VT_TAG_MASK) | tag))


EXTERN vtable_t *object_get_vtable(object_t *object);
EXTERN void object_set_reference(object_t *object, size_t field_offset, object_t *value);
EXTERN fun_t vtable_lookup(object_t *object, intptr_t id);


typedef void(*roots_declaration_func_t)(void(*)(object_t**));
typedef void(*thread_roots_declaration_func_t)(void*,void(*)(object_t**));

EXTERN roots_declaration_func_t add_roots_declaration_func(roots_declaration_func_t);
EXTERN void object_gc_init();
EXTERN void object_gc_safe_point(); // Arbitary safe point for GC magic to happen
EXTERN void object_gc_io_begin();   // Start of potentially thread pausing IO
EXTERN void object_gc_io_end();     // End of potentially thread pausing IO
EXTERN void object_gc_declare_thread(thread_roots_declaration_func_t,void*); // Any thread that can do allocation must call this early on

EXTERN void object_gc_print_heap(); // Print objects that survived the last GC

EXTERN void* object_create(vtable_t* vtable);
EXTERN void* array_create(vtable_t* vtable, int32_t length);

EXTERN void abort_on_maths_error();
EXTERN void abort_on_vtable_lookup();
EXTERN void abort_on_out_of_memory();
EXTERN void abort_on_too_large_object();
EXTERN void abort_on_heap_allocation_on_non_worker_thread();

EXTERN void* memory_pages_alloc(size_t page_count);
EXTERN void memory_pages_free(void* ptr, size_t page_count);
EXTERN bool memory_pages_is_heap(void*ptr);
EXTERN size_t memory_count();


/**********************************************************
 *****************************
 *************
 *****
 **
 *                   Worker Threaads
 **
 *****
 *************
 *****************************
 **********************************************************/


EXTERN void declare_roots_thread(void(*)(object_t**));
EXTERN void thread_start(void(*entrypoint)(object_t*, fun_t));

typedef struct worker_node {
    object_t parent;
    _Atomic(struct worker_node*) next;
    fun_t action;
} worker_node_t;

EXTERN worker_node_t* thread_work_prepare(fun_t action);
EXTERN void thread_work_post_io(worker_node_t* work);
EXTERN void thread_work_post_fast(worker_node_t* work);


/**********************************************************
 *****************************
 *************
 *****
 **
 *                   Lazy initialisation
 **
 *****
 *************
 *****************************
 **********************************************************/


INLINE bool lazy_global_init_complete(object_t* flag_ptr) {return 1==(intptr_t)flag_ptr;}
EXPORT void lazy_global_init(object_t** self, object_t* flag_ptr, fun_t init, fun_t callback);


/**********************************************************
 *****************************
 *************
 *****
 **
 *                   Primitive operations
 **
 *****
 *************
 *****************************
 **********************************************************/


EXTERN void __abort_on_overflow();


INLINE bool test_gt_int32(int32_t self, int32_t data) { return self  > data; }
INLINE bool test_eq_int32(int32_t self, int32_t data) { return self == data; }
INLINE bool test_lt_int32(int32_t self, int32_t data) { return self  < data; }


/**********************************************************
 *****************************
 *************
 *****
 **
 *                     Big integer
 **
 *****
 *************
 *****************************
 **********************************************************/


typedef struct integer {
    vtable_t* vtable;
    uint32_t length;
    int32_t sign;
    uintptr_t array[
#ifndef NDEBUG
        4
#endif
    ];
} ALIGNED integer_t;

struct integer_vtable;
EXTERN struct integer_vtable INTEGER_VTABLE;


#if WORD_SIZE == 64
#define INTEGER_LITERAL_N(sign, count, array) ((object_t*)&(struct{vtable_t*v;uint32_t l;int32_t s;intptr_t a[count];}){(vtable_t*)&INTEGER_VTABLE,((count)+1)/2,sign,array})
#define INTEGER_LITERAL_N_1(value1) ((intptr_t)(value1))
#define INTEGER_LITERAL_N_2(value1, value2) (((intptr_t)(value1)&0xffffffffull)|((intptr_t)(value2)<<32))
#define INTEGER_LITERAL_1(sign, value1) (((!sign)&&(value1>INT32_MAX/2))||(value1>INT32_MAX/2+1)?INTEGER_LITERAL_N(sign,1,{value1}):(object_t*)((intptr_t)value1*(sign?-1:1)*2+1))
#define INTEGER_LITERAL_2(sign, value1, value2) (((!sign)&&(value2>INT32_MAX/2))||(value2>INT32_MAX/2+1)?INTEGER_LITERAL_N(sign,2,{INTEGER_LITERAL_N_2(value1, value2)}):(object_t*)((((intptr_t)value2<<32)+value1)*(sign?-1:1)*2+1))
#else
#define INTEGER_LITERAL_N(sign, count, array) ((object_t*)&(struct{vtable_t*v;uint32_t l;int32_t s;intptr_t a[count];}){(vtable_t*)&INTEGER_VTABLE,count,sign,array})
#define INTEGER_LITERAL_N_1(value1) value1
#define INTEGER_LITERAL_N_2(value1, value2) value1, value2
#define INTEGER_LITERAL_1(sign, value1) (((!sign)&&value1>INT32_MAX/2)||(value1>INT32_MAX/2+1)?INTEGER_LITERAL_N(sign,1,{value1}):(object_t*)((intptr_t)value1*(sign?-1:1)*2+1))
#define INTEGER_LITERAL_2(sign, value1, value2) INTEGER_LITERAL_N(sign, 2, {INTEGER_LITERAL_N_2(value1, value2)})
#endif
#define INTEGER_LITERAL_SEP ,


EXTERN object_t* integer_add_full(object_t* self, object_t* data);
INLINE object_t* integer_add(object_t* self, object_t* data) {
    intptr_t va = (intptr_t)self, vb = (intptr_t)data, vc;
    if (LIKELY(va&vb&1 && !__builtin_add_overflow(va, vb^1, &vc))) {
        return (object_t*)vc;
    }
    return integer_add_full(self, data);
}

EXTERN object_t* integer_sub_full(object_t* self, object_t* data);
INLINE object_t* integer_sub(object_t* self, object_t* data) {
    intptr_t va = (intptr_t)self, vb = (intptr_t)data, vc;
    if (LIKELY(va&vb&1 && !__builtin_sub_overflow(va, vb^1, &vc))) {
        return (object_t*)vc;
    }
    return integer_sub_full(self, data);
}

EXTERN object_t* integer_div(object_t* self, object_t* data);
EXTERN object_t* integer_mul(object_t* self, object_t* data);
EXTERN object_t* integer_rem(object_t* self, object_t* data);
EXTERN int32_t   integer_cmp(object_t* self, object_t* data);
EXTERN object_t* integer_shl(object_t* self, object_t* amount);
EXTERN object_t* integer_shr(object_t* self, object_t* amount);

EXTERN object_t* integer_add_int32(object_t* self, int32_t value);
EXTERN int32_t   integer_cmp_int32(object_t* self, int32_t value);
EXTERN int32_t   integer_to_int32_with_overflow(object_t* self, int* overflow);
EXTERN int32_t   integer_to_int32(object_t* self);
EXTERN object_t* integer_create_from_int32(int32_t value);

INLINE bool integer_test_gt(object_t* self, object_t* data) {
    intptr_t va = (intptr_t)self, vb = (intptr_t)data;
    return LIKELY(va&vb&1 && va>vb) || integer_cmp(self, data) > 0;
}
INLINE bool integer_test_ge(object_t* self, object_t* data) {
    intptr_t va = (intptr_t)self, vb = (intptr_t)data;
    return LIKELY(va&vb&1 && va>=vb) || integer_cmp(self, data) >= 0;
}
INLINE bool integer_test_eq(object_t* self, object_t* data) {
    intptr_t va = (intptr_t)self, vb = (intptr_t)data;
    return LIKELY(va&vb&1 && va==vb) || integer_cmp(self, data) == 0;
}
INLINE bool integer_test_lt(object_t* self, object_t* data) {
    intptr_t va = (intptr_t)self, vb = (intptr_t)data;
    return LIKELY(va&vb&1 && va<vb) || integer_cmp(self, data) < 0;
}
INLINE bool integer_test_le(object_t* self, object_t* data) {
    intptr_t va = (intptr_t)self, vb = (intptr_t)data;
    return LIKELY(va&vb&1 && va<=vb) || integer_cmp(self, data) <= 0;
}



/**********************************************************
 *****************************
 *************
 *****
 **
 *                   Strings
 **
 *****
 *************
 *****************************
 **********************************************************/

typedef struct string {
    vtable_t* vtable;
    uint32_t length;
    uint8_t array[16];
} ALIGNED string_t;

struct string_vtable;
EXTERN struct string_vtable STRING_VTABLE;

struct string_empty;
EXTERN struct string_empty STRING_EMPTY;


// Helper macro to compute string length at compile time
#define STRING_LEN(str) (sizeof(str) - 1)

// Maximum characters that can fit in a pointer (leaving room for length byte)
#define MAX_SHORT_LEN ((WORD_SIZE/8) - 1)


// Helper macro to create a short string value for 32-bit
#if IS_LITTLE_ENDIAN
#define SHORT_STRING_32(str, len) ( \
                    (uint32_t)len            | \
                   ((uint32_t)str[0] <<  8 ) | \
    (len < 2 ? 0 : ((uint32_t)str[1] << 16)) | \
    (len < 3 ? 0 : ((uint32_t)str[2] << 24)) )
#else
#define SHORT_STRING_32(str, len) ( \
                    (uint32_t)len            | \
                   ((uint32_t)str[0] << 24 ) | \
    (len < 2 ? 0 : ((uint32_t)str[1] << 16)) | \
    (len < 3 ? 0 : ((uint32_t)str[2] <<  8)) )
#endif

// Helper macro to create a short string value for 64-bit
#if IS_LITTLE_ENDIAN
#define SHORT_STRING_64(str, len) ( \
                    (uint64_t)len            | \
                   ((uint64_t)str[0] <<  8 ) | \
    (len < 2 ? 0 : ((uint64_t)str[1] << 16)) | \
    (len < 3 ? 0 : ((uint64_t)str[2] << 24)) | \
    (len < 4 ? 0 : ((uint64_t)str[3] << 32)) | \
    (len < 5 ? 0 : ((uint64_t)str[4] << 40)) | \
    (len < 6 ? 0 : ((uint64_t)str[5] << 48)) | \
    (len < 7 ? 0 : ((uint64_t)str[6] << 56)) )
#else
#define SHORT_STRING_64(str, len) ( \
                    (uint64_t)len            | \
                   ((uint64_t)str[0] << 56 ) | \
    (len < 2 ? 0 : ((uint64_t)str[1] << 48)) | \
    (len < 3 ? 0 : ((uint64_t)str[2] << 40)) | \
    (len < 4 ? 0 : ((uint64_t)str[3] << 32)) | \
    (len < 5 ? 0 : ((uint64_t)str[4] << 24)) | \
    (len < 6 ? 0 : ((uint64_t)str[5] << 16)) | \
    (len < 7 ? 0 : ((uint64_t)str[6] <<  8)) )
#endif

// Choose appropriate short string implementation based on word size
#if WORD_SIZE == 32
#define SHORT_STRING(str, len) SHORT_STRING_32(str, len)
#else
#define SHORT_STRING(str, len) SHORT_STRING_64(str, len)
#endif

#define STR(contents) ( \
    STRING_LEN(contents) == 0 ? \
        (object_t*)&STRING_EMPTY : \
    STRING_LEN(contents) < MAX_SHORT_LEN ? \
        (object_t*)SHORT_STRING(contents, STRING_LEN(contents)) : \
        (object_t*)&( \
            struct { \
                vtable_t* v; \
                uint32_t l; \
                char a[sizeof(contents)]; \
            }){(vtable_t*)&STRING_VTABLE, STRING_LEN(contents), contents})


INLINE int32_t string_length(object_t* self) {
    return ((string_t*)self)->length;
}

EXTERN object_t* string_allocate(int32_t length);
EXTERN object_t* string_append(object_t* self, object_t* data);
EXTERN object_t* wchar_to_string(object_t* integer);
EXTERN object_t* print_string(object_t* self);



