
#include "common.h"
#include "yafl.h"
#include <string.h>


VTABLE_DECLARE_STRUCT(string_vtable, 16);
EXPORT struct string_vtable STRING_VTABLE = {
    .object_size = offsetof(string_t, array[0]),
    .array_el_size = sizeof(uint8_t),
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0,
    .functions_mask = 0,
    .array_len_offset = offsetof(string_t, length),
    .implements_array = VTABLE_IMPLEMENTS(0),
};


struct string_empty {
    vtable_t* vtable;
    uint32_t length;
    uint8_t array[1];
};
EXPORT struct string_empty STRING_EMPTY = {
    .vtable = (vtable_t*)&STRING_VTABLE,
    .length = 0,
    .array = ""
};


HIDDEN string_t* _string_allocate(int32_t length) {
    string_t* string = (string_t*)array_create((vtable_t*)&STRING_VTABLE, length);
    string->array[length] = 0; // Zero terminate all strings as a convenience for OS calls
    return string;
}


HIDDEN object_t* _string_create_from_bytes(uint8_t* data, int32_t length) {
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
        string_t* string = _string_allocate(length);
        memcpy(string->array, data, length);
        return (object_t*)string;
    }
}


HIDDEN object_t* _string_create_from_cstr(char* data) {
    return _string_create_from_bytes((uint8_t*)data, strlen(data));
}


HIDDEN char* _string_to_cstr(object_t* self, intptr_t* local_buffer, int32_t* len_ptr) {
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


HIDDEN object_t* _string_append2(char* cstr1, int32_t len1, char* cstr2, int32_t len2) {
    int64_t length = (int64_t)len1 + len2;
    string_t* string;
    uint8_t* ptr;

    if (length < sizeof(uintptr_t)) {
        uintptr_t test = 1;
        string = (string_t*)(uintptr_t)length;
        ptr = (uint8_t*)&string + (1==*(uint8_t*)&test ? 1 : 0);
    } else {
        string = _string_allocate(length);
        ptr = string->array;
    }

    memcpy(ptr, cstr1, len1);
    memcpy(ptr+len1, cstr2, len2);
    return (object_t*)string;
}


EXPORT object_t* string_append(object_t* self, object_t* data) {
    intptr_t buf1; int32_t len1;
    char* cstr1 = _string_to_cstr(self, &buf1, &len1);
    if (len1 == 0)
        return data;

    intptr_t buf2; int32_t len2;
    char* cstr2 = _string_to_cstr(data, &buf2, &len2);
    if (len2 == 0)
        return self;

    return _string_append2(cstr1, len1, cstr2, len2);
}


EXPORT object_t* string_slice_int32(object_t* self, int32_t start, int32_t end) {
    if (start <= 0 && end >= string_length(self))
        return self;

    intptr_t buf; int32_t len;
    char* cstr = _string_to_cstr(self, &buf, &len);

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

    return _string_create_from_bytes((uint8_t*)cstr, end - start);
}


EXPORT object_t* string_slice(object_t* self, object_t* start_int, object_t* end_int) {
    int32_t start_int32 = integer_to_int32(start_int);
    int32_t end_int32 = integer_to_int32(end_int);
    return string_slice_int32(self, start_int32, end_int32);
}


EXPORT int string_compare(object_t* self, object_t* data) {
    intptr_t buf_a, buf_b; int32_t len_a, len_b;
    char* cstr_a = _string_to_cstr(self, &buf_a, &len_a);
    char* cstr_b = _string_to_cstr(self, &buf_b, &len_b);

    int result = memcmp(cstr_a, cstr_b, len_a < len_b ? len_a : len_b);

    if (result != 0)
        return result;
    if (len_a < len_b)
        return -1;
    if (len_a > len_b)
        return 1;
    return 0;
}


EXPORT object_t* print_string(object_t* self) {
    intptr_t buf; int32_t len;
    char* cstr = _string_to_cstr(self, &buf, &len);
    int32_t result = (int32_t)fwrite(cstr, 1, len, stdout);
    return integer_create_from_int32(result);
}


EXPORT object_t* wchar_to_string(object_t* integer) {
    uint8_t utf8[4];
    int overflow = 0;
    int32_t codepoint = integer_to_int32_with_overflow(integer, &overflow);
    if (codepoint >= 0 && !overflow) {
        if (codepoint <= 0x7F) {
            utf8[0] = (uint8_t)codepoint;
            return _string_create_from_bytes(utf8, 1);
        } else if (codepoint <= 0x7FF) {
            utf8[0] = 0xC0 | (uint8_t)(codepoint >> 6);
            utf8[1] = 0x80 | (uint8_t)(codepoint & 0x3F);
            return _string_create_from_bytes(utf8, 2);
        } else if (codepoint <= 0xFFFF) {
            utf8[0] = 0xE0 | (uint8_t)(codepoint >> 12);
            utf8[1] = 0x80 | (uint8_t)((codepoint >> 6) & 0x3F);
            utf8[2] = 0x80 | (uint8_t)(codepoint & 0x3F);
            return _string_create_from_bytes(utf8, 3);
        } else if (codepoint <= 0x10FFFF) {
            utf8[0] = 0xF0 | (uint8_t)(codepoint >> 18);
            utf8[1] = 0x80 | (uint8_t)((codepoint >> 12) & 0x3F);
            utf8[2] = 0x80 | (uint8_t)((codepoint >> 6) & 0x3F);
            utf8[3] = 0x80 | (uint8_t)(codepoint & 0x3F);
            return _string_create_from_bytes(utf8, 4);
        }
    }
    __abort_on_overflow();
    __builtin_unreachable();
}

