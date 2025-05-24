#pragma once
#line 3 "yafl.h"


/**********************************************************
 *****************************
 *************
 *****
 **
 *            Common and useful definitions
 **
 *****
 *************
 *****************************
 **********************************************************/

#include <stdint.h>
#include <stdbool.h>
#include <string.h>


#define likely(x) __builtin_expect((x),1)
#define unlikely(x) __builtin_expect((x),0)
#define indexof(type, field) (offsetof(type, field) / sizeof(((type*)NULL)->field))
#define total_bits(type) (sizeof(type) * 8)


#ifndef EXTERN
#define EXTERN extern
#endif

#ifndef EXPORT
#define EXPORT
#endif


#ifdef NDEBUG
#define decl_cold __attribute__((cold,noinline))
#define decl_no_inline __attribute__((noinline))
#define decl_func
#define decl_variable
#else
#define decl_cold __attribute__((noinline))
#define decl_no_inline __attribute__((noinline))
#define decl_func __attribute__((noinline))
#define decl_variable
#endif


#define index_of_lowest_bit(value)               \
        _Generic( (value),                       \
            unsigned long long: __builtin_ctzll, \
            unsigned long: __builtin_ctzl,       \
            unsigned int: __builtin_ctz          \
        )(value)


#if UINTPTR_MAX == 0xFFFFFFFF
#define WORD_SIZE 32
#elif UINTPTR_MAX == 0xFFFFFFFFFFFFFFFF
#define WORD_SIZE 64
#else
#error "Unknown pointer size or unsupported platform."
#endif


#define ALIGNED     __attribute__((aligned(32)))


// Helper macro to determine if we're on a little-endian system
#if defined(__BYTE_ORDER__) && __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__
#define IS_LITTLE_ENDIAN 1
#elif defined(__BYTE_ORDER__) && __BYTE_ORDER__ == __ORDER_BIG_ENDIAN__
#define IS_LITTLE_ENDIAN 0
#elif defined(_WIN32)
#define IS_LITTLE_ENDIAN 1
#else
#error "Cannot determine endianness"
#endif


#if defined(__aarch64__) && defined(__APPLE__)
    #define CACHE_LINE_SIZE 128
#elif defined(__x86_64__) || defined(_M_X64)
    #define CACHE_LINE_SIZE 64
#else
    #define CACHE_LINE_SIZE 64 // fallback
#endif



/**********************************************************
 *****************************
 *************
 *****
 **
 *                   Debug tools
 **
 *****
 *************
 *****************************
 **********************************************************/

#include <stdnoreturn.h>
#include <stdio.h>
#include <stdarg.h>
#include <stdlib.h>
#include <errno.h>

EXTERN decl_func
void log_error(char const* format, ...);

EXTERN decl_func
noreturn void log_error_and_exit(char const* format, ...);

#define ERROR(...)  log_error_and_exit(__VA_ARGS__)

#ifndef NDEBUG
#define DEBUG(...)  log_error(__VA_ARGS__)
#else
#define DEBUG(...)
#endif

#define ZZ  DEBUG("%s: %d\n", __FILE__, __LINE__);


/**********************************************************
 *****************************
 *************
 *****
 **
 *                   Threading
 **
 *****
 *************
 *****************************
 **********************************************************/

#include <pthread.h>

#ifndef __STDC_NO_THREADS__
#include <threads.h>
#endif

#ifndef __STDC_NO_ATOMICS__
#include <stdatomic.h>
#endif

#ifndef thread_local
# if __STDC_VERSION__ >= 201112 && !defined __STDC_NO_THREADS__
#  define thread_local _Thread_local
# elif defined _WIN32 && ( \
       defined _MSC_VER || \
       defined __ICL || \
       defined __DMC__ || \
       defined __BORLANDC__ )
#  define thread_local __declspec(thread)
/* note that ICC (linux) and Clang are covered by __GNUC__ */
# elif defined __GNUC__ || \
       defined __SUNPRO_C || \
       defined __xlC__
