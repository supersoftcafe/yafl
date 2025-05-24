#include "yafl.h"
#line 3 "string.c"


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

#include <string.h>

EXPORT decl_variable
vtable_t* const STRING_VTABLE = VTABLE_DECLARE(0){
    .object_size = offsetof(string_t, array[0]),
    .array_el_size = sizeof(uint8_t),
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0,
    .functions_mask = 0,
    .array_len_offset = offsetof(string_t, length),
    .implements_array = VTABLE_IMPLEMENTS(0),
};

EXPORT decl_variable
object_t* STRING_EMPTY = (object_t*)&(struct {
    char* vtable;
    uint32_t length;
    uint8_t array[1];
}) {
    .vtable = (char*)STRING_VTABLE,
    .length = 0,
    .array[0] = 0 // Strings have an extra byte at the end for '\0'
};

EXPORT decl_func
string_t* _string_allocate_(int32_t length) {
    string_t* string = (string_t*)array_create(STRING_VTABLE, length);
    string->array[length] = 0; // Zero terminate all strings as a convenience for OS calls
    return string;
}

EXPORT decl_no_inline
object_t* string_create_from_bytes(uint8_t* data, int32_t length) {
    if (length == 0) {
        return (object_t*)&STRING_EMPTY;
    } else if (length < sizeof(uintptr_t)-1) {
        uintptr_t string = 0;
        memcpy(&string, data, length);
        uintptr_t test = 1;
        if (1 == *(uint8_t*)&test)
             string = (string << 8) | length;
        else string |= length;
        return (object_t*)string;
    } else {
        assert(length <= INT32_MAX);
        string_t* string = _string_allocate_(length);
        memcpy(string->array, data, length);
        return (object_t*)string;
    }
}

EXPORT decl_no_inline
object_t* string_create_from_cstr(char* data) {
    return string_create_from_bytes((uint8_t*)data, strlen(data));
}

EXPORT decl_func
int32_t string_length(object_t* self) {
    return ((string_t*)self)->length;
}

EXPORT decl_func
char* string_to_cstr(object_t* self, intptr_t* local_buffer, int32_t* len_ptr) {
    intptr_t masked_bits = (sizeof(uintptr_t)-1) & (intptr_t)self;
    if (masked_bits == 0) {
        *len_ptr = ((string_t*)self)->length;
        return (char*)((string_t*)self)->array;
    } else {
        uintptr_t test = 1;
        if (1 == *(uint8_t*)&test)
             *local_buffer = (uintptr_t)self >> 8;
        else *local_buffer = (uintptr_t)self & ~7;
        *len_ptr = (uint32_t)masked_bits;
        return (char*)local_buffer;
    }
}

EXPORT decl_no_inline
object_t* _string_append2_(char* cstr1, int32_t len1, char* cstr2, int32_t len2) {
    int32_t length = __OP_add_int32__(len1, len2);
    string_t* string;
    uint8_t* ptr;

    if (length < sizeof(uintptr_t)) {
        uintptr_t test = 1;
        string = (string_t*)(uintptr_t)length;
        uint8_t* ptr = (uint8_t*)&string + (1==*(uint8_t*)&test ? 1 : 0);
        memcpy(ptr, cstr1, len1);
        memcpy(ptr+len1, cstr2, len2);
    } else {
        string = _string_allocate_(length);
        ptr = string->array;
    }

    memcpy(ptr, cstr1, len1);
    memcpy(ptr+len1, cstr2, len2);
    return (object_t*)string;
}

EXPORT decl_func
object_t* string_append(object_t* self, object_t* data) {
    intptr_t buf1; int32_t len1;
    char* cstr1 = string_to_cstr(self, &buf1, &len1);
    if (len1 == 0)
        return data;

    intptr_t buf2; int32_t len2;
    char* cstr2 = string_to_cstr(data, &buf2, &len2);
    if (len2 == 0)
        return self;

    return _string_append2_(cstr1, len1, cstr2, len2);
}

EXPORT decl_no_inline
object_t* string_slice_int32(object_t* self, int32_t start, int32_t end) {
    intptr_t buf; int32_t len;
    char* cstr = string_to_cstr(self, &buf, &len);

    if (start < 0)
        start = 0;
    else if (start > len)
        start = len;

    if (end < 0)
        end = 0;
    else if (end > len)
        end = len;

    if (end <= start)
        end = start;

    return string_create_from_bytes((uint8_t*)cstr, end - start);
}

EXPORT decl_no_inline
object_t* string_slice(object_t* self, object_t* start_int, object_t* end_int) {
    int start_overflow, end_overflow;
    int32_t start_int32 = integer_to_int32(start_int, &start_overflow);
    int32_t end_int32 = integer_to_int32(end_int, &end_overflow);
    return string_slice_int32(self, start_int32, end_int32);
}

EXPORT decl_no_inline
int string_compare(object_t* self, object_t* data) {
    intptr_t buf_a, buf_b; int32_t len_a, len_b;
    char* cstr_a = string_to_cstr(self, &buf_a, &len_a);
    char* cstr_b = string_to_cstr(self, &buf_b, &len_b);

    int result = memcmp(cstr_a, cstr_b, len_a < len_b ? len_a : len_b);

    if (result != 0)
        return result;
    if (len_a < len_b)
        return -1;
    if (len_a > len_b)
        return 1;
    return 0;
}

EXPORT decl_no_inline
int32_t __OP_print_int32__(object_t* self) {
    intptr_t buf; int32_t len;
    char* cstr = string_to_cstr(self, &buf, &len);
    return (int32_t)fwrite(cstr, 1, len, stdout);
}

EXPORT decl_func
object_t* __OP_append_str__(object_t* self, object_t* data) {
    return string_append(self, data);
}

