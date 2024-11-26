
#include "integer.h"
#include "string.h"
#include <string.h>
#include <assert.h>


struct string {
    vtable_t* vtable;
    uint32_t length;
    uint8_t array[0];
};
typedef struct string string_t;
enum { MASK = sizeof(uintptr_t)-1 };


static vtable_t VTABLE = {
    .object_size = offsetof(string_t, array[0]),
    .array_el_size = 1,
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0,
    .array_len_index = offsetof(string_t, length),
    .functions_mask = 0
};

// Special case for the zero length string so that NULL still means absent, and not "".
static struct {
    vtable_t* vtable;
    uint32_t length;
    uint8_t array[1];
} EMPTY = {
    .vtable = &VTABLE,
    .length = 0,
    .array[0] = 0
};


object_t* string_create() {
    return (object_t*)&EMPTY;
}

static string_t* string_allocate(intptr_t length) {
    string_t* string = object_create_array(string_t, array, length + 1);
    string->vtable = &VTABLE;
    string->length = (uint32_t)length;
    string->array[length] = 0; // Zero terminate all strings as a convenience for OS calls
    return string;
}

object_t* string_create_from_bytes(uint8_t* data, intptr_t length) {
    if (length == 0) {
        return (object_t*)&EMPTY;
    } else if (length < sizeof(object_t*)) {
        uintptr_t string = length;
        for (intptr_t index = 0; index < length; index ++)
            string |= (uintptr_t)data[index] << ((sizeof(uintptr_t)-index) * 8 - 8);
        return (object_t*)string;
    } else {
        string_t* string = string_allocate(length);
        memcpy(string->array, data, length);
        return (object_t*)string;
    }
}

object_t* string_create_from_cstr(char* data) {
    return string_create_from_bytes((uint8_t*)data, strlen(data));
}

intptr_t string_length_native(object_t* self) {
    uintptr_t length = MASK & (intptr_t)self;
    if (length == 0) {
        length = ((string_t*)self)->length;
    }
    return length;
}

object_t* string_length(object_t* self) {
    return integer_create_from_native(string_length_native(self));
}

char* string_to_cstr(object_t* self, intptr_t* local_buffer) {
    intptr_t length = MASK & (intptr_t)self;
    if (length == 0) {
        length = ((string_t*)self)->length;
        return (char*)((string_t*)self)->array;
    } else {
        uint8_t* buffer = (uint8_t*)local_buffer;
        for (intptr_t index = 0; index < length; index ++)
            buffer[index] = (uint8_t)(((uintptr_t)self) >> ((sizeof(uintptr_t)-index) * 8 - 8));
        buffer[length] = 0;
        return (char*)buffer;
    }
}

object_t* string_append(object_t* self, object_t* data) {
    intptr_t buf_a, buf_b;
    uint8_t* cstr_a = (uint8_t*)string_to_cstr(self, &buf_a);
    uint8_t* cstr_b = (uint8_t*)string_to_cstr(data, &buf_b);
    intptr_t len_a = string_length_native(self);
    intptr_t len_b = string_length_native(data);

    intptr_t length = len_a + len_b;
    if (length == 0) {
        return (object_t*)&EMPTY;
    } else if (length < sizeof(object_t*)) {
        uintptr_t string = length;
        for (uint32_t index = 0; index < len_a; index ++)
            string |= (uintptr_t)cstr_a[index] << ((sizeof(uintptr_t)- index       ) * 8 - 8);
        for (uint32_t index = 0; index < len_b; index ++)
            string |= (uintptr_t)cstr_b[index] << ((sizeof(uintptr_t)-(index+len_a)) * 8 - 8);
        return (object_t*)string;
    } else {
        string_t* string = string_allocate(length);
        memcpy(string->array, cstr_a, len_a);
        memcpy(string->array+len_a, cstr_b, len_b);
        return (object_t*)string;
    }
}

object_t* string_slice(object_t* self, object_t* start, object_t* end) {
    intptr_t buf;
    char* cstr = string_to_cstr(self, &buf);
    intptr_t len = string_length_native(self);

    if (integer_compare_with_native(start, len) >= 0 || integer_compare_with_native(end, 0) <= 0) {
        return (object_t*)&EMPTY;
    }

    intptr_t native_end = integer_compare_with_native(end, len) < 0 ? integer_to_native(end) : len;
    intptr_t native_start = integer_compare_with_native(start, 0) >= 0 ? integer_to_native(start) : 0;
    intptr_t length = native_end - native_start;

    if (length == 0) {
        return (object_t*)&EMPTY;
    } else if (length < sizeof(object_t*)) {
        uintptr_t string = length;
        for (intptr_t index = 0; index < length; index ++)
            string |= (uintptr_t)cstr[native_start+index] << ((sizeof(uintptr_t)-index) * 8 - 8);
        return (object_t*)string;
    } else {
        string_t* string = string_allocate(length);
        memcpy(string->array, cstr + native_start, length);
        return (object_t*)string;
    }
}

int string_compare(object_t* self, object_t* data) {
    intptr_t buf_a, buf_b;
    char* cstr_a = string_to_cstr(self, &buf_a);
    char* cstr_b = string_to_cstr(self, &buf_b);
    intptr_t len_a = string_length_native(self);
    intptr_t len_b = string_length_native(data);

    int result = memcmp(cstr_a, cstr_b, len_a < len_b ? len_a : len_b);
    if (result != 0) return result;
    if (len_a < len_b) return -1;
    if (len_a > len_b) return 1;
    return 0;
}