#  define thread_local __thread
# else
#  error "Cannot define thread_local"
# endif
#endif


/**********************************************************
 *****************************
 *************
 *****
 **
 *                   Objects
 **
 *****
 *************
 *****************************
 **********************************************************/

#include <stddef.h>
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

typedef struct vtable {
    uint16_t object_size;
    uint16_t array_el_size;
    uint32_t object_pointer_locations;
    uint32_t array_el_pointer_locations;
    uint32_t functions_mask;     // Size-1, must be n^2-1, is the bit mask used to lookup function pointers
    uint16_t array_len_offset;   // Offset of uint32_t array length field
    struct vtable** implements_array; // Array of all classes that this class extends
#ifdef NDEBUG
    vtable_entry_t lookup[0];
#else
    vtable_entry_t lookup[16];   // The array size is nominal to help with debugging
#endif
} vtable_t;

#define VTABLE_DECLARE(LOOKUP_COUNT)\
        (struct vtable*)&(const struct {\
            uint16_t object_size;\
            uint16_t array_el_size;\
            uint32_t object_pointer_locations;\
            uint32_t array_el_pointer_locations;\
            uint32_t functions_mask;\
            uint16_t array_len_offset;\
            struct vtable** implements_array;\
            vtable_entry_t lookup[LOOKUP_COUNT];\
        })

#define VTABLE_IMPLEMENTS(COUNT, ...) (vtable_t**)&(struct{vtable_t*p[COUNT];vtable_t*t;}){.p = {__VA_ARGS__}, .t = (vtable_t*)0 }

typedef struct {
    vtable_t* vtable;
} object_t;

extern thread_local bool thread_is_worker;

// This calculation needs to work with positive signed 32 bit numbers
#define rotate_function_id(id)\
        ((id * sizeof(intptr_t) * 2) | (id / (134217728 / sizeof(intptr_t) * 8)))

EXTERN decl_func
vtable_t* object_get_vtable(void* object);

EXTERN decl_func
object_t* object_mutation(object_t* ptr);

EXTERN decl_func
fun_t vtable_lookup(void* object, intptr_t id);

EXTERN decl_func
fun_t vtable_fast_lookup(void* object, intptr_t id);

EXTERN decl_func
void* object_create(vtable_t* vtable);

EXTERN decl_func
void* array_create(vtable_t* vtable, int32_t length);

EXTERN decl_func
void __abort_on_vtable_lookup();

EXTERN decl_func
void __abort_on_out_of_memory();

EXTERN decl_func
void __abort_on_too_large_object();

EXTERN decl_func
void __abort_on_heap_allocation_on_non_worker_thread();

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

EXTERN decl_func
void thread_set_hook(void(*)());

EXTERN decl_func
void declare_roots_thread(void(*)(object_t**));

EXTERN decl_func
void declare_local_roots_thread(void(*)(object_t**));

EXTERN decl_no_inline
object_t* thread_work_prepare(fun_t action);

EXTERN decl_no_inline
void thread_work_post_io(object_t* work);

EXTERN decl_func
void thread_work_post_fast(object_t* work);

EXTERN decl_no_inline
void thread_start();



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

#undef DECLARE_OP_MATH_INT_WITH_OVERFLOW_CHECK
#define DECLARE_OP_MATH_INT_WITH_OVERFLOW_CHECK(type, operation)\
        EXTERN decl_func\
        type ## _t __OP_ ## operation ## _ ## type ## __(type ## _t a, type ## _t b);

DECLARE_OP_MATH_INT_WITH_OVERFLOW_CHECK(int8 , add)
DECLARE_OP_MATH_INT_WITH_OVERFLOW_CHECK(int16, add)
DECLARE_OP_MATH_INT_WITH_OVERFLOW_CHECK(int32, add)
DECLARE_OP_MATH_INT_WITH_OVERFLOW_CHECK(int64, add)
DECLARE_OP_MATH_INT_WITH_OVERFLOW_CHECK(int8 , sub)
DECLARE_OP_MATH_INT_WITH_OVERFLOW_CHECK(int16, sub)
DECLARE_OP_MATH_INT_WITH_OVERFLOW_CHECK(int32, sub)
DECLARE_OP_MATH_INT_WITH_OVERFLOW_CHECK(int64, sub)

#undef DECLARE_OP_CONVERT_INT_WITH_OVERFLOW_CHECK
#define DECLARE_OP_CONVERT_INT_WITH_OVERFLOW_CHECK(from_type, to_type)\
        EXTERN decl_func\
        to_type ## _t __OP_convert_ ## from_type ## _to_ ## to_type ## __(from_type ## _t a);

DECLARE_OP_CONVERT_INT_WITH_OVERFLOW_CHECK(int8 , int16)
DECLARE_OP_CONVERT_INT_WITH_OVERFLOW_CHECK(int8 , int32)
DECLARE_OP_CONVERT_INT_WITH_OVERFLOW_CHECK(int8 , int64)
DECLARE_OP_CONVERT_INT_WITH_OVERFLOW_CHECK(int16, int8 )
DECLARE_OP_CONVERT_INT_WITH_OVERFLOW_CHECK(int16, int32)
DECLARE_OP_CONVERT_INT_WITH_OVERFLOW_CHECK(int16, int64)
DECLARE_OP_CONVERT_INT_WITH_OVERFLOW_CHECK(int32, int8 )
DECLARE_OP_CONVERT_INT_WITH_OVERFLOW_CHECK(int32, int16)
DECLARE_OP_CONVERT_INT_WITH_OVERFLOW_CHECK(int32, int64)
DECLARE_OP_CONVERT_INT_WITH_OVERFLOW_CHECK(int64, int8 )
DECLARE_OP_CONVERT_INT_WITH_OVERFLOW_CHECK(int64, int16)
DECLARE_OP_CONVERT_INT_WITH_OVERFLOW_CHECK(int64, int32)


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
    intptr_t array[0];
} ALIGNED integer_t;

EXTERN decl_variable
vtable_t* const INTEGER_VTABLE;

#define literal_integer_small_value(value) ((object_t*)((value)<<1)|1)
#define INTEGER_DECLARE_BEGIN(global_name, int32_count)\
        EXPORT struct {\
            vtable_t* vtable;\
            uint32_t length;\
            intptr_t array[WORD_SIZE == 64 ? (int32_count+1)/2 : int32_count];\
        } global_name = {\
            .vtable = INTEGER_VTABLE,\
            .length = WORD_SIZE == 64 ? (int32_count+1)/2 : int32_count,\
            .array = {
#define INTEGER_DECLARE_SINGLE(a)   (intptr_t)(a),
#if WORD_SIZE == 64
#define INTEGER_DECLARE_PAIR(a, b)  (((intptr_t)(b) << 32) | ((intptr_t)(a) & 0xffffffffull)),
#else
#define INTEGER_DECLARE_PAIR(a, b)  (a),(b),
#endif
#define INTEGER_DECLARE_END() }\
        };

EXTERN decl_func
object_t* integer_create_from_intptr(intptr_t value);

EXTERN decl_func
object_t* integer_add(object_t* self, object_t* data);

EXTERN decl_func
object_t* integer_add_intptr(object_t* self, intptr_t value);

EXTERN decl_func
int integer_cmp_intptr(object_t* self, intptr_t value);

EXTERN decl_func
int integer_cmp(object_t* self, object_t* data);

EXTERN decl_func
int32_t integer_to_int32(object_t* self, int* overflow);


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
    uint8_t array[0];
} ALIGNED string_t;

EXTERN decl_variable
vtable_t* const STRING_VTABLE;

EXTERN decl_variable
object_t* STRING_EMPTY;


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
            }){STRING_VTABLE, STRING_LEN(contents), contents})



EXTERN decl_func
void __entrypoint__(object_t* self, fun_t continuation);

EXTERN decl_func
void declare_roots_yafl(void(*)(object_t**));


